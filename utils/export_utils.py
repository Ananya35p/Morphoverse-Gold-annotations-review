"""Export reviewer annotations for admin download."""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pandas as pd

from .admin_resolution_store import load_resolutions
from .review_utils import sanitize_display_title

ANNOTATION_SECTIONS = [
    ("culture_entities", "text"),
    ("metaphor_spans", "source_text"),
    ("stanza_emotions", "stanza_index"),
    ("visual_motifs", "motif"),
]


def _reviewer_name(review: Dict[str, Any]) -> str:
    return str(review.get("logged_in_user") or review.get("reviewer_id") or "unknown")


def reviews_to_json_bytes(reviews: List[Dict[str, Any]]) -> bytes:
    payload = [dict(review) for review in reviews]
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def summary_df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def flatten_annotations(reviews: List[Dict[str, Any]]) -> pd.DataFrame:
    """One row per annotation record across all sections."""
    rows: List[Dict[str, Any]] = []
    for review in reviews:
        if str(review.get("review_status") or "") == "draft" or review.get("is_draft"):
            continue
        base = {
            "poem_id": review.get("poem_id", ""),
            "title": sanitize_display_title(review.get("title", "")),
            "language": review.get("language", ""),
            "reviewer": _reviewer_name(review),
            "review_status": review.get("review_status", ""),
            "reviewer_confidence": review.get("reviewer_confidence", ""),
            "reviewed_at": review.get("reviewed_at", ""),
        }
        final = review.get("final_annotations") or {}
        for section, key_col, section_label in ANNOTATION_SECTIONS:
            for record in final.get(section) or []:
                if not isinstance(record, dict):
                    continue
                row = dict(base)
                row["section"] = section_label
                row["row_key"] = str(record.get(key_col) or "")
                for col, value in record.items():
                    if col.startswith("_"):
                        continue
                    row[col] = value
                rows.append(row)
    return pd.DataFrame(rows)


def annotations_to_csv_bytes(reviews: List[Dict[str, Any]]) -> bytes:
    df = flatten_annotations(reviews)
    if df.empty:
        return "poem_id,title,language,reviewer,section,row_key\n".encode("utf-8")
    return df.to_csv(index=False).encode("utf-8")


def accepted_reviews(reviews: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Reviews accepted by admin; falls back to all non-draft if no resolution."""
    resolutions = load_resolutions()
    accepted: List[Dict[str, Any]] = []
    reviews_by_poem: Dict[str, List[Dict[str, Any]]] = {}
    for review in reviews:
        if str(review.get("review_status") or "") == "draft" or review.get("is_draft"):
            continue
        poem_id = str(review.get("poem_id") or "")
        reviews_by_poem.setdefault(poem_id, []).append(review)

    for poem_id, poem_reviews in reviews_by_poem.items():
        resolution = resolutions.get(poem_id)
        if not resolution or str(resolution.get("status") or "") != "resolved":
            continue
        accepted_name = str(resolution.get("accepted_reviewer") or "")
        match = next(
            (r for r in poem_reviews if _reviewer_name(r) == accepted_name),
            None,
        )
        if match:
            gold = dict(match)
            gold["admin_resolution"] = resolution
            accepted.append(gold)

    return accepted


def gold_annotations_json_bytes(reviews: List[Dict[str, Any]]) -> bytes:
    return reviews_to_json_bytes(accepted_reviews(reviews))


def gold_annotations_csv_bytes(reviews: List[Dict[str, Any]]) -> bytes:
    return annotations_to_csv_bytes(accepted_reviews(reviews))


def filter_reviews_by_poem(reviews: List[Dict[str, Any]], poem_id: str) -> List[Dict[str, Any]]:
    return [r for r in reviews if str(r.get("poem_id") or "") == str(poem_id)]
