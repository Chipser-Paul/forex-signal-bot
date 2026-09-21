from __future__ import annotations

from html import escape

import streamlit as st  # pyright: ignore[reportMissingImports]

from app_security.models import MT5Credentials, mask_identifier
from utils.auth import (
    PASSWORD_WIDGET_KEY,
    clear_authenticated_session,
    establish_authenticated_session,
    get_authenticated_credentials,
)
from utils.credential_store import delete_password, get_password, store_password
from utils.mt5_connector import connect_mt5, shutdown_mt5
from utils.session_manager import clear_session, load_session, save_session


def _logout() -> None:
    credentials = get_authenticated_credentials(st.session_state)
    clear_session(
        forget_credentials=True,
        login=credentials.login if credentials else None,
        server=credentials.server if credentials else None,
    )
    clear_authenticated_session(st.session_state)
    shutdown_mt5()


def login_page() -> bool:
    st.markdown(
        """
        <div class="app-hero">
            <h1>MT5 Secure Login</h1>
            <p>Connect your trading account and launch the live dashboard.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    active_credentials = get_authenticated_credentials(st.session_state)
    if active_credentials:
        st.markdown(
            f"""
            <div class="card-shell" style="border-left: 4px solid var(--success);">
                <div class="panel-title">Active Session</div>
                <div class="mini-value">{escape(mask_identifier(active_credentials.login))}</div>
                <div class="mini-meta">Server: {escape(active_credentials.server)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button("Logout", width="stretch"):
                _logout()
                st.stop()
        with col2:
            st.info("Session is active. Go to Dashboard to monitor trades.")
        return True

    preferences = load_session() or {}
    saved_login = str(preferences.get("login", ""))
    saved_server = str(preferences.get("server", ""))
    remembered_password = None
    if preferences.get("remember_password") and saved_login and saved_server:
        remembered_password = get_password(saved_login, saved_server)

    st.markdown("<div class='section-title'>Credentials</div>", unsafe_allow_html=True)
    with st.form("login_form"):
        col1, col2 = st.columns(2)
        with col1:
            login = st.text_input("Login ID", value=saved_login, placeholder="Account number")
            server = st.text_input("Server", value=saved_server, placeholder="Broker server name")
        with col2:
            password = st.text_input(
                "Password",
                value=remembered_password or "",
                type="password",
                key=PASSWORD_WIDGET_KEY,
            )
            account_name = st.text_input(
                "Account Label (optional)",
                value=str(preferences.get("account_label", "")),
                placeholder="My Trading Account",
            )
        remember_password = st.checkbox(
            "Remember password in the operating system credential store",
            value=bool(remembered_password),
        )
        submit = st.form_submit_button("Connect MT5")

        if submit:
            if not login or not password or not server:
                st.error("Please fill in all required fields.")
                return False

            st.info("Connecting to MT5...")
            account_data, error = connect_mt5(login, password, server)

            if account_data:
                credentials = MT5Credentials(login=str(login), password=password, server=server)
                if saved_login and saved_server and (
                    saved_login != credentials.login
                    or saved_server.casefold() != credentials.server.casefold()
                ):
                    delete_password(saved_login, saved_server)
                password_persisted = False
                if remember_password:
                    password_persisted = store_password(login, server, password)
                else:
                    delete_password(login, server)

                preferences_saved = save_session(
                    login=str(login),
                    server=str(server),
                    account=str(account_data.get("login", "")),
                    broker=str(account_data.get("server", "")),
                    account_label=account_name or "",
                    capital=float(preferences.get("capital", 1000.0)),
                    daily_target_pct=float(preferences.get("daily_target_pct", 1.0)),
                    lock_profit=float(preferences.get("lock_profit", 5.0)),
                    lock_pct=float(preferences.get("lock_pct", 0.5)),
                    refresh_interval=int(preferences.get("refresh_interval", 5)),
                    btc_enabled=bool(preferences.get("btc_enabled", True)),
                    remember_password=password_persisted,
                )
                if not preferences_saved and password_persisted:
                    delete_password(credentials.login, credentials.server)
                    password_persisted = False
                establish_authenticated_session(st.session_state, credentials)
                st.success("Login successful. The connected account identity was verified.")
                if remember_password and not password_persisted:
                    st.warning(
                        "Secure OS credential storage is unavailable. "
                        "The password will be required again next time."
                    )
                if not preferences_saved:
                    st.warning("Non-sensitive preferences could not be saved on this machine.")
                shutdown_mt5()
                st.session_state["page"] = "dashboard"
                st.rerun()

            st.error("Login failed. Verify the account identifier, password, and broker server.")
            shutdown_mt5()

    st.caption(
        "Passwords stay in memory for the active session and are remembered only through "
        "the operating system credential store."
    )
    return False
