"""Senior review escalation queue."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .io_utils import load_json, now_iso, save_json

ESCALATIONS_DIR = Path("escalations")
ESCALATIONS_FILE = ESCALATIONS_DIR / "pending.json"


def ensure_escalations_dir() -> None:
    ESCALATIONS_DIR.mkdir(exist_ok=True)


def load_escalations() -> Dict[str, Dict[str, Any]]:
    ensure_escalations_dir()
    if not ESCALATIONS_FILE.exists():
        return {}
    try:
        data = load_json(ESCALATIONS_FILE)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_escalations(data: Dict[str, Dict[str, Any]]) -> None:
    ensure_escalations_dir()
    save_json(ESCALATIONS_FILE, data)


def escalate_poem(
    poem_id: str,
    *,
    title: str,
    language: str,
    escalated_by: str,
    agreement: str,
    reviewers: List[str],
) -> Dict[str, Any]:
    data = load_escalations()
    entry = {
        "poem_id": poem_id,
        "title": title,
        "language": language,
        "escalated_at": now_iso(),
        "escalated_by": escalated_by,
        "agreement": agreement,
        "reviewers": sorted(set(reviewers)),
        "status": "pending_senior_review",
        "senior_decision": None,
        "senior_comment": None,
        "resolved_at": None,
        "resolved_by": None,
    }
    data[poem_id] = entry
    save_escalations(data)
    return entry


def resolve_escalation(
    poem_id: str,
    *,
    senior_user: str,
    decision: str,
    comment: str,
) -> Optional[Dict[str, Any]]:
    data = load_escalations()
    entry = data.get(poem_id)
    if not entry:
        return None
    entry["status"] = "resolved"
    entry["senior_decision"] = decision
    entry["senior_comment"] = comment.strip()
    entry["resolved_at"] = now_iso()
    entry["resolved_by"] = senior_user
    data[poem_id] = entry
    save_escalations(data)
    return entry


def get_escalation(poem_id: str) -> Optional[Dict[str, Any]]:
    return load_escalations().get(poem_id)


def pending_escalations() -> List[Dict[str, Any]]:
    return [
        entry for entry in load_escalations().values()
        if str(entry.get("status") or "") == "pending_senior_review"
    ]


def is_escalated(poem_id: str) -> bool:
    entry = get_escalation(poem_id)
    return bool(entry and str(entry.get("status") or "") == "pending_senior_review")
