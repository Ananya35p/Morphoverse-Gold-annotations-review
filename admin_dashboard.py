from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from utils.admin_resolution_store import (
    get_resolution,
    pending_conflict_resolutions,
    save_admin_resolution,
)
from utils.auth_utils import admin_logout, init_admin_state, require_admin_login
from utils.comparison_utils import (
    comparison_rows,
    compute_agreement_report,
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
from utils.export_utils import (
    annotations_to_csv_bytes,
    filter_reviews_by_poem,
    gold_annotations_csv_bytes,
    gold_annotations_json_bytes,
    reviews_to_json_bytes,
    summary_df_to_csv_bytes,
)
from utils.io_utils import load_json, make_review_zip
from utils.review_history import format_history_table
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
.resolution-card {
    border: 1px solid #fcd34d;
    border-radius: 10px;
    padding: 1rem;
    background: #fffbeb;
    margin-bottom: 0.75rem;
}
.resolution-done {
    border: 1px solid #86efac;
    border-radius: 10px;
    padding: 1rem;
    background: #f0fdf4;
    margin: 1rem 0;
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
    for review in reviewer_reviews + legacy_reviews:
        user = str(review.get("logged_in_user") or review.get("reviewer_id") or "unknown")
        poem_id = str(review.get("poem_id") or "")
        key = str(review.get("review_id") or f"{user}__{poem_id}")
        reviews_by_id[key] = review

    for review in remote_reviews:
        user = str(review.get("logged_in_user") or review.get("reviewer_id") or "unknown")
        poem_id = str(review.get("poem_id") or "")
        key = str(review.get("review_id") or f"{user}__{poem_id}")
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


def _reviewer_label(review: Dict[str, Any]) -> str:
    return str(review.get("logged_in_user") or review.get("reviewer_id") or "unknown")


def render_admin_resolution_panel(
    poem_reviews: List[Dict[str, Any]],
    poem_id: str,
    title: str,
    language: str,
    admin_user: str,
    report: Dict[str, Any],
) -> None:
    resolution = get_resolution(poem_id)
    if resolution:
        status = str(resolution.get("status") or "")
        if status == "disputed":
            st.markdown(
                f"""
                <div class="resolution-card">
                    <strong>Admin decision: Disputed</strong><br>
                    <span class="small-muted">
                        Decided by {resolution.get("resolved_by", "")} on {resolution.get("resolved_at", "")}
                    </span>
                    <p>{resolution.get("admin_comment", "")}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
                <div class="resolution-done">
                    <strong>Admin accepted {resolution.get("accepted_reviewer", "reviewer")}'s submission</strong><br>
                    <span class="small-muted">
                        Decided by {resolution.get("resolved_by", "")} on {resolution.get("resolved_at", "")}
                    </span>
                    <p>{resolution.get("admin_comment", "")}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        return

    if len(poem_reviews) < 2:
        return

    if report.get("combined") == "HIGH":
        st.success("Reviewers agree on decision and annotations. No admin tie-break needed.")
        return

    st.markdown("### Admin final decision")
    st.caption("Choose which review becomes the accepted version, or mark the poem as disputed.")
    reviewer_map = {_reviewer_label(r): r for r in poem_reviews}
    with st.form(key=f"admin_resolve_{poem_id}"):
        resolution_type = st.radio(
            "Resolution",
            ["Accept a reviewer's submission", "Mark as disputed"],
            index=0,
        )
        selected_reviewer_name = st.selectbox(
            "Accept submission from",
            list(reviewer_map.keys()),
            disabled=resolution_type == "Mark as disputed",
        )
        admin_comment = st.text_area(
            "Admin comment (required)",
            height=110,
            placeholder="Explain which review you accepted and why, or why this poem is disputed.",
        )
        if st.form_submit_button("Save admin decision", type="primary", use_container_width=True):
            if not admin_comment.strip():
                st.error("Please add an admin comment.")
            elif resolution_type == "Mark as disputed":
                save_admin_resolution(
                    poem_id,
                    title=title,
                    language=language,
                    admin_user=admin_user,
                    reviewers=[_reviewer_label(r) for r in poem_reviews],
                    combined_agreement=str(report.get("combined") or ""),
                    decision_agreement=str(report.get("decision") or ""),
                    annotation_agreement=str(report.get("annotation") or ""),
                    status="disputed",
                    admin_comment=admin_comment,
                )
                st.success(f"Marked **{title}** as disputed.")
                st.rerun()
            else:
                accepted = reviewer_map[selected_reviewer_name]
                save_admin_resolution(
                    poem_id,
                    title=title,
                    language=language,
                    admin_user=admin_user,
                    reviewers=[_reviewer_label(r) for r in poem_reviews],
                    combined_agreement=str(report.get("combined") or ""),
                    decision_agreement=str(report.get("decision") or ""),
                    annotation_agreement=str(report.get("annotation") or ""),
                    status="resolved",
                    accepted_reviewer=_reviewer_label(accepted),
                    accepted_review_id=str(accepted.get("review_id") or ""),
                    admin_comment=admin_comment,
                )
                st.success(f"Accepted **{_reviewer_label(accepted)}**'s review for **{title}**.")
                st.rerun()


def render_comparison_panel(
    poem_reviews: List[Dict[str, Any]],
    poem_id: str,
    title: str,
    language: str,
    admin_user: str,
) -> None:
    report = compute_agreement_report(poem_reviews)
    combined = report["combined"]
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
                Decision agreement:
                <span class="{agreement_css_class(report["decision"])}">{report["decision"]}</span>
            </div>
            <div class="compare-row">
                Annotation agreement:
                <span class="{agreement_css_class(report["annotation"])}">{report["annotation"]}</span>
            </div>
            <div class="compare-row">
                Combined agreement:
                <span class="{agreement_css_class(combined)}">{combined}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if len(poem_reviews) < 2:
        st.caption("Comparison appears when two or more reviewers submit the same poem.")
        return

    stats = report.get("stats") or {}
    if stats:
        st.caption(
            f"Rows compared: {stats.get('rows_compared', 0)} · "
            f"Action conflicts: {stats.get('action_conflicts', 0)} · "
            f"Content conflicts: {stats.get('content_conflicts', 0)} · "
            f"Presence conflicts: {stats.get('presence_conflicts', 0)}"
        )

    conflicts = report.get("conflicts") or []
    if conflicts:
        st.warning(
            "Reviewers made conflicting annotation edits even though their overall decisions may match."
        )
        conflict_df = pd.DataFrame(
            [
                {
                    "Section": c.get("section", ""),
                    "Row": c.get("row", ""),
                    "Conflict": c.get("type", "").replace("_", " "),
                    "Reviewer A": c.get("reviewer_a", ""),
                    "A detail": c.get("detail_a", ""),
                    "Reviewer B": c.get("reviewer_b", ""),
                    "B detail": c.get("detail_b", ""),
                }
                for c in conflicts
            ]
        )
        st.dataframe(conflict_df, use_container_width=True, hide_index=True)
    elif report["decision"] == "HIGH" and report["annotation"] == "HIGH":
        st.success("Reviewers agree on both overall decision and annotation edits.")

    render_admin_resolution_panel(
        poem_reviews, poem_id, title, language, admin_user, report
    )


def render_pending_admin_decisions(multi_review_poems: Dict[str, List[Dict[str, Any]]]) -> None:
    pending = pending_conflict_resolutions(multi_review_poems, compute_agreement_report)
    if not pending:
        return

    st.markdown("### Poems awaiting admin decision")
    for entry in pending:
        reviewers = ", ".join(entry.get("reviewers") or [])
        st.markdown(
            f"""
            <div class="resolution-card">
                <strong>{entry.get("title", "Untitled poem")}</strong>
                <span class="small-muted"> &middot; {entry.get("language", "")}</span><br>
                <span class="small-muted">
                    Combined agreement: {entry.get("combined_agreement", "")} &middot;
                    Reviewers: {reviewers}
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.caption("Select a poem below to compare reviews and save your final admin decision.")
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

reviews, storage_message = load_all_reviews()
summary_df = review_summary_df(reviews)
multi_review_poems = poems_with_multiple_reviews(reviews)

st.title("MorphoVerse++ Review Admin")
st.caption(f"Signed in as admin: **{admin_user}**")
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
    st.markdown("##### Export data")
    st.download_button(
        "All reviews (JSON)",
        data=reviews_to_json_bytes(reviews),
        file_name="all_reviews.json",
        mime="application/json",
        use_container_width=True,
    )
    st.download_button(
        "Submissions summary (CSV)",
        data=summary_df_to_csv_bytes(submissions_display_df(summary_df)),
        file_name="submissions_summary.csv",
        mime="text/csv",
        use_container_width=True,
    )
    st.download_button(
        "All annotations (CSV)",
        data=annotations_to_csv_bytes(reviews),
        file_name="all_annotations.csv",
        mime="text/csv",
        use_container_width=True,
    )
    st.download_button(
        "Admin-accepted gold (JSON)",
        data=gold_annotations_json_bytes(reviews),
        file_name="gold_annotations.json",
        mime="application/json",
        use_container_width=True,
    )
    st.download_button(
        "Admin-accepted gold (CSV)",
        data=gold_annotations_csv_bytes(reviews),
        file_name="gold_annotations.csv",
        mime="text/csv",
        use_container_width=True,
    )

    if selected_poem_id:
        selected_exports = filter_reviews_by_poem(reviews, selected_poem_id)
        st.download_button(
            "Selected poem reviews (JSON)",
            data=reviews_to_json_bytes(selected_exports),
            file_name=f"poem_reviews_{selected_poem_id}.json",
            mime="application/json",
            use_container_width=True,
        )
        st.download_button(
            "Selected poem annotations (CSV)",
            data=annotations_to_csv_bytes(selected_exports),
            file_name=f"poem_annotations_{selected_poem_id}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.divider()
    zip_path = make_review_zip()
    if zip_path and zip_path.exists():
        with zip_path.open("rb") as f:
            st.download_button(
                "Legacy reviewed JSON (ZIP)",
                data=f,
                file_name="reviewed_outputs.zip",
                mime="application/zip",
                use_container_width=True,
            )

render_pending_admin_decisions(multi_review_poems)

st.subheader("Overview")
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Reviewers", summary_df["reviewer"].nunique())
m2.metric("Poems reviewed", summary_df["poem_id"].nunique())
m3.metric("Total submissions", len(summary_df))
m4.metric("Multi-review poems", len(multi_review_poems))
m5.metric(
    "Awaiting admin decision",
    len(pending_conflict_resolutions(multi_review_poems, compute_agreement_report)),
)

if multi_review_poems:
    st.markdown("### Poems needing comparison")
    compare_option_map = {
        comparison_option_label(revs, compute_agreement_report(revs)["combined"]): pid
        for pid, revs in sorted(
            multi_review_poems.items(),
            key=lambda item: compute_agreement_report(item[1])["combined"],
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
        )

    poem_title = (
        sanitize_display_title(poem_reviews[0].get("title", ""))
        if poem_reviews
        else "Untitled poem"
    )
    resolution = get_resolution(selected_poem_id) if selected_poem_id else None
    accepted_reviewer = str((resolution or {}).get("accepted_reviewer") or "")

    st.markdown(f"### Selected poem reviews — {poem_title}")
    export_col1, export_col2 = st.columns(2)
    with export_col1:
        st.download_button(
            "Download this poem (JSON)",
            data=reviews_to_json_bytes(poem_reviews),
            file_name=f"{poem_title.replace(' ', '_')}_reviews.json",
            mime="application/json",
            use_container_width=True,
            key=f"json_export_{selected_poem_id}",
        )
    with export_col2:
        st.download_button(
            "Download this poem annotations (CSV)",
            data=annotations_to_csv_bytes(poem_reviews),
            file_name=f"{poem_title.replace(' ', '_')}_annotations.csv",
            mime="text/csv",
            use_container_width=True,
            key=f"csv_export_{selected_poem_id}",
        )

    for review in poem_reviews:
        reviewer = review.get("logged_in_user") or review.get("reviewer_id", "unknown")
        label = f"{reviewer} — {review.get('review_status', '')}"
        if accepted_reviewer and str(reviewer) == accepted_reviewer:
            label += " · ADMIN ACCEPTED"
        with st.expander(label, expanded=len(poem_reviews) == 1):
            render_review(review)
