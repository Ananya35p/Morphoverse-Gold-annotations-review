"""Compare multiple reviewer submissions for the same poem."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

APPROVE_STATUSES = {"approved"}
NEEDS_EDIT_STATUSES = {"approved_with_corrections", "needs_major_revision"}
REJECT_STATUSES = {"rejected"}

ANNOTATION_SECTIONS: List[Tuple[str, str, str]] = [
    ("culture_entities", "text", "Culture"),
    ("metaphor_spans", "source_text", "Metaphors"),
    ("stanza_emotions", "stanza_index", "Emotions"),
    ("visual_motifs", "motif", "Visual motifs"),
]

METADATA_COLS = frozenset({"review_action", "reviewer_comment", "_is_original"})

LEVEL_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "N/A": 0}


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


def _reviewer_name(review: Dict[str, Any]) -> str:
    return str(review.get("logged_in_user") or review.get("reviewer_id") or "unknown")


def _submitted_reviews(reviews: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        r for r in reviews
        if str(r.get("review_status") or "").strip() not in {"", "draft"}
        and not r.get("is_draft")
    ]


def compute_decision_agreement(reviews: List[Dict[str, Any]]) -> str:
    """Agreement on overall review decision only."""
    submitted = _submitted_reviews(reviews)
    if len(submitted) < 2:
        return "N/A"

    categories = {_status_category(str(r.get("review_status") or "")) for r in submitted}
    categories.discard("draft")
    if len(categories) <= 1:
        return "HIGH"
    if "approve" in categories and ("needs_edit" in categories or "reject" in categories):
        return "LOW"
    return "MEDIUM"


def _row_key(record: Dict[str, Any], key_col: str) -> str:
    return str(record.get(key_col) or "").strip()


def _content_fingerprint(record: Dict[str, Any], key_col: str) -> str:
    payload = {}
    for col, value in record.items():
        if col in METADATA_COLS or col == key_col:
            continue
        payload[col] = str(value or "").strip()
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _edit_actions(review: Dict[str, Any], section: str, key_col: str) -> Dict[str, str]:
    changes = (review.get("review_changes") or {}).get(section) or []
    actions: Dict[str, str] = {}
    for row in changes:
        if not isinstance(row, dict):
            continue
        key = _row_key(row, key_col)
        action = str(row.get("review_action") or "").strip()
        if key and action in {"modify", "remove", "add"}:
            actions[key] = action
    return actions


def _final_rows(review: Dict[str, Any], section: str, key_col: str) -> Dict[str, str]:
    rows = (review.get("final_annotations") or {}).get(section) or []
    final: Dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = _row_key(row, key_col)
        if key:
            final[key] = _content_fingerprint(row, key_col)
    return final


def _pair_annotation_conflicts(
    review_a: Dict[str, Any],
    review_b: Dict[str, Any],
) -> Tuple[List[Dict[str, str]], Dict[str, int]]:
    conflicts: List[Dict[str, str]] = []
    stats = {
        "rows_compared": 0,
        "action_conflicts": 0,
        "content_conflicts": 0,
        "presence_conflicts": 0,
        "divergent_sections": 0,
    }
    name_a = _reviewer_name(review_a)
    name_b = _reviewer_name(review_b)

    for section, key_col, section_label in ANNOTATION_SECTIONS:
        actions_a = _edit_actions(review_a, section, key_col)
        actions_b = _edit_actions(review_b, section, key_col)
        final_a = _final_rows(review_a, section, key_col)
        final_b = _final_rows(review_b, section, key_col)

        if actions_a and actions_b and not (set(actions_a) & set(actions_b)):
            stats["divergent_sections"] += 1
            conflicts.append(
                {
                    "section": section_label,
                    "row": "(section)",
                    "type": "divergent_edits",
                    "reviewer_a": name_a,
                    "detail_a": f"{len(actions_a)} edit(s)",
                    "reviewer_b": name_b,
                    "detail_b": f"{len(actions_b)} edit(s) on different rows",
                }
            )

        for key in sorted(set(actions_a) | set(actions_b)):
            action_a = actions_a.get(key, "keep")
            action_b = actions_b.get(key, "keep")
            if action_a != action_b and not (action_a == "keep" and action_b == "keep"):
                stats["rows_compared"] += 1
                stats["action_conflicts"] += 1
                conflicts.append(
                    {
                        "section": section_label,
                        "row": key[:80],
                        "type": "action_mismatch",
                        "reviewer_a": name_a,
                        "detail_a": action_a,
                        "reviewer_b": name_b,
                        "detail_b": action_b,
                    }
                )

        for key in sorted(set(final_a) | set(final_b)):
            in_a = key in final_a
            in_b = key in final_b
            if in_a and in_b:
                stats["rows_compared"] += 1
                if final_a[key] != final_b[key]:
                    stats["content_conflicts"] += 1
                    conflicts.append(
                        {
                            "section": section_label,
                            "row": key[:80],
                            "type": "content_mismatch",
                            "reviewer_a": name_a,
                            "detail_a": "different final values",
                            "reviewer_b": name_b,
                            "detail_b": "different final values",
                        }
                    )
            elif in_a != in_b:
                stats["rows_compared"] += 1
                stats["presence_conflicts"] += 1
                conflicts.append(
                    {
                        "section": section_label,
                        "row": key[:80],
                        "type": "presence_mismatch",
                        "reviewer_a": name_a,
                        "detail_a": "present" if in_a else "absent",
                        "reviewer_b": name_b,
                        "detail_b": "present" if in_b else "absent",
                    }
                )

    return conflicts, stats


def compute_annotation_agreement(reviews: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, str]], Dict[str, int]]:
    """Agreement on actual annotation edits (row actions + final content)."""
    submitted = _submitted_reviews(reviews)
    if len(submitted) < 2:
        return "N/A", [], {}

    all_conflicts: List[Dict[str, str]] = []
    totals = {
        "rows_compared": 0,
        "action_conflicts": 0,
        "content_conflicts": 0,
        "presence_conflicts": 0,
        "divergent_sections": 0,
    }

    for i in range(len(submitted)):
        for j in range(i + 1, len(submitted)):
            pair_conflicts, pair_stats = _pair_annotation_conflicts(submitted[i], submitted[j])
            all_conflicts.extend(pair_conflicts)
            for key in totals:
                totals[key] += pair_stats.get(key, 0)

    # Deduplicate identical conflict rows for display
    seen = set()
    unique_conflicts: List[Dict[str, str]] = []
    for conflict in all_conflicts:
        sig = tuple(conflict.get(k, "") for k in ("section", "row", "type", "reviewer_a", "detail_a", "reviewer_b", "detail_b"))
        if sig not in seen:
            seen.add(sig)
            unique_conflicts.append(conflict)

    conflict_count = (
        totals["action_conflicts"]
        + totals["content_conflicts"]
        + totals["presence_conflicts"]
        + totals["divergent_sections"]
    )

    if conflict_count == 0:
        return "HIGH", unique_conflicts, totals
    if totals["action_conflicts"] > 0 or totals["presence_conflicts"] > 0:
        return "LOW", unique_conflicts, totals
    if totals["divergent_sections"] > 0 or totals["content_conflicts"] > 0:
        return "MEDIUM", unique_conflicts, totals
    return "MEDIUM", unique_conflicts, totals


def _lowest_level(*levels: str) -> str:
    valid = [level for level in levels if level in LEVEL_RANK]
    if not valid:
        return "N/A"
    return min(valid, key=lambda level: LEVEL_RANK[level])


def compute_agreement_report(reviews: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Full agreement report: decision + annotation + combined."""
    decision = compute_decision_agreement(reviews)
    annotation, conflicts, stats = compute_annotation_agreement(reviews)
    combined = _lowest_level(decision, annotation)
    return {
        "decision": decision,
        "annotation": annotation,
        "combined": combined,
        "conflicts": conflicts,
        "stats": stats,
    }


def compute_agreement(reviews: List[Dict[str, Any]]) -> str:
    """Combined agreement (decision AND annotation). Backward-compatible."""
    return compute_agreement_report(reviews)["combined"]


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
        reviewer = _reviewer_name(review)
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
