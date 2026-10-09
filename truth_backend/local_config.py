"""Read an optional project-local .env without executing or expanding its values."""
from __future__ import annotations

import os
from pathlib import Path


ALLOWED_SETTINGS = {
    "TRUTH_AI_BASE_URL", "TRUTH_AI_MODEL", "TRUTH_AI_API_KEY",
    "DEEPSEEK_API_KEY", "TRUTH_SEARCH_PROVIDER", "TAVILY_API_KEY",
    "BRAVE_API_KEY", "TRUTH_PORT",
}


def load_local_config(root: Path) -> None:
    path = root / ".env"
    if not path.is_file():
        return
    with path.open("rb") as handle:
        raw = handle.read(32_769)
    if len(raw) > 32_768:
        raise ValueError(".env exceeds 32 KB / 本机配置超过 32 KB / 設定が 32 KB を超えています")
    settings = {}
    for number, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or key not in ALLOWED_SETTINGS:
            raise ValueError(f"Invalid .env line / 本机配置行无效 / 無効な設定行: {number}")
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f"Invalid .env quote / 本机配置引号无效 / 無効な引用符: {number}")
            value = value[1:-1]
        settings[key] = value
    for key, value in settings.items():
        os.environ.setdefault(key, value)
