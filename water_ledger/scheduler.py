from __future__ import annotations

import hashlib
import json
import os
import plistlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from water_ledger.paths import CONFIG_PATH, DB_PATH, PRIVATE_ROOT, ROOT


DEFAULT_SNAPSHOT_TIME = "04:01"


@dataclass(frozen=True)
class DailyBrokerageSchedule:
    label: str
    task_name: str
    plist_path: Path
    windows_script_path: Path
    metadata_path: Path
    time: str
    provider: str
    log_path: Path


def parse_time(value: str) -> tuple[int, int]:
    try:
        hour_text, minute_text = value.strip().split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError as exc:
        raise SystemExit("Time must use HH:MM, for example 04:01.") from exc
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise SystemExit("Time must use HH:MM with hour 00-23 and minute 00-59.")
    return hour, minute


def normalized_time(value: str) -> str:
    hour, minute = parse_time(value)
    return f"{hour:02d}:{minute:02d}"


def project_id(root: Path = ROOT) -> str:
    return hashlib.sha1(str(root.resolve()).encode("utf-8")).hexdigest()[:10]


def project_label(root: Path = ROOT) -> str:
    return f"com.water-ledger.brokerage-snapshot.{project_id(root)}"


def windows_task_name(root: Path = ROOT) -> str:
    return f"Water Ledger Brokerage Snapshot {project_id(root)}"


def launch_agents_dir() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def project_python() -> str:
    candidates = [
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def default_schedule(
    *,
    time_value: str = DEFAULT_SNAPSHOT_TIME,
    provider: str = "enabled",
    label: str | None = None,
    task_name: str | None = None,
    launch_dir: Path | None = None,
) -> DailyBrokerageSchedule:
    safe_time = normalized_time(time_value)
    safe_label = label or project_label()
    log_path = PRIVATE_ROOT / "logs" / "brokerage_snapshot.log"
    return DailyBrokerageSchedule(
        label=safe_label,
        task_name=task_name or windows_task_name(),
        plist_path=(launch_dir or launch_agents_dir()) / f"{safe_label}.plist",
        windows_script_path=PRIVATE_ROOT / "logs" / "daily_brokerage_snapshot.cmd",
        metadata_path=PRIVATE_ROOT / "logs" / "brokerage_schedule.json",
        time=safe_time,
        provider=provider,
        log_path=log_path,
    )


def command_args(provider: str) -> list[str]:
    return [project_python(), "-m", "water_ledger", "brokerage-snapshot", "--provider", provider]


def quote_cmd(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def build_windows_script(schedule: DailyBrokerageSchedule) -> str:
    args = " ".join(quote_cmd(part) for part in command_args(schedule.provider))
    return "\r\n".join(
        [
            "@echo off",
            f"cd /d {quote_cmd(str(ROOT))}",
            f"set {quote_cmd(f'WATER_LEDGER_PRIVATE_DIR={PRIVATE_ROOT}')}",
            f"set {quote_cmd(f'WATER_LEDGER_DB_PATH={DB_PATH}')}",
            f"set {quote_cmd(f'WATER_LEDGER_CONFIG={CONFIG_PATH}')}",
            f"{args} >> {quote_cmd(str(schedule.log_path))} 2>&1",
            "",
        ]
    )


def write_windows_script(schedule: DailyBrokerageSchedule) -> None:
    schedule.windows_script_path.parent.mkdir(parents=True, exist_ok=True)
    schedule.windows_script_path.write_text(build_windows_script(schedule), encoding="utf-8")


def write_schedule_metadata(schedule: DailyBrokerageSchedule, scheduler: str) -> None:
    schedule.metadata_path.parent.mkdir(parents=True, exist_ok=True)
    schedule.metadata_path.write_text(
        json.dumps(
            {
                "scheduler": scheduler,
                "label": schedule.label,
                "task_name": schedule.task_name,
                "time": schedule.time,
                "provider": schedule.provider,
                "command": command_args(schedule.provider),
                "log": str(schedule.log_path),
                "plist": str(schedule.plist_path),
                "windows_script": str(schedule.windows_script_path),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def read_schedule_metadata(schedule: DailyBrokerageSchedule) -> dict[str, Any]:
    try:
        data = json.loads(schedule.metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def build_launch_agent(schedule: DailyBrokerageSchedule) -> dict[str, Any]:
    hour, minute = parse_time(schedule.time)
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"),
        "WATER_LEDGER_PRIVATE_DIR": str(PRIVATE_ROOT),
        "WATER_LEDGER_DB_PATH": str(DB_PATH),
        "WATER_LEDGER_CONFIG": str(CONFIG_PATH),
    }
    return {
        "Label": schedule.label,
        "ProgramArguments": command_args(schedule.provider),
        "WorkingDirectory": str(ROOT),
        "EnvironmentVariables": env,
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "StandardOutPath": str(schedule.log_path),
        "StandardErrorPath": str(schedule.log_path),
        "RunAtLoad": False,
    }


def launchctl_domain() -> str:
    return f"gui/{os.getuid()}"


def run_launchctl(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["launchctl", *args], check=check, capture_output=True, text=True)


def run_schtasks(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["schtasks.exe", *args], check=check, capture_output=True, text=True)


def load_launch_agent(plist_path: Path, label: str) -> None:
    domain = launchctl_domain()
    run_launchctl(["bootout", domain, str(plist_path)], check=False)
    run_launchctl(["bootstrap", domain, str(plist_path)])
    run_launchctl(["enable", f"{domain}/{label}"], check=False)


def unload_launch_agent(plist_path: Path) -> None:
    run_launchctl(["bootout", launchctl_domain(), str(plist_path)], check=False)


def install_macos_schedule(schedule: DailyBrokerageSchedule, load: bool) -> bool:
    schedule.plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist = build_launch_agent(schedule)
    with schedule.plist_path.open("wb") as f:
        plistlib.dump(plist, f, sort_keys=False)
    if load:
        load_launch_agent(schedule.plist_path, schedule.label)
    return load


def install_windows_schedule(schedule: DailyBrokerageSchedule, load: bool) -> bool:
    write_windows_script(schedule)
    if load:
        run_schtasks(
            [
                "/Create",
                "/F",
                "/SC",
                "DAILY",
                "/ST",
                schedule.time,
                "/TN",
                schedule.task_name,
                "/TR",
                f'cmd.exe /c "{schedule.windows_script_path}"',
            ]
        )
    return load


def install_daily_brokerage_schedule(
    *,
    time_value: str = DEFAULT_SNAPSHOT_TIME,
    provider: str = "enabled",
    load: bool = True,
    label: str | None = None,
    task_name: str | None = None,
    launch_dir: Path | None = None,
) -> dict[str, Any]:
    schedule = default_schedule(
        time_value=time_value,
        provider=provider,
        label=label,
        task_name=task_name,
        launch_dir=launch_dir,
    )
    schedule.log_path.parent.mkdir(parents=True, exist_ok=True)
    loaded = False
    if sys.platform == "darwin":
        loaded = install_macos_schedule(schedule, load)
        scheduler = "launchd"
    elif sys.platform == "win32":
        loaded = install_windows_schedule(schedule, load)
        scheduler = "windows-task-scheduler"
    elif load:
        raise SystemExit("Daily scheduling currently supports macOS launchd and Windows Task Scheduler.")
    else:
        loaded = install_macos_schedule(schedule, load=False)
        scheduler = "launchd-plist"
    write_schedule_metadata(schedule, scheduler)
    return {
        "status": "installed",
        "scheduler": scheduler,
        "loaded": loaded,
        "label": schedule.label,
        "task_name": schedule.task_name,
        "time": schedule.time,
        "provider": schedule.provider,
        "plist": str(schedule.plist_path),
        "windows_script": str(schedule.windows_script_path),
        "metadata": str(schedule.metadata_path),
        "log": str(schedule.log_path),
        "command": " ".join(command_args(schedule.provider)),
    }


def uninstall_daily_brokerage_schedule(
    *,
    label: str | None = None,
    task_name: str | None = None,
    launch_dir: Path | None = None,
) -> dict[str, Any]:
    schedule = default_schedule(label=label, task_name=task_name, launch_dir=launch_dir)
    existed = False
    if sys.platform == "darwin":
        existed = schedule.plist_path.exists()
        if existed:
            unload_launch_agent(schedule.plist_path)
        schedule.plist_path.unlink(missing_ok=True)
    elif sys.platform == "win32":
        query = run_schtasks(["/Query", "/TN", schedule.task_name], check=False)
        existed = query.returncode == 0
        if existed:
            run_schtasks(["/Delete", "/TN", schedule.task_name, "/F"], check=False)
        schedule.windows_script_path.unlink(missing_ok=True)
    else:
        existed = schedule.plist_path.exists() or schedule.windows_script_path.exists()
        schedule.plist_path.unlink(missing_ok=True)
        schedule.windows_script_path.unlink(missing_ok=True)
    schedule.metadata_path.unlink(missing_ok=True)
    return {
        "status": "uninstalled" if existed else "not-installed",
        "label": schedule.label,
        "task_name": schedule.task_name,
        "plist": str(schedule.plist_path),
        "windows_script": str(schedule.windows_script_path),
        "metadata": str(schedule.metadata_path),
    }


def read_schedule_plist(plist_path: Path) -> dict[str, Any]:
    with plist_path.open("rb") as f:
        data = plistlib.load(f)
    return data if isinstance(data, dict) else {}


def launch_agent_loaded(label: str) -> bool:
    if sys.platform != "darwin":
        return False
    result = run_launchctl(["print", f"{launchctl_domain()}/{label}"], check=False)
    return result.returncode == 0


def macos_schedule_status(schedule: DailyBrokerageSchedule) -> dict[str, Any]:
    installed = schedule.plist_path.exists()
    data = read_schedule_plist(schedule.plist_path) if installed else {}
    interval = data.get("StartCalendarInterval") if isinstance(data.get("StartCalendarInterval"), dict) else {}
    hour = interval.get("Hour")
    minute = interval.get("Minute")
    args = data.get("ProgramArguments") or []
    return {
        "status": "installed" if installed else "not-installed",
        "scheduler": "launchd",
        "loaded": launch_agent_loaded(schedule.label) if installed else False,
        "label": schedule.label,
        "task_name": schedule.task_name,
        "time": f"{int(hour):02d}:{int(minute):02d}" if hour is not None and minute is not None else None,
        "provider": args[-1] if len(args) >= 2 and args[-2] == "--provider" else None,
        "plist": str(schedule.plist_path),
        "windows_script": str(schedule.windows_script_path),
        "log": str(data.get("StandardOutPath") or schedule.log_path),
    }


def windows_schedule_status(schedule: DailyBrokerageSchedule) -> dict[str, Any]:
    result = run_schtasks(["/Query", "/TN", schedule.task_name, "/FO", "LIST", "/V"], check=False)
    installed = result.returncode == 0
    metadata = read_schedule_metadata(schedule)
    return {
        "status": "installed" if installed else "not-installed",
        "scheduler": "windows-task-scheduler",
        "loaded": installed,
        "label": schedule.label,
        "task_name": schedule.task_name,
        "time": metadata.get("time") if installed else None,
        "provider": metadata.get("provider") if installed else None,
        "plist": str(schedule.plist_path),
        "windows_script": str(schedule.windows_script_path),
        "metadata": str(schedule.metadata_path),
        "log": str(schedule.log_path),
    }


def daily_brokerage_schedule_status(
    *,
    label: str | None = None,
    task_name: str | None = None,
    launch_dir: Path | None = None,
) -> dict[str, Any]:
    schedule = default_schedule(label=label, task_name=task_name, launch_dir=launch_dir)
    if sys.platform == "win32":
        return windows_schedule_status(schedule)
    return macos_schedule_status(schedule)


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))
