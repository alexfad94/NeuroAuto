import json
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[3]
FAQ_FILE = ROOT_DIR / "data" / "faq_autosales.json"
ESCALATION_FILE = ROOT_DIR / "data" / "escalation_rules.json"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_faq() -> dict[str, Any]:
    return load_json(FAQ_FILE)


def load_escalation_rules() -> dict[str, Any]:
    return load_json(ESCALATION_FILE)
