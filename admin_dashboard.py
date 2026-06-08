from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from utils.auth_utils import admin_logout, init_admin_state, require_admin_login
from utils.io_utils import load_json, make_review_zip
from utils.reviewer_store import load_all_reviewer_submissions, SUBMISSIONS_DIR
from utils.storage_utils import load_reviews_from_persistent_storage, persistent_storage_label


st.set_page_config(
    page_title="MorphoVerse++ Review Admin",
    page_icon="MV",
    layout="wide",
    initial_sidebar_state="expanded",
)


CUSTOM_CSS = """
<style>
.block-container { padding-top: 1.15rem; padding-bottom: 2rem; }
.admin-card {
    border: 1px solid #d1d5db;
    border-radius: 8px;
    padding: 1rem;
    background: #ffffff;
    margin-bottom: 1rem;
}
.poem-box {
    white-space: pre-wrap;
    line-height: 1.75;
    font-size: 1rem;
    padding: 1rem;
    border-radius: 8px;
    border: 1px solid #d1d5db;
    background: #fffdf7;
    max-height: 360px;
    overflow-y: auto;
}
.small-muted { color: #4b5563; font-size: 0.88rem; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def load_legacy_reviews() -> List[Dict[str, Any]]:
    reviews: List[Dict[str, Any]] = []
    root = Path("reviewed_outputs")
    if not root.exists():
        return reviews
    paths = list(root.glob("*/*_reviewed.json"))
    paths.extend(root.glob("*/*/*_reviewed.json"))
    for path in sorted(paths):
        try:
            payload = load_json(path)
        except Exception:
            continue
        payload["_review_file"] = str(path)
        payload["_storage_source"] = "Legacy local"
        reviews.append(payload)
    return reviews


def load_all_reviews() -> tuple[List[Dict[str, Any]], str]:
    reviewer_reviews = load_all_reviewer_submissions()
    legacy_reviews = load_legacy_reviews()
    remote_reviews, remote_message = load_reviews_from_persistent_storage()

    reviews_by_id: Dict[str, Dict[str, Any]] = {}
    for review in reviewer_reviews + legacy_reviews + remote_reviews:
        user = str(review.get("logged_in_user") or review.get("reviewer_id") or "unknown")
        poem_id = str(review.get("poem_id") or "")
        key = str(review.get("review_id") or f"{user}__{poem_id}")
        if key not in reviews_by_id or review.get("_storage_source") == "Reviewer store":
            reviews_by_id[key] = review

    return list(reviews_by_id.values()), remote_message


def review_summary_df(reviews: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for review in reviews:
        decision = review.get("reviewer_decision", {}) or {}
        annotations = review.get("final_annotations", {}) or {}
        rows.append(
            {
                "reviewer": review.get("logged_in_user") or review.get("reviewer_id", ""),
                "poem_id": review.get("poem_id", ""),
                "language": review.get("language", ""),
                "title": review.get("title", ""),
                "status": review.get("review_status", ""),
                "confidence": review.get("reviewer_confidence", ""),
                "reviewed_at": review.get("reviewed_at", ""),
                "comment": decision.get("reason", ""),
                "source": review.get("_storage_source", "Local"),
                "culture_rows": len(annotations.get("culture_entities", []) or []),
                "metaphor_rows": len(annotations.get("metaphor_spans", []) or []),
                "emotion_rows": len(annotations.get("stanza_emotions", []) or []),
                "motif_rows": len(annotations.get("visual_motifs", []) or []),
            }
        )
    return pd.DataFrame(rows)


def records_df(records: List[Dict[str, Any]]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records).fillna("")


def render_review(review: Dict[str, Any]) -> None:
    decision = review.get("reviewer_decision", {}) or {}
    annotations = review.get("final_annotations", {}) or {}
    changes = review.get("review_changes", {}) or {}
    reviewer = review.get("logged_in_user") or review.get("reviewer_id", "unknown")

    st.markdown(
        f"""
        <div class="admin-card">
            <strong>Reviewer: {reviewer}</strong><br>
            <span class="small-muted">
                Status: {review.get("review_status", "")} |
                Confidence: {review.get("reviewer_confidence", "")} |
                Source: {review.get("_storage_source", "Local")} |
                Reviewed at: {review.get("reviewed_at", "")}
            </span>
            <p>{decision.get("reason", "") or "No final comment."}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Original poem")
        st.markdown(f'<div class="poem-box">{review.get("original_poem", "")}</div>', unsafe_allow_html=True)
    with c2:
        st.markdown("#### English translation")
        st.markdown(f'<div class="poem-box">{review.get("english_translation", "")}</div>', unsafe_allow_html=True)

    with st.expander("Culture entities", expanded=True):
        st.dataframe(records_df(annotations.get("culture_entities", []) or []), use_container_width=True, hide_index=True)
    with st.expander("Metaphors", expanded=False):
        st.dataframe(records_df(annotations.get("metaphor_spans", []) or []), use_container_width=True, hide_index=True)
    with st.expander("Stanza emotions", expanded=False):
        st.dataframe(records_df(annotations.get("stanza_emotions", []) or []), use_container_width=True, hide_index=True)
    with st.expander("Visual motifs", expanded=False):
        st.dataframe(records_df(annotations.get("visual_motifs", []) or []), use_container_width=True, hide_index=True)

    with st.expander("Changes made by reviewer", expanded=True):
        st.markdown("#### Culture entities")
        st.dataframe(records_df(changes.get("culture_entities", []) or []), use_container_width=True, hide_index=True)
        st.markdown("#### Metaphors")
        st.dataframe(records_df(changes.get("metaphor_spans", []) or []), use_container_width=True, hide_index=True)
        st.markdown("#### Stanza emotions")
        st.dataframe(records_df(changes.get("stanza_emotions", []) or []), use_container_width=True, hide_index=True)
        st.markdown("#### Visual motifs")
        st.dataframe(records_df(changes.get("visual_motifs", []) or []), use_container_width=True, hide_index=True)


init_admin_state()
admin_user = require_admin_login()

reviews, storage_message = load_all_reviews()
summary_df = review_summary_df(reviews)

st.title("MorphoVerse++ Review Admin")
st.caption(f"Signed in as admin: **{admin_user}**")
st.caption(f"Reviewer submissions folder: `{SUBMISSIONS_DIR}`")

if storage_message:
    st.info(storage_message)

if not reviews:
    st.warning("No reviewer submissions found yet.")
    st.info("Submissions appear here when reviewers submit poems from the main app.")
    if st.button("Sign out"):
        admin_logout()
        st.rerun()
    st.stop()

with st.sidebar:
    st.header("Admin")
    if st.button("Sign out", use_container_width=True):
        admin_logout()
        st.rerun()

    st.divider()
    reviewers = ["All"] + sorted(summary_df["reviewer"].dropna().astype(str).unique().tolist())
    selected_reviewer = st.selectbox("Reviewer", reviewers)

    languages = ["All"] + sorted(summary_df["language"].dropna().astype(str).unique().tolist())
    selected_language = st.selectbox("Language", languages)

    filtered = summary_df.copy()
    if selected_reviewer != "All":
        filtered = filtered[filtered["reviewer"] == selected_reviewer]
    if selected_language != "All":
        filtered = filtered[filtered["language"] == selected_language]

    poem_labels = [
        f"{row.poem_id} | {row.title} | {row.language}"
        for row in filtered[["poem_id", "title", "language"]].drop_duplicates().itertuples(index=False)
    ]
    selected_poem_label = st.selectbox("Poem", poem_labels) if poem_labels else None
    selected_poem_id = selected_poem_label.split(" | ", 1)[0] if selected_poem_label else None

    st.divider()
    zip_path = make_review_zip()
    if zip_path and zip_path.exists():
        with zip_path.open("rb") as f:
            st.download_button(
                "Download legacy reviewed JSON",
                data=f,
                file_name="reviewed_outputs.zip",
                mime="application/zip",
                use_container_width=True,
            )

st.subheader("Overview")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Reviewers", summary_df["reviewer"].nunique())
m2.metric("Poems reviewed", summary_df["poem_id"].nunique())
m3.metric("Total submissions", len(summary_df))
m4.metric("Languages", summary_df["language"].nunique())

st.markdown("### All submissions")
st.dataframe(
    filtered.sort_values(["reviewer", "language", "poem_id"]),
    use_container_width=True,
    hide_index=True,
)

if selected_poem_id:
    poem_reviews = [r for r in reviews if str(r.get("poem_id")) == selected_poem_id]
    poem_reviews = sorted(poem_reviews, key=lambda r: str(r.get("logged_in_user") or r.get("reviewer_id", "")))

    st.markdown("### Selected poem reviews")
    for review in poem_reviews:
        reviewer = review.get("logged_in_user") or review.get("reviewer_id", "unknown")
        with st.expander(f"{reviewer} — {review.get('review_status', '')}", expanded=len(poem_reviews) == 1):
            render_review(review)
