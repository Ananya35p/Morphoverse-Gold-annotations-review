"""Review event history for drafts and submissions."""

from __future__ import annotations

from typing import Any, Dict, List

from .io_utils import now_iso


def append_history_event(
    payload: Dict[str, Any],
    event: str,
    *,
    note: str = "",
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    history: List[Dict[str, Any]] = list(payload.get("history") or [])
    entry: Dict[str, Any] = {
        "event": event,
        "at": now_iso(),
        "review_status": payload.get("review_status"),
        "reviewer_confidence": payload.get("reviewer_confidence"),
    }
    if note:
        entry["note"] = note
    if extra:
        entry.update(extra)
    history.append(entry)
    payload["history"] = history[-50:]
    return payload


def history_event_label(event: str) -> str:
    labels = {
        "draft_saved": "Draft auto-saved",
        "submitted": "Review submitted",
        "updated": "Review updated",
        "escalated": "Escalated to senior reviewer",
        "senior_resolved": "Senior review completed",
    }
    return labels.get(event, event.replace("_", " ").title())


def format_history_table(history: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for item in reversed(history or []):
        rows.append(
            {
                "When": str(item.get("at") or ""),
                "Event": history_event_label(str(item.get("event") or "")),
                "Status": str(item.get("review_status") or ""),
                "Note": str(item.get("note") or ""),
            }
        )
    return rows
