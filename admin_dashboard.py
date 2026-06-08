from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from utils.auth_utils import admin_logout, get_admin_role, init_admin_state, require_admin_login
from utils.comparison_utils import (
    comparison_rows,
    compute_agreement,
    poems_with_multiple_reviews,
    reviews_for_poem,
)
from utils.display_utils import (
    build_poem_option_map,
    comparison_option_label,
    submissions_display_df,
)
from utils.review_utils import sanitize_display_title
from utils.display_prefs import get_display_css, init_display_prefs, render_display_controls
from utils.escalation_store import escalate_poem, get_escalation, pending_escalations, resolve_escalation
from utils.io_utils import load_json, make_review_zip
from utils.review_history import format_history_table
from utils.reviewer_store import load_all_reviewer_submissions, SUBMISSIONS_DIR
from utils.schema_utils import REVIEW_DECISIONS
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
.compare-panel {
    border: 2px solid #dbeafe;
    border-radius: 12px;
    padding: 1.1rem 1.25rem;
    background: linear-gradient(135deg, #f8fafc 0%, #eff6ff 100%);
    margin: 1rem 0 1.25rem 0;
}
.compare-row {
    padding: 0.55rem 0;
    border-bottom: 1px solid #e5e7eb;
    font-size: 1rem;
}
.compare-row:last-child { border-bottom: none; }
.agreement-high { color: #176b3a; font-weight: 700; }
.agreement-medium { color: #7a5200; font-weight: 700; }
.agreement-low { color: #9d1c1c; font-weight: 700; }
.agreement-na { color: #4b5563; font-weight: 700; }
.escalation-card {
    border: 1px solid #fcd34d;
    border-radius: 10px;
    padding: 1rem;
    background: #fffbeb;
    margin-bottom: 0.75rem;
}
</style>
"""
init_display_prefs()
st.markdown(CUSTOM_CSS + get_display_css(), unsafe_allow_html=True)


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
                "title": sanitize_display_title(review.get("title", "")),
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


def agreement_css_class(agreement: str) -> str:
    return {
        "HIGH": "agreement-high",
        "MEDIUM": "agreement-medium",
        "LOW": "agreement-low",
    }.get((agreement or "").upper(), "agreement-na")


def render_comparison_panel(
    poem_reviews: List[Dict[str, Any]],
    poem_id: str,
    title: str,
    language: str,
    staff_user: str,
    staff_role: str,
) -> None:
    agreement = compute_agreement(poem_reviews)
    rows = comparison_rows(poem_reviews)
    compare_lines = "".join(
        f'<div class="compare-row"><strong>{row["reviewer"]}</strong> &rarr; {row["decision"]}</div>'
        for row in rows
    )
    st.markdown(
        f"""
        <div class="compare-panel">
            <div class="section-header" style="margin-top:0;">Review comparison</div>
            {compare_lines}
            <div class="compare-row">
                <span class="{agreement_css_class(agreement)}">Agreement: {agreement}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if len(poem_reviews) < 2:
        st.caption("Comparison appears when two or more reviewers submit the same poem.")
        return

    escalation = get_escalation(poem_id)
    if escalation and str(escalation.get("status")) == "pending_senior_review":
        st.warning(
            f"Escalated on {escalation.get('escalated_at', '')} by **{escalation.get('escalated_by', 'admin')}**. "
            "Awaiting senior review."
        )
    elif staff_role == "admin" and agreement == "LOW":
        reviewers = [str(r.get("logged_in_user") or r.get("reviewer_id") or "") for r in poem_reviews]
        if st.button("Escalate to Senior Reviewer", type="primary", key=f"escalate_{poem_id}"):
            escalate_poem(
                poem_id,
                title=title,
                language=language,
                escalated_by=staff_user,
                agreement=agreement,
                reviewers=reviewers,
            )
            st.success(f"Escalated **{title}** to the senior review queue.")
            st.rerun()


def render_senior_review_queue(staff_user: str, staff_role: str) -> None:
    pending = pending_escalations()
    if not pending:
        return

    st.markdown("### Senior review queue")
    for entry in pending:
        poem_id = str(entry.get("poem_id") or "")
        with st.container():
            st.markdown(
                f"""
                <div class="escalation-card">
                    <strong>{entry.get("title", "Untitled poem")}</strong>
                    <span class="small-muted"> &middot; {entry.get("language", "")}</span><br>
                    <span class="small-muted">
                        Agreement: {entry.get("agreement", "")} &middot;
                        Reviewers: {", ".join(entry.get("reviewers") or [])} &middot;
                        Escalated by {entry.get("escalated_by", "")}
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if staff_role not in {"admin", "senior"}:
                continue
            with st.form(key=f"senior_resolve_{poem_id}"):
                decision = st.selectbox("Final senior decision", REVIEW_DECISIONS, key=f"senior_dec_{poem_id}")
                comment = st.text_area("Senior reviewer comment", key=f"senior_comment_{poem_id}", height=100)
                if st.form_submit_button("Submit senior decision", type="primary"):
                    if not comment.strip():
                        st.error("Please add a senior reviewer comment.")
                    else:
                        resolve_escalation(
                            poem_id,
                            senior_user=staff_user,
                            decision=decision,
                            comment=comment,
                        )
                        st.success(f"Senior review completed for **{entry.get('title', 'poem')}**.")
                        st.rerun()
    st.divider()


def render_review_history(review: Dict[str, Any]) -> None:
    history = review.get("history") or []
    if not history:
        st.caption("No history recorded for this review yet.")
        return
    st.dataframe(
        pd.DataFrame(format_history_table(history)),
        use_container_width=True,
        hide_index=True,
    )


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

    with st.expander("Review history", expanded=False):
        render_review_history(review)


init_admin_state()
admin_user = require_admin_login()
staff_role = get_admin_role()

reviews, storage_message = load_all_reviews()
summary_df = review_summary_df(reviews)
multi_review_poems = poems_with_multiple_reviews(reviews)

st.title("MorphoVerse++ Review Admin")
st.caption(f"Signed in as **{staff_role}**: **{admin_user}**")
st.caption(f"Reviewer submissions folder: `{SUBMISSIONS_DIR}` · Storage: {persistent_storage_label()}")

if storage_message and "not configured" in storage_message.lower():
    st.info(
        f"{storage_message} Add Supabase secrets and run `supabase/schema.sql` so every reviewer's "
        "submission is stored permanently (multiple reviewers per poem supported)."
    )
elif storage_message:
    st.success(storage_message)

if not reviews:
    st.warning("No reviewer submissions found yet.")
    st.info("Submissions appear here when reviewers submit poems from the main app.")
    if st.button("Sign out"):
        admin_logout()
        st.rerun()
    st.stop()

with st.sidebar:
    st.header("Admin")
    render_display_controls()
    st.divider()
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

    poem_option_map = build_poem_option_map(filtered)
    poem_labels = list(poem_option_map.keys())
    selected_poem_label = st.selectbox("Poem", poem_labels) if poem_labels else None
    selected_poem_id = poem_option_map.get(selected_poem_label or "", None)

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

render_senior_review_queue(admin_user, staff_role)

st.subheader("Overview")
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Reviewers", summary_df["reviewer"].nunique())
m2.metric("Poems reviewed", summary_df["poem_id"].nunique())
m3.metric("Total submissions", len(summary_df))
m4.metric("Multi-review poems", len(multi_review_poems))
m5.metric("Pending escalations", len(pending_escalations()))

if multi_review_poems:
    st.markdown("### Poems needing comparison")
    compare_option_map = {
        comparison_option_label(revs, compute_agreement(revs)): pid
        for pid, revs in sorted(
            multi_review_poems.items(),
            key=lambda item: compute_agreement(item[1]),
        )
    }
    compare_labels = list(compare_option_map.keys())
    quick_compare = st.selectbox("Jump to comparison", compare_labels, key="quick_compare")
    if quick_compare:
        quick_poem_id = compare_option_map.get(quick_compare, "")
        quick_reviews = reviews_for_poem(reviews, quick_poem_id)
        if quick_reviews:
            first = quick_reviews[0]
            render_comparison_panel(
                quick_reviews,
                quick_poem_id,
                str(first.get("title") or ""),
                str(first.get("language") or ""),
                admin_user,
                staff_role,
            )

st.markdown("### All submissions")
st.dataframe(
    submissions_display_df(filtered),
    use_container_width=True,
    hide_index=True,
)

if selected_poem_id:
    poem_reviews = reviews_for_poem(reviews, selected_poem_id)
    poem_reviews = sorted(poem_reviews, key=lambda r: str(r.get("logged_in_user") or r.get("reviewer_id", "")))

    if poem_reviews:
        first = poem_reviews[0]
        render_comparison_panel(
            poem_reviews,
            selected_poem_id,
            str(first.get("title") or ""),
            str(first.get("language") or ""),
            admin_user,
            staff_role,
        )

    poem_title = (
        sanitize_display_title(poem_reviews[0].get("title", ""))
        if poem_reviews
        else "Untitled poem"
    )
    st.markdown(f"### Selected poem reviews — {poem_title}")
    for review in poem_reviews:
        reviewer = review.get("logged_in_user") or review.get("reviewer_id", "unknown")
        with st.expander(f"{reviewer} — {review.get('review_status', '')}", expanded=len(poem_reviews) == 1):
            render_review(review)
