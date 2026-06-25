from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from water_ledger.paths import DB_PATH, PRIVATE_ROOT, ROOT
from water_ledger.privacy import scan_public_workspace


PID_FILE = PRIVATE_ROOT / "logs" / "server.pid"
LOG_FILE = PRIVATE_ROOT / "logs" / "server.log"


def money_to_cents(value: str) -> int:
    normalized = value.strip().replace(",", "").replace("￥", "").replace("¥", "")
    amount = Decimal(normalized)
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def normalize_balance_time(value: str) -> str:
    text = value.strip()
    if not text:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if len(text) == 10:
        datetime.strptime(text, "%Y-%m-%d")
        return f"{text} 23:59:59"
    parsed = datetime.fromisoformat(text)
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def configure_profile(config_path: os.PathLike[str] | str, force: bool = False) -> None:
    if not sys.stdin.isatty() or (Path(config_path).exists() and not force):
        return
    name = input("账本显示名（直接回车使用“我的个人资产账本”）：").strip()
    if not name:
        return
    title = name if name.endswith("的个人资产账本") else f"{name}的个人资产账本"
    try:
        import yaml
    except ImportError:
        return
    path = Path(config_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    profile = data.setdefault("profile", {})
    profile["display_name"] = name
    profile["ledger_title"] = title
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def configure_initial_balances(config_path: os.PathLike[str] | str) -> None:
    if not sys.stdin.isatty():
        return
    try:
        import yaml
    except ImportError:
        return

    path = Path(config_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    accounts = data.get("accounts") or []
    if not accounts:
        return

    print("可选：录入账户当前余额。银行/券商账单或接口会提供余额的账户可直接回车跳过。")
    updated = False
    for account in accounts:
        if account.get("manual_balance_cents") not in (None, "") and account.get("manual_balance_at"):
            continue
        name = account.get("name") or "未命名账户"
        account_type = account.get("account_type") or ""
        if account_type == "liability":
            prompt = f"账户「{name}」当前欠款（元；正数会按负债保存，回车跳过）："
        else:
            prompt = f"账户「{name}」当前余额（元，回车跳过）："
        raw_amount = input(prompt).strip()
        if not raw_amount:
            continue
        try:
            balance_cents = money_to_cents(raw_amount)
        except (InvalidOperation, ValueError):
            print(f"跳过「{name}」：金额格式无法识别。")
            continue
        if account_type == "liability" and balance_cents > 0:
            balance_cents = -balance_cents

        raw_time = input("余额对应时间（YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS，直接回车使用现在）：")
        try:
            balance_at = normalize_balance_time(raw_time)
        except ValueError:
            print(f"跳过「{name}」：时间格式无法识别。")
            continue

        account["manual_balance_cents"] = balance_cents
        account["manual_balance_at"] = balance_at
        updated = True

    if updated:
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def init_workspace(force: bool = False, configure_balances: bool = False, no_balance_prompts: bool = False) -> None:
    dirs = [
        PRIVATE_ROOT,
        PRIVATE_ROOT / "imports" / "alipay",
        PRIVATE_ROOT / "imports" / "wechat",
        PRIVATE_ROOT / "imports" / "bank",
        PRIVATE_ROOT / "data",
        PRIVATE_ROOT / "outputs" / "longbridge_live_snapshots",
        PRIVATE_ROOT / "logs",
    ]
    for path in dirs:
        path.mkdir(parents=True, exist_ok=True)

    src_config = ROOT / "config" / "config.example.yaml"
    if not src_config.exists():
        src_config = ROOT / "water_ledger" / "resources" / "config.example.yaml"
    dst_config = PRIVATE_ROOT / "config.yaml"
    created_config = force or not dst_config.exists()
    if created_config:
        shutil.copyfile(src_config, dst_config)
    if created_config:
        configure_profile(dst_config, force=True)
    if not no_balance_prompts and (created_config or configure_balances):
        configure_initial_balances(dst_config)

    manual_example = ROOT / "examples" / "manual_transactions.example.json"
    manual_dst = PRIVATE_ROOT / "data" / "manual_transactions.json"
    if manual_example.exists() and (force or not manual_dst.exists()):
        shutil.copyfile(manual_example, manual_dst)

    print(json.dumps({
        "private_root": str(PRIVATE_ROOT),
        "config": str(dst_config),
        "database": str(DB_PATH),
    }, ensure_ascii=False, indent=2))


def import_command() -> None:
    from water_ledger.pipeline import rebuild_database

    print(json.dumps(rebuild_database(), ensure_ascii=False, indent=2))


def serve_command(host: str, port: int) -> None:
    from web_app.server import run_server

    run_server(host, port)


def pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_pid() -> int | None:
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


def start_command(host: str, port: int) -> int:
    PRIVATE_ROOT.joinpath("logs").mkdir(parents=True, exist_ok=True)
    existing = read_pid()
    if existing and pid_is_running(existing):
        print(json.dumps({
            "status": "already-running",
            "pid": existing,
            "url": f"http://{host}:{port}",
            "log": str(LOG_FILE),
        }, ensure_ascii=False, indent=2))
        return 0
    if port_is_open(host, port):
        print(json.dumps({
            "status": "port-in-use",
            "url": f"http://{host}:{port}",
            "hint": "Stop the process using this port, then run `python -m water_ledger start` again.",
        }, ensure_ascii=False, indent=2))
        return 1

    log = LOG_FILE.open("a", encoding="utf-8")
    env = os.environ.copy()
    env.setdefault("WATER_LEDGER_PRIVATE_DIR", str(PRIVATE_ROOT))
    proc = subprocess.Popen(
        [sys.executable, "-m", "water_ledger", "serve", "--host", host, "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    time.sleep(0.5)
    if proc.poll() is not None:
        PID_FILE.unlink(missing_ok=True)
        print(json.dumps({
            "status": "failed",
            "exit_code": proc.returncode,
            "log": str(LOG_FILE),
        }, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({
        "status": "started",
        "pid": proc.pid,
        "url": f"http://{host}:{port}",
        "log": str(LOG_FILE),
    }, ensure_ascii=False, indent=2))
    return 0


def stop_command() -> int:
    pid = read_pid()
    if not pid or not pid_is_running(pid):
        PID_FILE.unlink(missing_ok=True)
        print(json.dumps({"status": "not-running"}, ensure_ascii=False, indent=2))
        return 0
    os.kill(pid, signal.SIGTERM)
    PID_FILE.unlink(missing_ok=True)
    print(json.dumps({"status": "stopped", "pid": pid}, ensure_ascii=False, indent=2))
    return 0


def status_command() -> int:
    pid = read_pid()
    running = bool(pid and pid_is_running(pid))
    print(json.dumps({
        "status": "running" if running else "not-running",
        "pid": pid if running else None,
        "url": "http://127.0.0.1:8787" if running else None,
        "log": str(LOG_FILE),
    }, ensure_ascii=False, indent=2))
    return 0 if running else 1


def privacy_check_command() -> int:
    findings = scan_public_workspace()
    if findings:
        print("Privacy check failed:")
        for finding in findings:
            print(f"- {finding.path}: {finding.kind} ({finding.detail})")
        return 1
    print("Privacy check passed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="water-ledger")
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="Create local private workspace")
    init_parser.add_argument("--force", action="store_true", help="overwrite generated private config/example files")
    init_parser.add_argument("--configure-balances", action="store_true", help="prompt for manual account balances even when config already exists")
    init_parser.add_argument("--no-balance-prompts", action="store_true", help="skip interactive balance prompts")

    sub.add_parser("import", help="Import bills and rebuild the local database")

    serve_parser = sub.add_parser("serve", help="Run the local dashboard server")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", default=8787, type=int)

    start_parser = sub.add_parser("start", help="Start the local dashboard in the background")
    start_parser.add_argument("--host", default="127.0.0.1")
    start_parser.add_argument("--port", default=8787, type=int)

    sub.add_parser("stop", help="Stop the background dashboard")
    sub.add_parser("status", help="Show background dashboard status")

    sub.add_parser("privacy-check", help="Scan public workspace for private finance data")

    args = parser.parse_args(argv)
    if args.command == "init":
        init_workspace(
            force=args.force,
            configure_balances=args.configure_balances,
            no_balance_prompts=args.no_balance_prompts,
        )
        return 0
    if args.command == "import":
        import_command()
        return 0
    if args.command == "serve":
        serve_command(args.host, args.port)
        return 0
    if args.command == "start":
        return start_command(args.host, args.port)
    if args.command == "stop":
        return stop_command()
    if args.command == "status":
        return status_command()
    if args.command == "privacy-check":
        return privacy_check_command()
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
