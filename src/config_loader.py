from __future__ import annotations
from pathlib import Path
import yaml

def load_config(config_path: str) -> dict:
    p = Path(config_path)
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    return yaml.safe_load(p.read_text(encoding="utf-8"))
