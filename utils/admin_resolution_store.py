"""Admin final decisions for multi-reviewer poem conflicts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .io_utils import load_json, now_iso, save_json

RESOLUTIONS_DIR = Path("admin_resolutions")
RESOLUTIONS_FILE = RESOLUTIONS_DIR / "resolutions.json"


def ensure_resolutions_dir() -> None:
    RESOLUTIONS_DIR.mkdir(exist_ok=True)


def load_resolutions() -> Dict[str, Dict[str, Any]]:
    ensure_resolutions_dir()
    if not RESOLUTIONS_FILE.exists():
        return {}
    try:
        data = load_json(RESOLUTIONS_FILE)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_resolutions(data: Dict[str, Dict[str, Any]]) -> None:
    ensure_resolutions_dir()
    save_json(RESOLUTIONS_FILE, data)


def get_resolution(poem_id: str) -> Optional[Dict[str, Any]]:
    return load_resolutions().get(poem_id)


def is_resolved(poem_id: str) -> bool:
    entry = get_resolution(poem_id)
    return bool(entry and str(entry.get("status") or "") in {"resolved", "disputed"})


def save_admin_resolution(
    poem_id: str,
    *,
    title: str,
    language: str,
    admin_user: str,
    reviewers: List[str],
    combined_agreement: str,
    decision_agreement: str,
    annotation_agreement: str,
    status: str,
    accepted_reviewer: str = "",
    accepted_review_id: str = "",
    admin_comment: str,
) -> Dict[str, Any]:
    data = load_resolutions()
    entry = {
        "poem_id": poem_id,
        "title": title,
        "language": language,
        "status": status,
        "combined_agreement": combined_agreement,
        "decision_agreement": decision_agreement,
        "annotation_agreement": annotation_agreement,
        "resolved_at": now_iso(),
        "resolved_by": admin_user,
        "admin_comment": admin_comment.strip(),
        "accepted_reviewer": accepted_reviewer.strip(),
        "accepted_review_id": accepted_review_id.strip(),
        "reviewers_involved": sorted(set(reviewers)),
    }
    data[poem_id] = entry
    save_resolutions(data)
    return entry


def pending_conflict_resolutions(
    multi_review_poems: Dict[str, List[Dict[str, Any]]],
    agreement_fn,
) -> List[Dict[str, Any]]:
    """Poems with reviewer conflicts that admin has not finalized yet."""
    pending: List[Dict[str, Any]] = []
    for poem_id, reviews in multi_review_poems.items():
        if is_resolved(poem_id):
            continue
        report = agreement_fn(reviews)
        if report.get("combined") != "HIGH":
            first = reviews[0] if reviews else {}
            pending.append(
                {
                    "poem_id": poem_id,
                    "title": first.get("title", "Untitled poem"),
                    "language": first.get("language", ""),
                    "combined_agreement": report.get("combined", ""),
                    "reviewers": [
                        str(r.get("logged_in_user") or r.get("reviewer_id") or "")
                        for r in reviews
                    ],
                }
            )
    return pending


def all_resolutions() -> List[Dict[str, Any]]:
    return list(load_resolutions().values())
