from __future__ import annotations

import os
from typing import Dict

import streamlit as st


def init_auth_state() -> None:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "username" not in st.session_state:
        st.session_state.username = None
    if "show_instructions" not in st.session_state:
        st.session_state.show_instructions = False
    if "instructions_completed" not in st.session_state:
        st.session_state.instructions_completed = False


def get_credentials(section: str, env_key: str, default: Dict[str, str] | None = None) -> Dict[str, str]:
    credentials: Dict[str, str] = dict(default or {})

    try:
        section_creds = st.secrets.get(section, {})
        if isinstance(section_creds, dict):
            for username, password in section_creds.items():
                credentials[str(username)] = str(password)
    except (FileNotFoundError, AttributeError, KeyError):
        pass

    env_users = os.environ.get(env_key, "")
    if env_users:
        for pair in env_users.split(","):
            pair = pair.strip()
            if ":" in pair:
                username, password = pair.split(":", 1)
                credentials[username.strip()] = password.strip()

    return credentials


def get_reviewer_credential_passwords() -> Dict[str, str]:
    creds = get_credentials("reviewer_credentials", "REVIEWER_CREDENTIALS")
    if not creds:
        creds["reviewer"] = os.environ.get("REVIEWER_PASSWORD", "morphoverse2025")
    return creds


def get_shared_reviewer_password() -> str:
    try:
        password = st.secrets.get("REVIEWER_PASSWORD", "")
        if password:
            return str(password).strip()
    except (FileNotFoundError, AttributeError, KeyError):
        pass

    env_password = os.environ.get("REVIEWER_PASSWORD", "").strip()
    if env_password:
        return env_password

    creds = get_reviewer_credential_passwords()
    passwords = {str(p).strip() for p in creds.values() if str(p).strip()}
    if len(passwords) == 1:
        return next(iter(passwords))

    return "morphoverse2025"


def get_admin_credentials() -> Dict[str, str]:
    creds = get_credentials("admin_credentials", "ADMIN_CREDENTIALS")
    if not creds:
        creds["admin"] = os.environ.get("ADMIN_PASSWORD", "admin2025")
    return creds


def validate_reviewer_login(name: str, password: str) -> bool:
    name = name.strip()
    password = password.strip()
    if not name or not password:
        return False

    shared_password = get_shared_reviewer_password()
    if password == shared_password:
        return True

    # Support legacy secrets.toml with [reviewer_credentials] — any name is OK
    # when the password matches any configured reviewer password.
    allowed_passwords = {str(p).strip() for p in get_reviewer_credential_passwords().values() if str(p).strip()}
    return password in allowed_passwords


def validate_admin_login(username: str, password: str) -> bool:
    expected = get_admin_credentials().get(username.strip())
    return expected is not None and expected == password


def logout() -> None:
    st.session_state.authenticated = False
    st.session_state.username = None
    st.session_state.show_instructions = False
    st.session_state.instructions_completed = False
    st.session_state.selected_language = None
    st.session_state.selected_languages = []


def admin_logout() -> None:
    st.session_state.admin_authenticated = False
    st.session_state.admin_username = None


def render_login_page() -> None:
    st.markdown(
        """
        <div class="mv-hero" style="max-width: 560px; margin: 2.5rem auto 1.5rem auto; text-align: center;">
            <h1>MorphoVerse++ Human Review</h1>
            <div class="small-muted">
                Enter your name and the shared reviewer password to begin.<br>
                Your work is saved under your name and is visible only to admins.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, center, _ = st.columns([1, 1.1, 1])
    with center:
        with st.form("login_form", clear_on_submit=False):
            name = st.text_input("Your name", placeholder="your name")
            password = st.text_input("Password", type="password", placeholder="Shared reviewer password")
            submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)

        if submitted:
            if not name.strip() or not password:
                st.error("Please enter your name and the password.")
            elif validate_reviewer_login(name, password):
                st.session_state.authenticated = True
                st.session_state.username = name.strip()
                st.session_state.show_instructions = True
                st.session_state.instructions_completed = False
                st.rerun()
            else:
                st.error("Incorrect password. Any name works — use the shared reviewer password.")


def render_admin_login_page() -> None:
    st.markdown(
        """
        <div class="mv-hero" style="max-width: 520px; margin: 2.5rem auto 1.5rem auto; text-align: center;">
            <h1>Admin Dashboard</h1>
            <div class="small-muted">Sign in to review submissions and resolve reviewer conflicts.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, center, _ = st.columns([1, 1.1, 1])
    with center:
        with st.form("admin_login_form", clear_on_submit=False):
            username = st.text_input("Admin username", placeholder="admin")
            password = st.text_input("Password", type="password", placeholder="Admin password")
            submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)

        if submitted:
            if not username.strip() or not password:
                st.error("Please enter both username and password.")
            elif validate_admin_login(username, password):
                st.session_state.admin_authenticated = True
                st.session_state.admin_username = username.strip()
                st.rerun()
            else:
                st.error("Invalid admin credentials.")


@st.dialog("How to review poems", width="large")
def show_instructions_dialog() -> None:
    st.markdown(
        """
        Welcome! Please read these steps before you start reviewing.
        """
    )

    st.markdown("#### Workflow")
    st.markdown(
        """
        1. **Choose your languages** — select which languages you will review.
        2. **Pick a poem** from the sidebar for your active language.
        3. **Read** the original poem and English translation.
        4. **Review annotation tables** — culture entities, metaphors, emotions, and visual motifs.
        5. **Use actions on each row:**
           - `keep` — correct as-is (row becomes read-only)
           - `modify` — you corrected it (add a comment)
           - `remove` — exclude from final output (add a comment)
           - `add` — only for new rows you create
        6. **Submit** your final decision with a comment at the bottom.
        """
    )

    st.markdown("#### Rules")
    st.markdown(
        """
        - Your submissions are saved under your **name** and visible only to admins.
        - Use **approved** only when you made no changes. Use **approved_with_corrections** if you edited anything.
        - Rows marked **keep** cannot be edited.
        - Existing rows cannot use the **add** action — use **add** only for new rows.
        - Always add a **reviewer_comment** when you modify, remove, or add a row.
        """
    )

    if st.button("Continue to language selection", type="primary", use_container_width=True):
        st.session_state.show_instructions = False
        st.session_state.instructions_completed = True
        st.rerun()


def render_instructions_if_needed() -> None:
    if st.session_state.get("show_instructions") and not st.session_state.get("instructions_completed"):
        show_instructions_dialog()


def require_login() -> str:
    init_auth_state()
    if not st.session_state.authenticated:
        render_login_page()
        st.stop()
    return str(st.session_state.username or "")


def init_admin_state() -> None:
    if "admin_authenticated" not in st.session_state:
        st.session_state.admin_authenticated = False
    if "admin_username" not in st.session_state:
        st.session_state.admin_username = None


def require_admin_login() -> str:
    init_admin_state()
    if not st.session_state.admin_authenticated:
        render_admin_login_page()
        st.stop()
    return str(st.session_state.admin_username or "")
