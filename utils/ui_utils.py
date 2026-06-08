from __future__ import annotations

from html import escape
from typing import Any, Dict, List, Tuple

import streamlit as st

from utils.review_utils import get_title
from utils.reviewer_store import get_user_languages, save_user_languages


LANGUAGE_UI_CSS = """
<style>
.lang-hero {
    text-align: center;
    margin: 1.5rem auto 2rem auto;
    max-width: 720px;
}
.lang-hero h2 {
    margin: 0 0 0.5rem 0;
    font-size: 1.85rem;
    color: #111827;
}
.lang-card {
    border: 2px solid #e5e7eb;
    border-radius: 14px;
    padding: 1rem;
    background: #f9fafb;
    text-align: center;
    margin-bottom: 0.5rem;
}
.lang-card h3 {
    margin: 0 0 0.35rem 0;
    font-size: 1.1rem;
    color: #1e3a5f;
}
.lang-poem-list {
    list-style: none;
    margin: 0.6rem 0 0 0;
    padding: 0;
    text-align: left;
}
.lang-poem-list li {
    font-size: 0.86rem;
    color: #374151;
    padding: 0.28rem 0;
    border-bottom: 1px solid #e5e7eb;
}
.lang-poem-list li:last-child {
    border-bottom: none;
}
.lang-poem-id {
    font-size: 0.75rem;
    color: #6b7280;
}
.top-bar {
    border: 1px solid #dbeafe;
    border-radius: 10px;
    padding: 0.85rem 1.1rem;
    background: linear-gradient(90deg, #eff6ff 0%, #f8fafc 100%);
    margin-bottom: 1.1rem;
}
.top-bar-title {
    font-size: 1.05rem;
    font-weight: 700;
    color: #1e3a8a;
}
.top-bar-sub {
    font-size: 0.88rem;
    color: #4b5563;
}
.section-header {
    font-size: 1.15rem;
    font-weight: 700;
    color: #111827;
    margin: 0.5rem 0 0.75rem 0;
    padding-bottom: 0.35rem;
    border-bottom: 2px solid #e5e7eb;
}
</style>
"""


def init_ui_state() -> None:
    if "selected_language" not in st.session_state:
        st.session_state.selected_language = None
    if "selected_languages" not in st.session_state:
        st.session_state.selected_languages = []
    if "choosing_languages" not in st.session_state:
        st.session_state.choosing_languages = False


def clear_language_setup() -> None:
    st.session_state.selected_language = None
    st.session_state.selected_languages = []
    st.session_state.choosing_languages = True


def language_key(raw: Dict[str, Any]) -> str:
    return str(raw.get("language") or raw.get("_language_folder") or "Unknown")


def language_poem_groups(
    poems: List[Dict[str, Any]],
    get_poem_id_fn,
) -> List[Tuple[str, List[Tuple[str, str]]]]:
    """Return (language, [(poem_id, title), ...]) sorted by language then title."""
    languages = sorted({language_key(p) for p in poems})
    rows: List[Tuple[str, List[Tuple[str, str]]]] = []
    for lang in languages:
        lang_poems = sorted(
            [p for p in poems if language_key(p) == lang],
            key=lambda p: get_title(p).lower(),
        )
        entries = [(get_poem_id_fn(p), get_title(p)) for p in lang_poems]
        rows.append((lang, entries))
    return rows


def _poem_list_html(entries: List[Tuple[str, str]]) -> str:
    items = []
    for poem_id, title in entries:
        safe_title = escape(title or poem_id)
        safe_id = escape(poem_id)
        items.append(
            f'<li><strong>{safe_title}</strong><br><span class="lang-poem-id">{safe_id}</span></li>'
        )
    return f'<ul class="lang-poem-list">{"".join(items)}</ul>'


def render_language_multiselect(
    poems: List[Dict[str, Any]],
    reviewed_index: Dict[str, Dict[str, Any]],
    get_poem_id_fn,
    logged_in_user: str,
) -> None:
    st.markdown(LANGUAGE_UI_CSS, unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="lang-hero">
            <h2>Which languages will you review?</h2>
            <div class="small-muted">
                Hi <strong>{logged_in_user}</strong> — select one or more languages.
                You will only see these languages while reviewing.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    groups = language_poem_groups(poems, get_poem_id_fn)
    all_languages = [lang for lang, _ in groups]

    saved = get_user_languages(logged_in_user)
    default_selection = [lang for lang in saved if lang in all_languages]

    cols = st.columns(min(3, len(groups)) or 1)
    for index, (lang, entries) in enumerate(groups):
        with cols[index % len(cols)]:
            st.markdown(
                f"""
                <div class="lang-card">
                    <h3>{escape(lang)}</h3>
                    {_poem_list_html(entries)}
                </div>
                """,
                unsafe_allow_html=True,
            )

    selected = st.multiselect(
        "Your languages",
        options=all_languages,
        default=default_selection,
        placeholder="Select at least one language",
        help="Only these languages will appear in your review workflow.",
    )

    if st.button("Start reviewing", type="primary", disabled=not selected, use_container_width=True):
        st.session_state.selected_languages = selected
        save_user_languages(logged_in_user, selected)
        st.session_state.selected_language = selected[0]
        st.session_state.choosing_languages = False
        st.rerun()


def render_top_bar(language: str, logged_in_user: str) -> None:
    st.markdown(
        f"""
        <div class="top-bar">
            <span class="top-bar-title">MorphoVerse++ Review</span>
            <span class="top-bar-sub"> &rsaquo; {language} &middot; {logged_in_user}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def require_language_setup(
    poems: List[Dict[str, Any]],
    reviewed_index: Dict[str, Dict[str, Any]],
    get_poem_id_fn,
    logged_in_user: str,
) -> tuple[List[str], str]:
    """Return (selected_languages, active_language). Blocks until configured."""
    init_ui_state()

    available = {language_key(p) for p in poems}
    if st.session_state.choosing_languages:
        render_language_multiselect(poems, reviewed_index, get_poem_id_fn, logged_in_user)
        st.stop()

    saved = [lang for lang in get_user_languages(logged_in_user) if lang in available]
    if not st.session_state.selected_languages and saved:
        st.session_state.selected_languages = saved

    selected_languages = [lang for lang in st.session_state.selected_languages if lang in available]
    if not selected_languages:
        st.session_state.choosing_languages = True
        render_language_multiselect(poems, reviewed_index, get_poem_id_fn, logged_in_user)
        st.stop()

    active = st.session_state.get("selected_language")
    if active not in selected_languages:
        active = selected_languages[0]
        st.session_state.selected_language = active

    return selected_languages, str(active)
