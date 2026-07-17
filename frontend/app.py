import streamlit as st  # pyright: ignore[reportMissingImports]

from ui_pages.login_page import login_page
from ui_pages.dashboard_page import dashboard_page
from ui_pages.strategy_page import strategy_page
from ui_pages.analytics_page import analytics_page
from ui_pages.ai_page import ai_page
from ui_pages.settings_page import settings_page
from utils.session_manager import load_session
from utils.ui_theme import apply_theme

st.set_page_config(page_title="Forex Signal Bot", layout="wide")
apply_theme()

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

# initialize simple page state
if "page" not in st.session_state:
    # prefer dashboard if session exists
    st.session_state.page = "dashboard" if load_session() else "login"

# Sidebar navigation
with st.sidebar:
    # Brand header
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

    choice = st.radio(
        "Navigate",
        ("Login", "Dashboard", "Strategy", "Analytics", "AI Copilot", "Settings"),
        index=0
        if st.session_state.page == "login"
        else 1
        if st.session_state.page == "dashboard"
        else 2
        if st.session_state.page == "strategy"
        else 3
        if st.session_state.page == "analytics"
        else 4
        if st.session_state.page == "ai"
        else 5,
        label_visibility="collapsed",
    )

    st.markdown('<div class="nav-divider"></div>', unsafe_allow_html=True)

    session = load_session()
    if session:
        st.markdown(
            f"""
            <div class="sidebar-card">
                <div class="status-row">
                    <span class="status-dot"></span>
                    <span class="pill success">SESSION LIVE</span>
                </div>
                <div class="session-user">Logged in as <strong>{session.get('login')}</strong></div>
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
                    <div class="snapshot-value">${float(session.get('capital', 1000.0)):.2f}</div>
                </div>
                <div class="snapshot-vsep"></div>
                <div class="snapshot-item">
                    <div class="snapshot-label">Target</div>
                    <div class="snapshot-value">{float(session.get('daily_target_pct', 1.0)):.2f}%</div>
                </div>
                <div class="snapshot-vsep"></div>
                <div class="snapshot-item">
                    <div class="snapshot-label">Refresh</div>
                    <div class="snapshot-value">{int(session.get('refresh_interval', 5))}s</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div class="sidebar-card">
                <div class="status-row">
                    <span class="status-dot offline"></span>
                    <span class="pill warn">OFFLINE</span>
                </div>
                <div class="session-user">Login to connect MT5</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# map radio selection to page state
if choice == "Login":
    st.session_state.page = "login"
elif choice == "Dashboard":
    st.session_state.page = "dashboard"
elif choice == "Strategy":
    st.session_state.page = "strategy"
elif choice == "Analytics":
    st.session_state.page = "analytics"
elif choice == "AI Copilot":
    st.session_state.page = "ai"
else:
    st.session_state.page = "settings"

# Render the requested page
st.markdown('<div class="page-transition">', unsafe_allow_html=True)
if st.session_state.page == "login":
    login_page()
elif st.session_state.page == "dashboard":
    dashboard_page()
elif st.session_state.page == "strategy":
    strategy_page()
elif st.session_state.page == "analytics":
    analytics_page()
elif st.session_state.page == "ai":
    ai_page()
else:
    settings_page()
st.markdown('</div>', unsafe_allow_html=True)
