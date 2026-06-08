"""Compare multiple reviewer submissions for the same poem."""

from __future__ import annotations

from typing import Any, Dict, List

APPROVE_STATUSES = {"approved"}
NEEDS_EDIT_STATUSES = {"approved_with_corrections", "needs_major_revision"}
REJECT_STATUSES = {"rejected"}


def status_display_label(status: str) -> str:
    labels = {
        "approved": "Approve",
        "approved_with_corrections": "Approved with corrections",
        "needs_major_revision": "Needs Edit",
        "rejected": "Rejected",
        "draft": "Draft (in progress)",
    }
    return labels.get(str(status or "").strip(), str(status or "unknown").replace("_", " ").title())


def _status_category(status: str) -> str:
    status = str(status or "").strip()
    if status in APPROVE_STATUSES:
        return "approve"
    if status in NEEDS_EDIT_STATUSES:
        return "needs_edit"
    if status in REJECT_STATUSES:
        return "reject"
    if status == "draft":
        return "draft"
    return status or "unknown"


def compute_agreement(reviews: List[Dict[str, Any]]) -> str:
    """Return HIGH, MEDIUM, LOW, or N/A."""
    submitted = [
        r for r in reviews
        if str(r.get("review_status") or "").strip() not in {"", "draft"}
        and not r.get("is_draft")
    ]
    if len(submitted) < 2:
        return "N/A"

    categories = {_status_category(str(r.get("review_status") or "")) for r in submitted}
    categories.discard("draft")
    if len(categories) <= 1:
        return "HIGH"
    if "approve" in categories and ("needs_edit" in categories or "reject" in categories):
        return "LOW"
    return "MEDIUM"


def agreement_badge_kind(agreement: str) -> str:
    agreement = (agreement or "").upper()
    if agreement == "HIGH":
        return "green"
    if agreement == "MEDIUM":
        return "yellow"
    if agreement == "LOW":
        return "red"
    return "gray"


def reviews_for_poem(reviews: List[Dict[str, Any]], poem_id: str) -> List[Dict[str, Any]]:
    return [
        r for r in reviews
        if str(r.get("poem_id") or "") == str(poem_id)
        and str(r.get("review_status") or "") != "draft"
        and not r.get("is_draft")
    ]


def comparison_rows(reviews: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for review in reviews:
        reviewer = str(review.get("logged_in_user") or review.get("reviewer_id") or "unknown")
        status = str(review.get("review_status") or "")
        decision = review.get("reviewer_decision", {}) or {}
        rows.append(
            {
                "reviewer": reviewer,
                "decision": status_display_label(status),
                "confidence": str(review.get("reviewer_confidence") or ""),
                "reviewed_at": str(review.get("reviewed_at") or ""),
                "comment": str(decision.get("reason") or "")[:120],
            }
        )
    return rows


def poems_with_multiple_reviews(reviews: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    by_poem: Dict[str, List[Dict[str, Any]]] = {}
    for review in reviews:
        if str(review.get("review_status") or "") == "draft" or review.get("is_draft"):
            continue
        poem_id = str(review.get("poem_id") or "")
        if not poem_id:
            continue
        by_poem.setdefault(poem_id, []).append(review)
    return {pid: rs for pid, rs in by_poem.items() if len(rs) >= 2}
