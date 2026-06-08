from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from utils.io_utils import (
    append_audit_log,
    ensure_app_dirs,
    load_raw_poems,
    now_iso,
    review_id,
    resolve_data_dir,
)
from utils.review_utils import (
    cleaned_records,
    get_agreement,
    get_original_poem,
    get_poem_id,
    get_stanza_rows,
    get_status,
    get_title,
    get_translation,
    normalize_culture_entities,
    normalize_emotions,
    normalize_metaphors,
    normalize_visual_motifs,
)
from utils.schema_utils import (
    ALLOWED_CULTURE_CATEGORIES,
    ALLOWED_EMOTIONS,
    REVIEW_ACTIONS,
    REVIEW_ACTIONS_EXISTING,
    REVIEW_CONFIDENCE,
    REVIEW_DECISIONS,
    REVIEW_STATUS_FILTERS,
)
from utils.reviewer_store import (
    get_co_reviewers_for_poem,
    load_user_poem_review,
    load_user_reviewed_index,
    save_poem_review,
)
from utils.auth_utils import (
    init_auth_state,
    logout,
    render_instructions_if_needed,
    require_login,
    show_instructions_dialog,
)
from utils.ui_utils import (
    LANGUAGE_UI_CSS,
    clear_language_setup,
    init_ui_state,
    language_key,
    render_top_bar,
    require_language_setup,
)
from utils.display_prefs import get_display_css, init_display_prefs, render_display_controls
from utils.storage_utils import get_supabase_config, persistent_storage_label, save_review_to_persistent_storage


st.set_page_config(
    page_title="MorphoVerse++ Human Review",
    page_icon="MV",
    layout="wide",
    initial_sidebar_state="expanded",
)


CUSTOM_CSS = """
<style>
.block-container {
    padding-top: 1.15rem;
    padding-bottom: 2rem;
}
.mv-card {
    border: 1px solid #d1d5db;
    border-radius: 8px;
    padding: 1rem;
    background: #ffffff;
    color: #111827;
    margin-bottom: 1rem;
    box-shadow: 0 1px 2px rgba(36, 39, 47, 0.05);
}
.mv-hero {
    border: 1px solid #d1d5db;
    border-radius: 8px;
    padding: 1.15rem 1.25rem;
    background: #ffffff;
    color: #111827;
    margin-bottom: 1rem;
}
.mv-hero h1 {
    margin: 0 0 0.35rem 0;
    font-size: 2rem;
    color: #111827;
}
.mv-section-title {
    margin-bottom: 0.45rem;
    color: #111827;
}
.mv-badge {
    display: inline-block;
    border-radius: 999px;
    padding: 0.22rem 0.7rem;
    font-size: 0.78rem;
    font-weight: 700;
    margin: 0 0.35rem 0.35rem 0;
    border: 1px solid rgba(49, 51, 63, 0.15);
}
.badge-green { background: #eaf7ef; color: #176b3a; }
.badge-blue { background: #edf4ff; color: #174a8b; }
.badge-yellow { background: #fff7db; color: #7a5200; }
.badge-red { background: #ffecec; color: #9d1c1c; }
.badge-gray { background: #f2f2f2; color: #444; }
.poem-box {
    white-space: pre-wrap;
    line-height: 1.85;
    font-size: 1.08rem;
    padding: 1.1rem 1.2rem;
    border-radius: 8px;
    border: 1px solid rgba(31, 41, 55, 0.22);
    background: #fffdf7;
    color: #111827;
    min-height: 220px;
    max-height: 480px;
    overflow-y: auto;
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.7);
}
.poem-label {
    color: inherit;
    font-size: 0.9rem;
    font-weight: 700;
    margin: 0.35rem 0 0.4rem 0;
}
.quick-review-band {
    border-top: 1px solid rgba(36, 39, 47, 0.12);
    padding-top: 0.85rem;
    margin-top: 0.35rem;
}
.small-muted {
    color: #4b5563;
    font-size: 0.88rem;
}
.metric-note {
    font-size: 0.78rem;
    color: #4b5563;
}
.attention-list {
    margin: 0.2rem 0 0 1rem;
    padding: 0;
    color: #111827;
}
.attention-list li {
    margin-bottom: 0.25rem;
}
.review-steps {
    margin: 0.35rem 0 0 1.2rem;
    padding: 0;
    color: #111827;
}
.review-steps li {
    margin-bottom: 0.45rem;
}
.review-steps strong {
    color: #0f5132;
}
.field-guide {
    margin: 0.35rem 0 0 0;
    color: #111827;
}
.field-guide p {
    margin: 0 0 0.45rem 0;
}
.field-guide code,
.review-steps code {
    color: #7c2d12;
    background: #fff7ed;
    border: 1px solid #fed7aa;
    border-radius: 4px;
    padding: 0.05rem 0.25rem;
}
</style>
"""
st.markdown(CUSTOM_CSS + LANGUAGE_UI_CSS + get_display_css(), unsafe_allow_html=True)


def badge(text: str, kind: str = "gray") -> str:
    return f'<span class="mv-badge badge-{kind}">{text}</span>'


def status_badge_kind(status: str) -> str:
    status = (status or "").lower()
    if status in {"approved", "completed"}:
        return "green"
    if status in {"approved_with_corrections", "in_progress"}:
        return "blue"
    if status in {"pending_review", "needs_major_revision", "pending"}:
        return "yellow"
    if status in {"rejected", "failed", "load_error"}:
        return "red"
    return "gray"


def agreement_badge_kind(agreement: str) -> str:
    agreement = (agreement or "").lower()
    if agreement == "high":
        return "green"
    if agreement == "medium":
        return "yellow"
    if agreement == "low":
        return "red"
    return "gray"


def get_current_review_status(raw: Dict[str, Any], reviewed_index: Dict[str, Dict[str, Any]]) -> str:
    poem_id = get_poem_id(raw)
    if poem_id in reviewed_index:
        return str(reviewed_index[poem_id].get("review_status") or "reviewed")
    raw_status = get_status(raw).lower()
    if raw_status in {"failed", "pending"}:
        return raw_status
    return "pending_review"


def filter_poems(poems: List[Dict[str, Any]], language: str, status_filter: str, reviewed_index: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    filtered = [p for p in poems if p.get("language") == language or p.get("_language_folder") == language]
    if status_filter != "all":
        filtered = [p for p in filtered if get_current_review_status(p, reviewed_index) == status_filter]
    return filtered


def load_initial_tables(raw: Dict[str, Any], reviewed: Dict[str, Any] | None):
    """Load edited tables from reviewed JSON when available; otherwise raw normalized tables."""
    if reviewed and reviewed.get("final_annotations"):
        final = reviewed["final_annotations"]
        culture_df = pd.DataFrame(final.get("culture_entities", []))
        metaphor_df = pd.DataFrame(final.get("metaphor_spans", []))
        emotion_df = pd.DataFrame(final.get("stanza_emotions", []))
        motif_df = pd.DataFrame(final.get("visual_motifs", []))

        # Ensure columns remain stable even if old reviewed files are incomplete.
        if culture_df.empty:
            culture_df = normalize_culture_entities(raw)
        if metaphor_df.empty:
            metaphor_df = normalize_metaphors(raw)
        if emotion_df.empty:
            emotion_df = normalize_emotions(raw)
        if motif_df.empty:
            motif_df = normalize_visual_motifs(raw)
        return culture_df, metaphor_df, emotion_df, motif_df

    return (
        normalize_culture_entities(raw),
        normalize_metaphors(raw),
        normalize_emotions(raw),
        normalize_visual_motifs(raw),
    )


def safe_text(value: Any) -> str:
    return escape(str(value or ""))


def row_count(df: pd.DataFrame) -> int:
    return 0 if df is None or df.empty else len(df)


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except TypeError:
        pass
    return isinstance(value, str) and not value.strip()


def review_records(df: pd.DataFrame, key_col: str) -> List[Dict[str, Any]]:
    """Return non-empty rows for validation and saving."""
    if df is None or df.empty:
        return []

    records: List[Dict[str, Any]] = []
    for rec in df.fillna("").to_dict(orient="records"):
        if str(rec.get(key_col, "")).strip():
            records.append(rec)
    return records


def validate_review_table(
    df: pd.DataFrame,
    section: str,
    key_col: str,
    required_when_kept: List[str],
) -> List[str]:
    errors: List[str] = []
    for idx, rec in enumerate(review_records(df, key_col), start=1):
        action = str(rec.get("review_action", "")).strip()
        row_name = str(rec.get(key_col, "")).strip()

        if action not in REVIEW_ACTIONS:
            errors.append(f"{section} row {idx} ({row_name}): choose a review_action from the dropdown.")
            continue

        if action in {"modify", "remove", "add"} and is_blank(rec.get("reviewer_comment")):
            errors.append(f"{section} row {idx} ({row_name}): add a reviewer_comment for {action}.")

        if action != "remove":
            for col in required_when_kept:
                if is_blank(rec.get(col)):
                    errors.append(f"{section} row {idx} ({row_name}): fill `{col}` or mark the row as remove.")

    return errors


def has_review_edits(*tables: pd.DataFrame) -> bool:
    for df in tables:
        for rec in review_records(df, "review_action"):
            if str(rec.get("review_action", "")).strip() in {"modify", "remove", "add"}:
                return True
    return False


def changed_records(df: pd.DataFrame, key_col: str) -> List[Dict[str, Any]]:
    changes: List[Dict[str, Any]] = []
    for rec in review_records(df, key_col):
        if str(rec.get("review_action", "")).strip() in {"modify", "remove", "add"}:
            changes.append(rec)
    return changes


def table_preview(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)
    available = [col for col in columns if col in df.columns]
    return df[available].copy()


def get_low_agreement_notes(raw: Dict[str, Any]) -> List[str]:
    notes: List[str] = []
    if str(get_agreement(raw)).lower() == "low":
        notes.append("Overall model agreement is low.")

    annotation = raw.get("annotation", {})
    stats = annotation.get("agreement_stats", {}) if isinstance(annotation, dict) else {}
    low_stanzas = int(stats.get("low_stanza_count") or 0)
    low_entities = int(stats.get("low_entity_count") or 0)
    review_items = raw.get("review_items", []) or []

    if low_stanzas:
        notes.append(f"{low_stanzas} stanza-level item(s) have low agreement.")
    if low_entities:
        notes.append(f"{low_entities} cultural entity item(s) have low agreement.")
    if review_items:
        notes.append(f"{len(review_items)} model disagreement item(s) are queued for checking.")
    if not notes:
        notes.append("No urgent disagreement flags were found for this poem.")
    return notes


def poem_option_label(raw: Dict[str, Any], reviewed_index: Dict[str, Dict[str, Any]]) -> str:
    poem_id = get_poem_id(raw)
    title = get_title(raw)
    short_title = title if len(title) <= 42 else f"{title[:39]}..."
    status = get_current_review_status(raw, reviewed_index)
    you_status = "done" if status not in {"pending_review", "pending"} else "pending"
    agreement = get_agreement(raw) or "n/a"
    return f"{short_title} · {poem_id} · you: {you_status}"


def review_action_column(include_add: bool = True) -> st.column_config.SelectboxColumn:
    options = REVIEW_ACTIONS if include_add else REVIEW_ACTIONS_EXISTING
    return st.column_config.SelectboxColumn(
        "Action",
        help="keep = correct (read-only for culture) · modify · remove · add (new rows only)",
        options=options,
        required=True,
    )


def mark_original_rows(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "_is_original" not in out.columns:
        out["_is_original"] = True
    out["_is_original"] = out["_is_original"].fillna(False).astype(bool)
    return out


def build_keep_disabled_mask(df: pd.DataFrame, action_col: str = "review_action") -> pd.DataFrame:
    disabled = pd.DataFrame(False, index=df.index, columns=df.columns)
    if df.empty:
        return disabled
    for idx in df.index:
        if str(df.at[idx, action_col]).strip() == "keep":
            for col in df.columns:
                if col not in {action_col, "_is_original"}:
                    disabled.at[idx, col] = True
    return disabled


def strip_internal_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop(columns=["_is_original"], errors="ignore")


def validate_existing_row_actions(df: pd.DataFrame, section: str, key_col: str) -> List[str]:
    errors: List[str] = []
    if df is None or df.empty or "_is_original" not in df.columns:
        return errors
    for idx, rec in enumerate(df.fillna("").to_dict(orient="records"), start=1):
        is_original = rec.get("_is_original") is True or str(rec.get("_is_original", "")).lower() == "true"
        if is_original and str(rec.get("review_action", "")).strip() == "add":
            row_name = str(rec.get(key_col, "")).strip() or f"row {idx}"
            errors.append(f"{section} ({row_name}): 'add' is only for new rows you create.")
    return errors


def validate_culture_keep_unchanged(
    edited: pd.DataFrame,
    original: pd.DataFrame,
    key_col: str = "text",
) -> List[str]:
    errors: List[str] = []
    if edited is None or original is None or edited.empty or original.empty:
        return errors
    original_by_key = {
        str(row.get(key_col, "")).strip(): row
        for row in original.fillna("").to_dict(orient="records")
        if str(row.get(key_col, "")).strip()
    }
    for rec in edited.fillna("").to_dict(orient="records"):
        if str(rec.get("review_action", "")).strip() != "keep":
            continue
        row_name = str(rec.get(key_col, "")).strip()
        source = original_by_key.get(row_name)
        if not source:
            continue
        compare_cols = [c for c in edited.columns if c not in {"review_action", "reviewer_comment", "_is_original"}]
        for col in compare_cols:
            if str(rec.get(col, "")).strip() != str(source.get(col, "")).strip():
                errors.append(
                    f"Culture entities ({row_name}): rows marked keep cannot be edited. "
                    "Change the action to modify if you need to correct this row."
                )
                break
    return errors


def metrics_block(poems: List[Dict[str, Any]], reviewed_index: Dict[str, Dict[str, Any]], language: str | None = None):
    if language:
        poems = [p for p in poems if language_key(p) == language]
    total = len(poems)
    reviewed = len([p for p in poems if get_poem_id(p) in reviewed_index])
    pending = total - reviewed

    reviews = [
        review
        for poem_review_summary in reviewed_index.values()
        for review in poem_review_summary.get("reviews", [])
    ]
    decisions = [str(v.get("review_status") or "") for v in reviews]
    approved = decisions.count("approved")
    corrected = decisions.count("approved_with_corrections")
    major = decisions.count("needs_major_revision")
    rejected = decisions.count("rejected")

    c1, c2, c3 = st.columns(3)
    c1.metric("Total loaded", total)
    c2.metric("Poems with review", reviewed)
    c3.metric("Pending", pending)
    if total:
        st.progress(reviewed / total, text=f"{reviewed} of {total} poems reviewed")

    c4, c5, c6, c7 = st.columns(4)
    c4.metric("Approved reviews", approved)
    c5.metric("Approved + corrections", corrected)
    c6.metric("Major revision", major)
    c7.metric("Rejected", rejected)


def df_editor_culture(df: pd.DataFrame, key: str) -> pd.DataFrame:
    df = mark_original_rows(df)
    display_cols = [
        "review_action",
        "text",
        "category",
        "preserved",
        "english_gloss",
        "romanization",
        "translation_note",
        "stanza_index",
        "confidence",
        "reviewer_comment",
        "_is_original",
    ]
    for col in display_cols:
        if col not in df.columns and col != "_is_original":
            df[col] = ""
    editor_df = df[display_cols].copy()
    if isinstance(st.session_state.get(key), pd.DataFrame):
        editor_df = st.session_state[key]
    edited = st.data_editor(
        editor_df,
        key=key,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        disabled=build_keep_disabled_mask(editor_df),
        column_config={
            "category": st.column_config.SelectboxColumn("category", options=ALLOWED_CULTURE_CATEGORIES),
            "review_action": review_action_column(include_add=True),
            "reviewer_comment": st.column_config.TextColumn("reviewer_comment", width="large"),
            "_is_original": None,
        },
    )
    if edited is None:
        return df
    if "_is_original" in edited.columns:
        edited.loc[edited["_is_original"].isna(), "_is_original"] = False
    return edited


def df_editor_metaphor(df: pd.DataFrame, key: str) -> pd.DataFrame:
    df = mark_original_rows(df)
    edited = st.data_editor(
        df,
        key=key,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_order=[
            "review_action",
            "source_text",
            "abstract_meaning",
            "literal_meaning",
            "visual_hint",
            "stanza_index",
            "confidence",
            "reviewer_comment",
            "_is_original",
        ],
        column_config={
            "review_action": review_action_column(include_add=True),
            "abstract_meaning": st.column_config.TextColumn("abstract_meaning", width="large"),
            "visual_hint": st.column_config.TextColumn("visual_hint", width="large"),
            "reviewer_comment": st.column_config.TextColumn("reviewer_comment", width="large"),
            "_is_original": None,
        },
    )
    return edited if edited is not None else df


def df_editor_emotion(df: pd.DataFrame, key: str) -> pd.DataFrame:
    df = mark_original_rows(df)
    edited = st.data_editor(
        df,
        key=key,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_order=[
            "review_action",
            "stanza_index",
            "emotion",
            "tone",
            "translation_quality",
            "loss_note",
            "confidence",
            "reviewer_comment",
            "_is_original",
        ],
        column_config={
            "emotion": st.column_config.SelectboxColumn("emotion", options=ALLOWED_EMOTIONS),
            "review_action": review_action_column(include_add=True),
            "reviewer_comment": st.column_config.TextColumn("reviewer_comment", width="large"),
            "_is_original": None,
        },
    )
    return edited if edited is not None else df


def df_editor_motif(df: pd.DataFrame, key: str) -> pd.DataFrame:
    df = mark_original_rows(df)
    edited = st.data_editor(
        df,
        key=key,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_order=[
            "review_action",
            "motif",
            "keep_for_image_generation",
            "importance",
            "stanza_index",
            "confidence",
            "reviewer_comment",
            "_is_original",
        ],
        column_config={
            "keep_for_image_generation": st.column_config.CheckboxColumn("keep_for_image_generation"),
            "review_action": review_action_column(include_add=True),
            "reviewer_comment": st.column_config.TextColumn("reviewer_comment", width="large"),
            "_is_original": None,
        },
    )
    return edited if edited is not None else df


init_auth_state()
init_ui_state()
init_display_prefs()
logged_in_user = require_login()
render_instructions_if_needed()

ensure_app_dirs()
data_dir = resolve_data_dir()
poems = load_raw_poems(data_dir)
reviewed_index = load_user_reviewed_index(logged_in_user)

if not data_dir.exists():
    st.error(
        f"Raw data folder not found: `{data_dir}`. Place the `output_v3` folder in the project root."
    )
    st.stop()

if not poems:
    st.warning("No low-confidence poems found. Check that `output_v3/annotation_summary.csv` is present.")
    st.stop()

st.caption(f"Loaded **{len(poems)}** low-confidence poems from `{data_dir}`")

selected_languages, language = require_language_setup(
    poems, reviewed_index, get_poem_id, logged_in_user
)

render_top_bar(language, logged_in_user)

with st.sidebar:
    st.header("Navigation")
    if len(selected_languages) > 1:
        language = st.selectbox("Active language", selected_languages, index=selected_languages.index(language))
        st.session_state.selected_language = language
    else:
        st.caption(f"Language: **{language}**")

    if st.button("Change languages", use_container_width=True, type="secondary"):
        clear_language_setup()
        st.rerun()

    status_filter = st.selectbox("Show poems", REVIEW_STATUS_FILTERS, index=0)

    language_poems = filter_poems(poems, language, status_filter, reviewed_index)
    search_query = st.text_input("Search", placeholder="Poem ID or title").strip().lower()
    if search_query:
        language_poems = [
            p
            for p in language_poems
            if search_query in get_poem_id(p).lower() or search_query in get_title(p).lower()
        ]
    if not language_poems:
        st.warning("No poems match this filter. Try a different status or search term.")
        st.stop()

    poem_options = {
        poem_option_label(p, reviewed_index): get_poem_id(p) for p in language_poems
    }
    poem_labels = list(poem_options.keys())
    selected_label = st.selectbox("Select poem to review", poem_labels, index=0)
    selected_poem_id = poem_options[selected_label]

    st.divider()
    render_display_controls()

    st.divider()
    st.caption(f"Signed in as **{logged_in_user}**")
    st.caption(f"Storage: {persistent_storage_label()}")
    if st.button("Review instructions", use_container_width=True):
        st.session_state.show_instructions = True
        st.session_state.instructions_completed = False
        show_instructions_dialog()
    if st.button("Sign out", use_container_width=True):
        logout()
        st.rerun()

raw = next(p for p in language_poems if get_poem_id(p) == selected_poem_id)
poem_id = get_poem_id(raw)
poem_language = str(raw.get("language") or raw.get("_language_folder") or language)
title = get_title(raw)
reviewed = load_user_poem_review(logged_in_user, poem_id)
current_review_status = get_current_review_status(raw, reviewed_index)
original_culture_df = normalize_culture_entities(raw)

st.markdown('<div class="section-header">Poem overview</div>', unsafe_allow_html=True)
st.subheader(title)
st.markdown(
    badge(poem_id, "blue")
    + badge(poem_language, "gray")
    + badge(f"Status: {current_review_status}", status_badge_kind(current_review_status)),
    unsafe_allow_html=True,
)
co_reviewers = get_co_reviewers_for_poem(poem_id, exclude_username=logged_in_user)
if co_reviewers:
    st.caption(
        f"**{len(co_reviewers)} other reviewer(s)** also submitted this poem: {', '.join(co_reviewers)}. "
        "Your review is saved separately under your name."
    )

if reviewed:
    st.info("You have a saved review for this poem. Submitting again will update your copy only.")
else:
    st.caption("Your review will be saved under your name. Other reviewers can review the same poem independently.")

culture_df, metaphor_df, emotion_df, motif_df = load_initial_tables(raw, reviewed)

st.markdown('<div class="section-header">Read the poem</div>', unsafe_allow_html=True)
st.markdown('<div class="quick-review-band"></div>', unsafe_allow_html=True)

poem_left, poem_right = st.columns(2)
with poem_left:
    st.markdown('<div class="poem-label">Original poem</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="poem-box">{safe_text(get_original_poem(raw))}</div>', unsafe_allow_html=True)
with poem_right:
    st.markdown('<div class="poem-label">English translation</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="poem-box">{safe_text(get_translation(raw))}</div>', unsafe_allow_html=True)

st.markdown('<div class="section-header">Edit annotations</div>', unsafe_allow_html=True)
st.caption("Click any cell to edit. Use the **Action** column: keep · modify · remove · add")

tab_culture, tab_metaphor, tab_emotion, tab_motif = st.tabs([
    f"Culture ({row_count(culture_df)})",
    f"Metaphors ({row_count(metaphor_df)})",
    f"Emotions ({row_count(emotion_df)})",
    f"Visual motifs ({row_count(motif_df)})",
])

with tab_culture:
    st.caption("Rows marked **keep** are read-only. Use **modify** to edit a row.")
    edited_culture_df = df_editor_culture(culture_df, key=f"culture_{poem_id}")

with tab_metaphor:
    st.caption("Keep only truly figurative phrases. Remove literal or invented metaphors.")
    edited_metaphor_df = df_editor_metaphor(metaphor_df, key=f"metaphor_{poem_id}")

with tab_emotion:
    st.caption("Check each stanza's emotion and tone against the poem and translation.")
    edited_emotion_df = df_editor_emotion(emotion_df, key=f"emotion_{poem_id}")

with tab_motif:
    st.caption("Keep concrete visual motifs present in the poem. Remove vague or generic items.")
    edited_motif_df = df_editor_motif(motif_df, key=f"motif_{poem_id}")

with st.container():
    st.markdown('<div class="section-header">Submit your review</div>', unsafe_allow_html=True)
    st.caption(
        "Use **approved** only if nothing changed. Use **approved_with_corrections** if you edited any row. "
        "Add a reason for major revision or rejection."
    )

    previous_decision = reviewed.get("reviewer_decision", {}) if reviewed else {}
    previous_status = reviewed.get("review_status", "approved_with_corrections") if reviewed else "approved_with_corrections"
    previous_confidence = reviewed.get("reviewer_confidence", "medium") if reviewed else "medium"

    with st.form(key=f"decision_form_{poem_id}", clear_on_submit=False):
        decision = st.selectbox(
            "Overall decision",
            REVIEW_DECISIONS,
            index=REVIEW_DECISIONS.index(previous_status) if previous_status in REVIEW_DECISIONS else 1,
        )
        confidence = st.selectbox(
            "Reviewer confidence",
            REVIEW_CONFIDENCE,
            index=REVIEW_CONFIDENCE.index(previous_confidence) if previous_confidence in REVIEW_CONFIDENCE else 1,
        )
        reason = st.text_area(
            "Final reviewer reason/comment",
            value=str(previous_decision.get("reason", "")),
            height=130,
            placeholder="Mention what you corrected, approved, rejected, or why this needs revision.",
        )
        confirm = st.checkbox("I confirm that I have reviewed this poem and its annotations.")
        submitted = st.form_submit_button("Submit reviewed annotation", type="primary", use_container_width=True)

    if submitted:
        errors = []
        if decision in {"needs_major_revision", "rejected"} and not reason.strip():
            errors.append("Reason/comment is mandatory for needs_major_revision or rejected.")
        if not confirm:
            errors.append("Please confirm that you reviewed this poem.")
        culture_clean = strip_internal_columns(edited_culture_df)
        metaphor_clean = strip_internal_columns(edited_metaphor_df)
        emotion_clean = strip_internal_columns(edited_emotion_df)
        motif_clean = strip_internal_columns(edited_motif_df)

        errors.extend(validate_review_table(culture_clean, "Culture entities", "text", ["category", "preserved"]))
        errors.extend(validate_review_table(metaphor_clean, "Metaphors", "source_text", ["abstract_meaning"]))
        errors.extend(validate_review_table(emotion_clean, "Stanza emotions", "stanza_index", ["emotion"]))
        errors.extend(validate_review_table(motif_clean, "Visual motifs", "motif", ["keep_for_image_generation"]))
        errors.extend(validate_existing_row_actions(culture_clean, "Culture entities", "text"))
        errors.extend(validate_existing_row_actions(metaphor_clean, "Metaphors", "source_text"))
        errors.extend(validate_existing_row_actions(emotion_clean, "Stanza emotions", "stanza_index"))
        errors.extend(validate_existing_row_actions(motif_clean, "Visual motifs", "motif"))
        errors.extend(validate_culture_keep_unchanged(culture_clean, mark_original_rows(original_culture_df)))
        if decision == "approved" and has_review_edits(culture_clean, metaphor_clean, emotion_clean, motif_clean):
            errors.append("Use approved_with_corrections because at least one row is marked modify, remove, or add.")

        if errors:
            for err in errors:
                st.error(err)
        else:
            submitted_reviewer_id = logged_in_user
            reviewed_at = now_iso()

            payload = {
                "review_id": review_id(poem_id, submitted_reviewer_id),
                "poem_id": poem_id,
                "language": poem_language,
                "title": title,
                "review_status": decision,
                "reviewer_id": submitted_reviewer_id,
                "logged_in_user": logged_in_user,
                "reviewer_confidence": confidence,
                "reviewed_at": reviewed_at,
                "original_poem": get_original_poem(raw),
                "english_translation": get_translation(raw),
                "source_annotation_file": raw.get("_source_file", ""),
                "final_annotations": {
                    "culture_entities": cleaned_records(culture_clean, "text"),
                    "metaphor_spans": cleaned_records(metaphor_clean, "source_text"),
                    "stanza_emotions": cleaned_records(emotion_clean, "stanza_index"),
                    "visual_motifs": cleaned_records(motif_clean, "motif"),
                },
                "review_changes": {
                    "culture_entities": changed_records(culture_clean, "text"),
                    "metaphor_spans": changed_records(metaphor_clean, "source_text"),
                    "stanza_emotions": changed_records(emotion_clean, "stanza_index"),
                    "visual_motifs": changed_records(motif_clean, "motif"),
                },
                "reviewer_decision": {
                    "decision": decision,
                    "reason": reason.strip(),
                },
                "raw_llm_annotation_snapshot": raw,
            }

            save_poem_review(logged_in_user, poem_id, payload)

            audit_entry = {
                "event": "review_submitted",
                "review_id": payload["review_id"],
                "poem_id": poem_id,
                "language": poem_language,
                "reviewer_id": submitted_reviewer_id,
                "logged_in_user": logged_in_user,
                "decision": decision,
                "reviewer_confidence": confidence,
                "reviewed_at": reviewed_at,
                "storage": "reviewer_submissions",
            }
            append_audit_log(audit_entry)

            persistent_ok, persistent_message = save_review_to_persistent_storage(payload, audit_entry)

            st.success(f"Your review for **{poem_id}** was saved under **{logged_in_user}**.")
            if persistent_ok:
                st.success("Saved to database (Supabase). Admins can see all reviewer submissions.")
            elif get_supabase_config()[0]:
                st.warning(persistent_message)
            else:
                st.caption(
                    "Saved locally. Configure Supabase in Streamlit secrets for persistent cloud storage."
                )
