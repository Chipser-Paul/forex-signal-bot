import streamlit as st  # pyright: ignore[reportMissingImports]

from utils.session_manager import save_session, load_session, clear_session
from utils.mt5_connector import connect_mt5, shutdown_mt5


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

    session = load_session()
    if session:
        st.markdown(
            f"""
            <div class="card-shell" style="border-left: 4px solid var(--success);">
                <div class="panel-title">Active Session</div>
                <div class="mini-value">{session.get('login')}</div>
                <div class="mini-meta">Server: {session.get('server')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button("Logout", width="stretch"):
                clear_session()
                shutdown_mt5()
                st.session_state["page"] = "login"
                st.stop()
        with col2:
            st.info("Session is active. Go to Dashboard to monitor trades.")
        return True

    st.markdown("<div class='section-title'>Credentials</div>", unsafe_allow_html=True)
    with st.form("login_form"):
        col1, col2 = st.columns(2)
        with col1:
            login = st.text_input("Login ID", placeholder="Account number")
            server = st.text_input("Server", placeholder="Broker server name")
        with col2:
            password = st.text_input("Password", type="password")
            account_name = st.text_input("Account Label (optional)", placeholder="My Live Account")
        submit = st.form_submit_button("Connect MT5")

        if submit:
            if not login or not password or not server:
                st.error("Please fill in all required fields.")
                return False

            st.info("Connecting to MT5...")
            account_data, error = connect_mt5(login, password, server)

            if account_data:
                # Default trading settings
                capital = 1000.0
                lock_profit = 5.0
                daily_target_pct = 1.0
                lock_pct = (lock_profit / capital) * 100.0

                save_session(
                    login=login,
                    password=password,
                    server=server,
                    account=str(account_data.get("login", "")),
                    broker=str(account_data.get("server", "")),
                    capital=capital,
                    daily_target_pct=daily_target_pct,
                    lock_profit=lock_profit,
                    lock_pct=lock_pct,
                    lock_profit_pct=lock_pct,
                    account_label=account_name or "",
                )

                st.success(f"Login successful. Welcome, {account_data.get('name', 'Trader')}.")
                shutdown_mt5()
                st.session_state["page"] = "dashboard"
                st.stop()

            st.error(f"Login failed: {error}")
            shutdown_mt5()

    st.markdown(
        """
        <div class="card-shell">
            <div class="panel-title">Security Note</div>
            <div class="panel-subtitle">Credentials are stored in a local session file on this machine.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    return False
