from __future__ import annotations

import os
import time
from pathlib import Path

import streamlit as st  # pyright: ignore[reportMissingImports]

from utils.bot_control import get_bot_state
from utils.bot_runner import get_bot_status
from utils.mt5_connector import (
    connect_mt5,
    get_account_info,
    get_closed_profit_today,
    get_open_trades,
)
from utils.session_manager import load_session
from utils.ui_launcher import get_ui_status


def dashboard_page() -> None:
    session = load_session()
    if not session:
        st.warning("No active session. Please log in again.")
        st.stop()

    login = session.get("login")
    password = session.get("password")
    server = session.get("server")
    refresh_rate = int(session.get("refresh_interval", 5))

    with st.spinner("Connecting to MT5..."):
        account_data, error = connect_mt5(login, password, server)
        if error or not account_data:
            st.error(f"Failed to connect to MT5: {error}")
            st.stop()

    st.markdown(
        f"""
        <div class="app-hero">
            <h1>Mission Control</h1>
            <p>Account {account_data['login']} | Server {account_data['server']} | Clean live view of performance, risk, and system health.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    current_session = load_session() or session
    current_capital = float(current_session.get("capital", 1000.0))
    current_target_pct = float(current_session.get("daily_target_pct", 1.0))
    current_lock_profit = float(current_session.get("lock_profit", 5.0))
    current_lock_pct = float(
        current_session.get("lock_pct", (current_lock_profit / max(current_capital, 1e-9)) * 100.0)
    )
    refresh_rate = int(current_session.get("refresh_interval", refresh_rate))

    account_info = get_account_info()
    trades = get_open_trades()
    bot_status_live = get_bot_status()
    ui_status_live = get_ui_status()

    if not account_info:
        st.error("Connection lost. Please restart the app.")
        return

    current_profit = float(get_closed_profit_today())
    daily_target_value = current_capital * current_target_pct / 100.0
    amount_locked = min(current_profit, current_lock_profit)
    progress_pct = (
        min((current_profit / daily_target_value) * 100.0, 100.0)
        if daily_target_value > 0
        else 0.0
    )
    safe_progress = max(0.0, min(progress_pct, 100.0)) / 100.0
    last_updated = time.strftime("%H:%M:%S")

    if current_profit >= daily_target_value:
        status_text = "TARGET HIT"
        status_meta = "Daily objective reached. Risk is protected."
    elif current_profit >= current_lock_profit:
        status_text = "LOCK LEVEL"
        status_meta = "Profit lock threshold is active."
    else:
        status_text = "ACTIVE"
        status_meta = "System is still hunting valid setups."

    st.markdown(
        f"""
        <div class="hero-split">
            <div class="hero-stat">
                <div class="hero-stat-label">Live Status</div>
                <div class="hero-stat-value">{status_text}</div>
                <div class="hero-stat-meta">{status_meta}</div>
            </div>
            <div class="hero-stat">
                <div class="hero-stat-label">Equity</div>
                <div class="hero-stat-value">${account_info['equity']:.2f}</div>
                <div class="hero-stat-meta">Balance ${account_info['balance']:.2f}</div>
            </div>
            <div class="hero-stat">
                <div class="hero-stat-label">Profit Today</div>
                <div class="hero-stat-value">${current_profit:.2f}</div>
                <div class="hero-stat-meta">Target ${daily_target_value:.2f}</div>
            </div>
            <div class="hero-stat">
                <div class="hero-stat-label">Lock Level</div>
                <div class="hero-stat-value">${amount_locked:.2f}</div>
                <div class="hero-stat-meta">Cap ${current_lock_profit:.2f} | {current_lock_pct:.2f}%</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    top_left, top_right = st.columns([1.45, 1])
    with top_left:
        st.markdown("<div class='section-title'>Performance Board</div>", unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="card-shell">
                <div class="panel-title">Daily Progress</div>
                <div class="panel-subtitle">Refresh every {refresh_rate} seconds | Last update {last_updated}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.progress(safe_progress)
        st.caption(
            f"Current Profit ${current_profit:.2f} / Target ${daily_target_value:.2f} ({progress_pct:.2f}%)"
        )

        quick_stats = st.columns(3)
        quick_stats[0].metric("Open Symbols", len(trades))
        quick_stats[1].metric("Bot State", "Running" if bot_status_live["running"] else "Stopped")
        quick_stats[2].metric("Refresh", f"{refresh_rate}s")

        st.markdown("<div class='section-title'>Open Trade Exposure</div>", unsafe_allow_html=True)
        if trades:
            rows_html = ""
            for symbol, data in trades.items():
                profit = round(float(data.get("total_profit", 0.0)), 2)
                profit_class = "positive" if profit >= 0 else "negative"
                rows_html += f"""<tr>
                    <td>{symbol}</td>
                    <td>{data.get("count", 0)}</td>
                    <td class="metric-value {profit_class}">${profit:.2f}</td>
                </tr>"""
            st.markdown(
                f"""
                <div class="card-shell">
                    <table class="health-table">
                        <thead><tr><th>Symbol</th><th>Positions</th><th>Profit (USD)</th></tr></thead>
                        <tbody>{rows_html}</tbody>
                    </table>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.info("No open trades at the moment.")

    with top_right:
        st.markdown("<div class='section-title'>Operations Snapshot</div>", unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="card-stack">
                <div class="mini-stat">
                    <div class="mini-label">Bot Process</div>
                    <div class="mini-value">{'<span style="color: var(--success);">RUNNING</span>' if bot_status_live['running'] else '<span style="color: var(--danger);">STOPPED</span>'}</div>
                    <div class="mini-meta">{f"PID {bot_status_live['pid']}" if bot_status_live['running'] else 'No active process'}</div>
                </div>
                <div class="mini-stat">
                    <div class="mini-label">UI Launcher</div>
                    <div class="mini-value">{'<span style="color: var(--success);">RUNNING</span>' if ui_status_live['running'] else '<span style="color: var(--danger);">STOPPED</span>'}</div>
                    <div class="mini-meta">{f"PID {ui_status_live['pid']}" if ui_status_live['running'] else 'No active launcher'}</div>
                </div>
                <div class="mini-stat">
                    <div class="mini-label">Control State</div>
                    <div class="mini-value">{get_bot_state().upper()}</div>
                    <div class="mini-meta">Managed from Settings & Control</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

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
        )
        fcm_service_ready = Path(fcm_service_path).exists()
        push_ready = fcm_tokens_ready and fcm_service_ready

        st.markdown(
            f"""
            <div class="card-shell">
                <div class="panel-title">Health Check</div>
                <table class="health-table">
                    <thead><tr><th>Component</th><th>Status</th><th>Details</th></tr></thead>
                    <tbody>
                        <tr>
                            <td>MT5 Session</td>
                            <td><span class="pill success">OK</span></td>
                            <td>Account {account_data['login']}</td>
                        </tr>
                        <tr>
                            <td>Telegram</td>
                            <td><span class="pill {'success' if telegram_ready else 'warn'}">{'READY' if telegram_ready else 'NOT SET'}</span></td>
                            <td>Alert channel</td>
                        </tr>
                        <tr>
                            <td>Push (FCM)</td>
                            <td><span class="pill {'success' if push_ready else 'warn'}">{'READY' if push_ready else 'NOT SET'}</span></td>
                            <td>Device token + service account</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div class='section-title'>Control Guidance</div>", unsafe_allow_html=True)
    info_cols = st.columns(3)
    info_cols[0].markdown(
        """
        <div class="card-shell compact">
            <div class="panel-title">Dashboard</div>
            <div class="panel-subtitle">Live operational view for equity, target progress, and exposure.<div style="margin-top:8px;color:var(--accent);font-size:12px;">View dashboard →</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    info_cols[1].markdown(
        """
        <div class="card-shell compact">
            <div class="panel-title">Strategy</div>
            <div class="panel-subtitle">Check the last loop, current bias, and why the bot traded or skipped.<div style="margin-top:8px;color:var(--accent);font-size:12px;">Open strategy desk →</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    info_cols[2].markdown(
        """
        <div class="card-shell compact">
            <div class="panel-title">Settings & Control</div>
            <div class="panel-subtitle">Change risk settings, launch/stop processes, and manage integrations.<div style="margin-top:8px;color:var(--accent);font-size:12px;">Go to settings →</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # NOTE:
    # Do not auto-refresh / rerun the entire dashboard page.
    # The bot loop updates are expected to be driven by the backend on its own cadence (≈30s),
    # and the live loop feed should refresh independently on its dedicated page/component.
