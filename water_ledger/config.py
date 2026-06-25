from __future__ import annotations

import json
from typing import Any

from water_ledger.paths import CONFIG_PATH, ROOT


PACKAGE_CONFIG = ROOT / "water_ledger" / "resources" / "config.example.yaml"


def load_config() -> dict[str, Any]:
    repo_config = ROOT / "config" / "config.example.yaml"
    path = CONFIG_PATH if CONFIG_PATH.exists() else repo_config
    if not path.exists():
        path = PACKAGE_CONFIG
    if not path.exists():
        return {}
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise SystemExit(f"Invalid config root in {path}: expected a mapping")
        return data
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit("Missing dependency: PyYAML. Install with `pip install -r requirements.txt`.") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"Invalid config root in {path}: expected a mapping")
    return data


CONFIG = load_config()


def config_section(name: str) -> dict[str, Any]:
    value = CONFIG.get(name) or {}
    return value if isinstance(value, dict) else {}


def profile_config() -> dict[str, Any]:
    return config_section("profile")


def ledger_title() -> str:
    profile = profile_config()
    title = str(profile.get("ledger_title") or "").strip()
    if title:
        return title
    display_name = str(profile.get("display_name") or "").strip() or "我的"
    if display_name.endswith("的个人资产账本"):
        return display_name
    return f"{display_name}的个人资产账本"


def account_mapping() -> dict[str, Any]:
    return config_section("account_mapping")


def private_rules() -> dict[str, Any]:
    return config_section("private_rules")


def classification_config() -> dict[str, Any]:
    return config_section("classification")


def config_list(section: str, default: list[Any] | None = None) -> list[Any]:
    value = CONFIG.get(section)
    return value if isinstance(value, list) else (default or [])


def keyword_list(value: Any) -> list[str]:
    from water_ledger.core.utils import norm_text

    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [norm_text(item) for item in value if norm_text(item)]


def mapping_account(key: str, default: str) -> str:
    from water_ledger.core.utils import norm_text

    return norm_text(account_mapping().get(key)) or default
