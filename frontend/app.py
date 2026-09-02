from __future__ import annotations

import sys
from html import escape
from pathlib import Path

import streamlit as st  # pyright: ignore[reportMissingImports]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from app_security.environment import load_project_environment
from app_security.models import mask_identifier
from ui_pages.ai_page import ai_page
from ui_pages.analytics_page import analytics_page
from ui_pages.dashboard_page import dashboard_page
from ui_pages.login_page import login_page
from ui_pages.settings_page import settings_page
from ui_pages.strategy_page import strategy_page
from utils.auth import (
    PASSWORD_WIDGET_KEY,
    REMOTE_TOKEN_WIDGET_KEY,
    authorize_remote_access,
    get_authenticated_credentials,
    is_authenticated,
    remote_access_authorized,
    remote_access_is_configured,
    remote_access_required,
    resolve_page,
)
from utils.session_manager import load_session
from utils.ui_theme import apply_theme


load_project_environment()
st.set_page_config(page_title="Forex Signal Bot", layout="wide")
apply_theme()


def _enforce_remote_access_gate() -> None:
    if not remote_access_required(server_address=st.get_option("server.address")):
        return
    if remote_access_authorized(st.session_state):
        st.session_state.pop(REMOTE_TOKEN_WIDGET_KEY, None)
        return
    if not remote_access_is_configured():
        st.error("Remote access is disabled because no application access token is configured.")
        st.stop()

    st.title("Remote Access")
    with st.form("remote_access_form"):
        candidate = st.text_input(
            "Application access token",
            type="password",
            key=REMOTE_TOKEN_WIDGET_KEY,
        )
        submitted = st.form_submit_button("Continue")
        if submitted:
            if authorize_remote_access(st.session_state, candidate):
                st.rerun()
            st.error("Access denied.")
    st.stop()


st.markdown(
    """
    <link rel="manifest" href="/static/manifest.json">
    <meta name="theme-color" content="#f8d34f">
    <script>
      if ("serviceWorker" in navigator) {
        window.addEventListener("load", () => {
          navigator.serviceWorker.register("/static/service-worker.js");
        });
      }
    </script>
    """,
    unsafe_allow_html=True,
)

_enforce_remote_access_gate()

# Loading preferences also performs one-way migration of legacy password fields.
preferences = load_session() or {}
if not is_authenticated(st.session_state):
    st.session_state["page"] = "login"
    login_page()
    st.stop()

st.session_state.pop(PASSWORD_WIDGET_KEY, None)
credentials = get_authenticated_credentials(st.session_state)
if credentials is None:
    st.session_state["page"] = "login"
    st.stop()

if "page" not in st.session_state:
    st.session_state["page"] = "dashboard"

with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand">
            <span class="brand-icon">◈</span> FX BOT
        </div>
        <div class="sidebar-subtitle">Trading Terminal</div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="nav-section-label">NAVIGATION</div>', unsafe_allow_html=True)

    page_order = ("login", "dashboard", "strategy", "analytics", "ai", "settings")
    current_page = resolve_page(st.session_state.get("page", "dashboard"), st.session_state)
    current_index = page_order.index(current_page)
    choice = st.radio(
        "Navigate",
        ("Login", "Dashboard", "Strategy", "Analytics", "AI Copilot", "Settings"),
        index=current_index,
        label_visibility="collapsed",
    )

    st.markdown('<div class="nav-divider"></div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="sidebar-card">
            <div class="status-row">
                <span class="status-dot"></span>
                <span class="pill success">SESSION LIVE</span>
            </div>
            <div class="session-user">Logged in as <strong>{escape(mask_identifier(credentials.login))}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="nav-section-label">SNAPSHOT</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="snapshot-grid">
            <div class="snapshot-item">
                <div class="snapshot-label">Capital</div>
                <div class="snapshot-value">${float(preferences.get('capital', 1000.0)):.2f}</div>
            </div>
            <div class="snapshot-vsep"></div>
            <div class="snapshot-item">
                <div class="snapshot-label">Target</div>
                <div class="snapshot-value">{float(preferences.get('daily_target_pct', 1.0)):.2f}%</div>
            </div>
            <div class="snapshot-vsep"></div>
            <div class="snapshot-item">
                <div class="snapshot-label">Refresh</div>
                <div class="snapshot-value">{int(preferences.get('refresh_interval', 5))}s</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

choice_to_page = {
    "Login": "login",
    "Dashboard": "dashboard",
    "Strategy": "strategy",
    "Analytics": "analytics",
    "AI Copilot": "ai",
    "Settings": "settings",
}
st.session_state["page"] = resolve_page(choice_to_page[choice], st.session_state)

st.markdown('<div class="page-transition">', unsafe_allow_html=True)
if st.session_state["page"] == "login":
    login_page()
elif st.session_state["page"] == "dashboard":
    dashboard_page()
elif st.session_state["page"] == "strategy":
    strategy_page()
elif st.session_state["page"] == "analytics":
    analytics_page()
elif st.session_state["page"] == "ai":
    ai_page()
else:
    settings_page()
st.markdown("</div>", unsafe_allow_html=True)
