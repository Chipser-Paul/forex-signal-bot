from __future__ import annotations

import streamlit as st  # pyright: ignore[reportMissingImports]

from utils.ai_assistant import load_analytics_details, load_analytics_overview


def analytics_page() -> None:
    st.markdown(
        """
        <div class="app-hero">
            <h1>Performance Analytics</h1>
            <p>Database-backed breakdowns of no-trades, exits, conditions, and setup behavior.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    lookback = st.segmented_control(
        "Window",
        options=[1, 7, 30, 90],
        default=30,
        format_func=lambda value: f"{value} Days",
    )
    days = int(lookback or 30)
    overview = load_analytics_overview(limit_days=days)
    details = load_analytics_details(limit_days=days)

    closed_trades = str(int(overview.get("closed_trades") or 0))
    win_rate = float(overview.get("win_rate") or 0.0)
    net_pnl = float(overview.get("net_pnl") or 0.0)
    top_exit = str(overview.get("top_exit_reason") or "-")

    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.markdown(
        f'<div class="metric-card"><div class="metric-label">Closed Trades</div>'
        f'<div class="metric-value">{closed_trades}</div></div>',
        unsafe_allow_html=True,
    )
    wr_color = "var(--success)" if win_rate >= 50 else "var(--warn)" if win_rate >= 30 else "var(--danger)"
    metric2.markdown(
        f'<div class="metric-card"><div class="metric-label">Win Rate</div>'
        f'<div class="metric-value" style="color:{wr_color}">{win_rate:.2f}%</div></div>',
        unsafe_allow_html=True,
    )
    pnl_color = "var(--success)" if net_pnl >= 0 else "var(--danger)"
    metric3.markdown(
        f'<div class="metric-card"><div class="metric-label">Net P/L</div>'
        f'<div class="metric-value" style="color:{pnl_color}">${net_pnl:.2f}</div></div>',
        unsafe_allow_html=True,
    )
    metric4.markdown(
        f'<div class="metric-card"><div class="metric-label">Top Exit Reason</div>'
        f'<div class="metric-value" style="font-size:18px;">{top_exit}</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown("<div class='section-title'>Execution Friction</div>", unsafe_allow_html=True)
    left, right = st.columns(2)
    with left:
        st.markdown(
            """
            <div class="card-shell">
                <div class="panel-title">Top No-Trade Reasons</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.dataframe(
            details.get("no_trade_reasons", []) or [{"reason_code": "-", "count": 0}],
            width="stretch",
            hide_index=True,
        )
    with right:
        st.markdown(
            """
            <div class="card-shell">
                <div class="panel-title">Top Exit Reasons</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.dataframe(
            details.get("exit_reasons", []) or [{"reason": "-", "count": 0}],
            width="stretch",
            hide_index=True,
        )

    st.markdown("<div class='section-title'>Pattern Quality</div>", unsafe_allow_html=True)
    left, right = st.columns(2)
    with left:
        st.markdown(
            """
            <div class="card-shell">
                <div class="panel-title">Condition Performance</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.dataframe(
            details.get("condition_performance", []) or [{"name": "-", "trades": 0, "wins": 0, "win_rate": 0.0, "net_pnl": 0.0}],
            width="stretch",
            hide_index=True,
        )
    with right:
        st.markdown(
            """
            <div class="card-shell">
                <div class="panel-title">Setup Performance</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.dataframe(
            details.get("setup_performance", []) or [{"name": "-", "trades": 0, "wins": 0, "win_rate": 0.0, "net_pnl": 0.0}],
            width="stretch",
            hide_index=True,
        )

    st.markdown("<div class='section-title'>Loop Environment</div>", unsafe_allow_html=True)
    st.dataframe(
        details.get("condition_loop_counts", []) or [{"condition": "-", "loops": 0}],
        width="stretch",
        hide_index=True,
    )

    with st.expander("Raw Analytics Payload", expanded=False):
        st.json({"overview": overview, "details": details})
    st.caption("Debug payload showing raw overview and details dictionaries from load_analytics_* functions.")
