from __future__ import annotations

import streamlit as st

FONT_MIN = 80
FONT_MAX = 140
FONT_STEP = 10
FONT_DEFAULT = 100

THEME_OPTIONS = ("Light", "Dark", "Sepia")


def init_display_prefs() -> None:
    if "font_scale" not in st.session_state:
        st.session_state.font_scale = FONT_DEFAULT
    if "ui_theme" not in st.session_state:
        st.session_state.ui_theme = "Light"


def _theme_tokens(theme: str) -> dict[str, str]:
    if theme == "Dark":
        return {
            "app_bg": "#0f1419",
            "card_bg": "#1a2332",
            "card_border": "#2d3a4f",
            "text": "#e8edf4",
            "muted": "#9aa8b8",
            "poem_bg": "#151d28",
            "poem_border": "#3d4f66",
            "hero_bg": "#1a2332",
            "top_bar_bg": "linear-gradient(90deg, #1e2a3d 0%, #151d28 100%)",
            "top_bar_border": "#2d3a4f",
            "top_bar_title": "#93c5fd",
            "section_border": "#2d3a4f",
            "code_bg": "#2a1f14",
            "code_text": "#fdba74",
            "code_border": "#7c4a1a",
        }
    if theme == "Sepia":
        return {
            "app_bg": "#f4ecd8",
            "card_bg": "#faf6eb",
            "card_border": "#d4c4a0",
            "text": "#3d2f1f",
            "muted": "#6b5a42",
            "poem_bg": "#fff9ee",
            "poem_border": "#c9b896",
            "hero_bg": "#faf6eb",
            "top_bar_bg": "linear-gradient(90deg, #f5ead0 0%, #faf6eb 100%)",
            "top_bar_border": "#d4c4a0",
            "top_bar_title": "#5c3d1e",
            "section_border": "#d4c4a0",
            "code_bg": "#fff3e0",
            "code_text": "#7c2d12",
            "code_border": "#e8c9a0",
        }
    return {
        "app_bg": "#ffffff",
        "card_bg": "#ffffff",
        "card_border": "#d1d5db",
        "text": "#111827",
        "muted": "#4b5563",
        "poem_bg": "#fffdf7",
        "poem_border": "rgba(31, 41, 55, 0.22)",
        "hero_bg": "#ffffff",
        "top_bar_bg": "linear-gradient(90deg, #eff6ff 0%, #f8fafc 100%)",
        "top_bar_border": "#dbeafe",
        "top_bar_title": "#1e3a8a",
        "section_border": "#e5e7eb",
        "code_bg": "#fff7ed",
        "code_text": "#7c2d12",
        "code_border": "#fed7aa",
    }


def get_display_css() -> str:
    init_display_prefs()
    scale = st.session_state.font_scale / 100.0
    theme = str(st.session_state.ui_theme)
    tokens = _theme_tokens(theme)
    base_px = 16 * scale
    poem_px = base_px * 1.08
    small_px = 0.88 * base_px
    title_px = 2.0 * base_px

    return f"""
<style>
.stApp {{
    background-color: {tokens["app_bg"]};
    color: {tokens["text"]};
    font-size: {base_px}px;
}}
.block-container {{
    color: {tokens["text"]};
}}
.mv-card, .mv-hero, .admin-card {{
    border: 1px solid {tokens["card_border"]};
    background: {tokens["card_bg"]};
    color: {tokens["text"]};
}}
.mv-hero h1 {{
    color: {tokens["text"]};
    font-size: {title_px}px;
}}
.mv-section-title, .section-header, .lang-hero h2 {{
    color: {tokens["text"]};
}}
.small-muted, .metric-note, .lang-stat, .top-bar-sub {{
    color: {tokens["muted"]};
    font-size: {small_px}px;
}}
.poem-box {{
    font-size: {poem_px}px;
    background: {tokens["poem_bg"]};
    border-color: {tokens["poem_border"]};
    color: {tokens["text"]};
}}
.poem-label {{
    color: {tokens["text"]};
    font-size: {0.9 * base_px}px;
}}
.top-bar {{
    background: {tokens["top_bar_bg"]};
    border-color: {tokens["top_bar_border"]};
}}
.top-bar-title {{
    color: {tokens["top_bar_title"]};
    font-size: {1.05 * base_px}px;
}}
.lang-card {{
    background: {tokens["card_bg"]};
    border-color: {tokens["card_border"]};
}}
.lang-card h3 {{
    color: {tokens["top_bar_title"]};
}}
.lang-poem-list li {{
    color: {tokens["text"]};
    border-bottom-color: {tokens["section_border"]};
}}
.lang-poem-id {{
    color: {tokens["muted"]};
}}
.section-header {{
    border-bottom-color: {tokens["section_border"]};
    font-size: {1.15 * base_px}px;
}}
.field-guide code, .review-steps code {{
    color: {tokens["code_text"]};
    background: {tokens["code_bg"]};
    border-color: {tokens["code_border"]};
}}
.attention-list, .review-steps, .field-guide {{
    color: {tokens["text"]};
}}
[data-testid="stSidebar"] {{
    background-color: {tokens["card_bg"]};
}}
</style>
"""


def render_display_controls() -> None:
    init_display_prefs()
    st.markdown("##### Display")
    theme_index = (
        THEME_OPTIONS.index(st.session_state.ui_theme)
        if st.session_state.ui_theme in THEME_OPTIONS
        else 0
    )
    st.session_state.ui_theme = st.selectbox("Theme", THEME_OPTIONS, index=theme_index)

    st.caption(f"Text size: {st.session_state.font_scale}%")
    minus_col, reset_col, plus_col = st.columns(3)
    with minus_col:
        if st.button("A−", use_container_width=True, help="Decrease text size"):
            st.session_state.font_scale = max(FONT_MIN, st.session_state.font_scale - FONT_STEP)
            st.rerun()
    with reset_col:
        if st.button("Reset", use_container_width=True, help="Reset text size"):
            st.session_state.font_scale = FONT_DEFAULT
            st.rerun()
    with plus_col:
        if st.button("A+", use_container_width=True, help="Increase text size"):
            st.session_state.font_scale = min(FONT_MAX, st.session_state.font_scale + FONT_STEP)
            st.rerun()
