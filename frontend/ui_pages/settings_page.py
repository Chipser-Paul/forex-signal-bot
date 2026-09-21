from __future__ import annotations

import os
from html import escape
from pathlib import Path

import streamlit as st  # pyright: ignore[reportMissingImports]

from app_security.models import mask_identifier
from utils.auth import clear_authenticated_session, get_authenticated_credentials
from utils.bot_control import get_bot_state, set_bot_state
from utils.bot_runner import get_bot_status, start_bot, stop_bot
from utils.mt5_connector import shutdown_mt5
from utils.session_manager import clear_session, load_session, save_session
from utils.ui_launcher import get_ui_status, start_ui, stop_ui


def settings_page() -> None:
    credentials = get_authenticated_credentials(st.session_state)
    if credentials is None:
        st.warning("Authentication is required. Please log in again.")
        st.session_state["page"] = "login"
        st.stop()
    session = load_session() or {}

    capital = float(session.get("capital", 1000.0))
    daily_target_pct = float(session.get("daily_target_pct", 1.0))
    lock_profit = float(session.get("lock_profit", 5.0))
    lock_pct = float(session.get("lock_pct", (lock_profit / max(capital, 1e-9)) * 100.0))
    refresh_interval = int(session.get("refresh_interval", 5))
    btc_enabled = bool(session.get("btc_enabled", True))

    st.markdown(
        """
        <div class="app-hero">
            <h1>Settings & Control</h1>
            <p>Manage risk settings, operating state, launcher processes, and platform readiness.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left, right = st.columns([1.3, 1])
    with left:
        st.markdown("<div class='section-title'>Trading Profile</div>", unsafe_allow_html=True)
        with st.container(border=True):
            new_capital = st.number_input("Capital (USD)", min_value=1.0, value=capital, step=100.0)
            new_daily_target_pct = st.slider(
                "Daily Profit Target (%)", 0.5, 20.0, value=float(daily_target_pct), step=0.5
            )
            col1, col2 = st.columns(2)
            with col1:
                new_lock_profit = st.number_input("Lock Profit (USD)", min_value=0.0, value=lock_profit, step=1.0)
            with col2:
                new_lock_pct = st.number_input("Lock Profit (%)", min_value=0.0, value=lock_pct, step=0.1)
            new_refresh_interval = st.slider("UI Refresh Interval (sec)", 3, 30, value=refresh_interval)

            if st.button("Save Trading Settings", key="save_settings", width="stretch"):
                if new_capital > 0:
                    if abs(new_lock_profit - lock_profit) < 1e-9 and abs(new_lock_pct - lock_pct) > 1e-9:
                        new_lock_profit = round((new_lock_pct / 100.0) * new_capital, 6)
                    else:
                        new_lock_pct = round((new_lock_profit / max(new_capital, 1e-9)) * 100.0, 4)
                save_session(
                    {
                        **session,
                        "capital": float(new_capital),
                        "daily_target_pct": float(new_daily_target_pct),
                        "lock_profit": float(new_lock_profit),
                        "lock_pct": float(new_lock_pct),
                        "refresh_interval": int(new_refresh_interval),
                        "btc_enabled": btc_enabled,
                    }
                )
                st.success("Trading settings updated.")

        st.markdown("<div class='section-title'>BTCUSDm Control</div>", unsafe_allow_html=True)
        with st.container(border=True):
            status_class = "success" if btc_enabled else "danger"
            status_text = "BTCUSDm TRADING ON" if btc_enabled else "BTCUSDm TRADING OFF"
            st.markdown(
                f"<span class='pill {status_class}'>{status_text}</span>",
                unsafe_allow_html=True,
            )
            st.caption(
                "This only controls whether new BTCUSDm trades can be opened. "
                "Existing BTCUSDm positions will still be managed safely."
            )
            button_label = "Turn Off BTCUSDm Trading" if btc_enabled else "Turn On BTCUSDm Trading"
            if st.button(button_label, key="toggle_btc_trading", width="stretch"):
                updated_btc_enabled = not btc_enabled
                save_session(
                    {
                        **session,
                        "capital": capital,
                        "daily_target_pct": daily_target_pct,
                        "lock_profit": lock_profit,
                        "lock_pct": lock_pct,
                        "refresh_interval": refresh_interval,
                        "btc_enabled": updated_btc_enabled,
                    }
                )
                st.success(
                    "BTCUSDm trading enabled." if updated_btc_enabled else "BTCUSDm trading disabled."
                )
                st.rerun()

        st.markdown("<div class='section-title'>Session</div>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown(
                f"""
                <div class="mini-stat-grid">
                    <div class="mini-stat">
                        <div class="mini-label">Login</div>
                        <div class="mini-value">{escape(mask_identifier(credentials.login))}</div>
                    </div>
                    <div class="mini-stat">
                        <div class="mini-label">Server</div>
                        <div class="mini-value">{escape(credentials.server)}</div>
                    </div>
                    <div class="mini-stat">
                        <div class="mini-label">Refresh</div>
                        <div class="mini-value">{session.get('refresh_interval', 5)}s</div>
                    </div>
                    <div class="mini-stat">
                        <div class="mini-label">BTC</div>
                        <div class="mini-value">{'ON' if session.get('btc_enabled', True) else 'OFF'}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Logout Session", key="logout_settings", width="stretch"):
                clear_session(
                    forget_credentials=True,
                    login=credentials.login,
                    server=credentials.server,
                )
                clear_authenticated_session(st.session_state)
                shutdown_mt5()
                st.success("Session cleared.")
                st.stop()

    with right:
        st.markdown("<div class='section-title'>Operations</div>", unsafe_allow_html=True)
        bot_status = get_bot_status()
        ui_status = get_ui_status()
        control_state = get_bot_state().upper()

        with st.container(border=True):
            st.markdown("#### Bot Engine")
            st.markdown(
                f"<span class='pill {'success' if bot_status['running'] else 'danger'}'>BOT {'RUNNING' if bot_status['running'] else 'STOPPED'}</span>",
                unsafe_allow_html=True,
            )
            if bot_status["running"]:
                st.caption(f"PID {bot_status['pid']} | Started {bot_status['started_at']}")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Start Bot", width="stretch", key="settings_start_bot"):
                    ok, msg = start_bot(float(session.get("capital", 1000.0)), credentials)
                    if ok:
                        set_bot_state("running")
                        st.success(msg)
                    else:
                        st.warning(msg)
            with col2:
                if st.button("Stop Bot", width="stretch", key="settings_stop_bot"):
                    ok, msg = stop_bot()
                    set_bot_state("stopped")
                    if ok:
                        st.success(msg)
                    else:
                        st.warning(msg)
            if st.button("Pause Bot (soft)", width="stretch", key="settings_pause_bot"):
                set_bot_state("paused")
                st.info("Bot state set to paused.")
            st.caption(f"Control State: {control_state}")

        with st.container(border=True):
            st.markdown("#### Frontend Launcher")
            st.markdown(
                f"<span class='pill {'success' if ui_status['running'] else 'danger'}'>UI {'RUNNING' if ui_status['running'] else 'STOPPED'}</span>",
                unsafe_allow_html=True,
            )
            if ui_status["running"]:
                st.caption(f"PID {ui_status['pid']} | Started {ui_status['started_at']}")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Start UI", width="stretch", key="settings_start_ui"):
                    ok, msg = start_ui()
                    if ok:
                        st.success(msg)
                    else:
                        st.warning(msg)
            with col2:
                if st.button("Stop UI", width="stretch", key="settings_stop_ui"):
                    ok, msg = stop_ui()
                    if ok:
                        st.success(msg)
                    else:
                        st.warning(msg)

        with st.container(border=True):
            telegram_ready = bool(
                os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
                and os.getenv("TELEGRAM_CHAT_ID", "").strip()
            )
            fcm_tokens_ready = bool(
                os.getenv("FCM_DEVICE_TOKEN", "").strip()
                or os.getenv("FCM_DEVICE_TOKENS", "").strip()
            )
            fcm_service_path = os.getenv(
                "FIREBASE_SERVICE_ACCOUNT_PATH",
                "secrets/firebase-service-account.json",
            ).strip() or "secrets/firebase-service-account.json"
            fcm_service_ready = Path(fcm_service_path).exists()
            push_ready = fcm_tokens_ready and fcm_service_ready

            st.markdown("#### Integrations")
            st.markdown(
                f"""
                <div class="card-shell">
                    <table class="health-table">
                        <thead><tr><th>Component</th><th>Status</th></tr></thead>
                        <tbody>
                            <tr>
                                <td>Telegram</td>
                                <td><span class="pill {'success' if telegram_ready else 'warn'}">{'READY' if telegram_ready else 'NOT SET'}</span></td>
                            </tr>
                            <tr>
                                <td>Push (FCM)</td>
                                <td><span class="pill {'success' if push_ready else 'warn'}">{'READY' if push_ready else 'NOT SET'}</span></td>
                            </tr>
                            <tr>
                                <td>Service Account</td>
                                <td><span class="pill {'success' if fcm_service_ready else 'danger'}">{'FOUND' if fcm_service_ready else 'MISSING'}</span></td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                """,
                unsafe_allow_html=True,
            )
