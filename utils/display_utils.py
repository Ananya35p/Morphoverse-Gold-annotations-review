"""UI helpers that hide internal poem identifiers."""

from __future__ import annotations

from typing import Any, Callable, Dict, List

import pandas as pd

from .review_utils import poem_display_label, sanitize_display_title

ADMIN_SUBMISSION_COLUMNS = [
    "reviewer",
    "title",
    "language",
    "status",
    "confidence",
    "reviewed_at",
    "comment",
    "source",
]

ADMIN_SUBMISSION_HEADERS = {
    "title": "Poem",
    "reviewer": "Reviewer",
    "language": "Language",
    "status": "Status",
    "confidence": "Confidence",
    "reviewed_at": "Reviewed at",
    "comment": "Comment",
    "source": "Source",
}


def _unique_label(base_label: str, poem_id: str, options: Dict[str, str]) -> str:
    label = base_label
    suffix = 2
    while label in options and options[label] != poem_id:
        label = f"{base_label} ({suffix})"
        suffix += 1
    return label


def build_poem_option_map(rows: pd.DataFrame) -> Dict[str, str]:
    """Map poem names to internal poem_id values."""
    options: Dict[str, str] = {}
    if rows.empty:
        return options

    for row in rows[["poem_id", "title"]].drop_duplicates().itertuples(index=False):
        base_label = poem_display_label(str(row.title or ""))
        label = _unique_label(base_label, str(row.poem_id), options)
        options[label] = str(row.poem_id)
    return options


def build_reviewer_poem_options(
    poems: List[dict],
    get_poem_id_fn: Callable[[dict], str],
    get_title_fn: Callable[[dict], str],
) -> Dict[str, str]:
    """Map poem names to internal poem_id values for the reviewer sidebar."""
    options: Dict[str, str] = {}
    for raw in poems:
        poem_id = str(get_poem_id_fn(raw))
        title = get_title_fn(raw)
        base_label = title if len(title) <= 50 else f"{title[:47]}..."
        label = _unique_label(base_label, poem_id, options)
        options[label] = poem_id
    return options


def submissions_display_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    columns = [col for col in ADMIN_SUBMISSION_COLUMNS if col in df.columns]
    display = df[columns].copy()
    if "title" in display.columns:
        display["title"] = display["title"].map(lambda value: sanitize_display_title(value))
    display = display.sort_values(
        [col for col in ["reviewer", "language", "title"] if col in display.columns]
    )
    return display.rename(columns=ADMIN_SUBMISSION_HEADERS)


def comparison_option_label(reviews: List[dict], agreement: str) -> str:
    first = reviews[0] if reviews else {}
    title = poem_display_label(str(first.get("title") or ""))
    return f"{title} — Agreement: {agreement}"
