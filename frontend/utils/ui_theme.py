from __future__ import annotations

import streamlit as st  # pyright: ignore[reportMissingImports]


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

        :root {
            --bg-0: #070a12;
            --bg-1: #0b0f1a;
            --bg-2: #101827;
            --card: #0b1220;
            --card-2: #0f172a;
            --line: rgba(148, 163, 184, 0.18);
            --text-0: #f8fafc;
            --text-1: #e2e8f0;
            --text-2: #94a3b8;
            --accent: #f8d34f;
            --accent-2: #22d3ee;
            --success: #22c55e;
            --warn: #f97316;
            --danger: #ef4444;
        }

        html, body, [class*="css"]  {
            font-family: "IBM Plex Sans", sans-serif;
            color: var(--text-0);
        }

        .stApp {
            background:
                radial-gradient(900px 600px at 10% -10%, rgba(248, 211, 79, 0.22), transparent 55%),
                radial-gradient(900px 600px at 90% 8%, rgba(34, 211, 238, 0.18), transparent 55%),
                repeating-linear-gradient(
                    135deg,
                    rgba(248, 211, 79, 0.05) 0px,
                    rgba(248, 211, 79, 0.05) 1px,
                    transparent 1px,
                    transparent 14px
                ),
                linear-gradient(180deg, var(--bg-0) 0%, var(--bg-1) 45%, var(--bg-2) 100%);
        }

        [data-testid="stSidebar"] {
            background:
                radial-gradient(600px 300px at 10% -20%, rgba(248, 211, 79, 0.18), transparent 60%),
                radial-gradient(500px 300px at 90% 0%, rgba(34, 211, 238, 0.12), transparent 60%),
                linear-gradient(180deg, #070a12 0%, #0b1220 60%, #0b0f1a 100%);
            border-right: 1px solid rgba(248, 211, 79, 0.25);
            box-shadow: inset -1px 0 0 rgba(248, 211, 79, 0.08);
        }

        [data-testid="stSidebar"] > div {
            background: transparent;
        }

        /* =============================================
           SIDEBAR CUSTOM NAVIGATION (Radio restyle)
           ============================================= */

        /* Hide radio circles */
        [data-testid="stSidebar"] [data-testid="stRadio"] input[type="radio"] {
            opacity: 0;
            position: absolute;
            width: 0;
            height: 0;
            margin: 0;
            padding: 0;
        }

        /* Radio group as vertical nav list */
        [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] {
            display: flex;
            flex-direction: column;
            gap: 1px;
            padding: 0;
            background: transparent !important;
            border: none !important;
        }

        /* Hide Streamlit's own collapsed widget label (renders as empty 44px block otherwise) */
        [data-testid="stSidebar"] [data-testid="stRadio"] > label {
            display: none !important;
        }

        /* Each nav item label */
        [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label {
            display: flex !important;
            align-items: center !important;
            padding: 11px 14px !important;
            border-radius: 10px !important;
            cursor: pointer;
            transition: all 0.2s ease !important;
            background: transparent !important;
            border: none !important;
            border-left: 3px solid transparent !important;
            color: var(--text-1) !important;
            font-weight: 500 !important;
            font-size: 14px;
            position: relative !important;
            min-height: 44px;
            margin: 0 !important;
            gap: 0;
        }

        /* Hide the radio indicator div */
        [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label > div:first-child {
            display: none !important;
        }

        /* Hover state */
        [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label:hover {
            background: rgba(248, 211, 79, 0.06) !important;
            border-left-color: rgba(248, 211, 79, 0.25) !important;
            color: var(--text-0) !important;
        }

        /* Active (checked) nav item */
        [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) {
            background: linear-gradient(90deg, rgba(248, 211, 79, 0.10), transparent) !important;
            border-left-color: var(--accent) !important;
            color: var(--accent) !important;
            font-weight: 600 !important;
        }

        /* Icon pseudo-element for ALL nav items */
        [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label::before {
            content: "";
            display: inline-block !important;
            width: 20px !important;
            height: 20px !important;
            margin-right: 13px !important;
            flex-shrink: 0 !important;
            background-color: var(--text-2);
            mask-size: contain;
            mask-repeat: no-repeat;
            mask-position: center;
            -webkit-mask-size: contain;
            -webkit-mask-repeat: no-repeat;
            -webkit-mask-position: center;
            transition: background-color 0.2s ease;
        }

        /* Icon color on hover */
        [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label:hover::before {
            background-color: var(--text-0);
        }

        /* Icon color on active */
        [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked)::before {
            background-color: var(--accent) !important;
        }

        /* Individual icons per nav item (1=Login, 2=Dashboard, 3=Strategy, 4=Analytics, 5=AI Copilot, 6=Settings) */
        [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label:nth-child(1)::before {
            mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4'/%3E%3Cpolyline points='10,17 15,12 10,7'/%3E%3Cline x1='15' y1='12' x2='3' y2='12'/%3E%3C/svg%3E");
            -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4'/%3E%3Cpolyline points='10,17 15,12 10,7'/%3E%3Cline x1='15' y1='12' x2='3' y2='12'/%3E%3C/svg%3E");
        }
        [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label:nth-child(2)::before {
            mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='3' y='12' width='4' height='9' rx='1'/%3E%3Crect x='10' y='5' width='4' height='16' rx='1'/%3E%3Crect x='17' y='8' width='4' height='13' rx='1'/%3E%3C/svg%3E");
            -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='3' y='12' width='4' height='9' rx='1'/%3E%3Crect x='10' y='5' width='4' height='16' rx='1'/%3E%3Crect x='17' y='8' width='4' height='13' rx='1'/%3E%3C/svg%3E");
        }
        [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label:nth-child(3)::before {
            mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round'%3E%3Ccircle cx='12' cy='12' r='8'/%3E%3Cline x1='12' y1='2' x2='12' y2='6'/%3E%3Cline x1='12' y1='18' x2='12' y2='22'/%3E%3Cline x1='2' y1='12' x2='6' y2='12'/%3E%3Cline x1='18' y1='12' x2='22' y2='12'/%3E%3Ccircle cx='12' cy='12' r='2' fill='currentColor' stroke='none'/%3E%3C/svg%3E");
            -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round'%3E%3Ccircle cx='12' cy='12' r='8'/%3E%3Cline x1='12' y1='2' x2='12' y2='6'/%3E%3Cline x1='12' y1='18' x2='12' y2='22'/%3E%3Cline x1='2' y1='12' x2='6' y2='12'/%3E%3Cline x1='18' y1='12' x2='22' y2='12'/%3E%3Ccircle cx='12' cy='12' r='2' fill='currentColor' stroke='none'/%3E%3C/svg%3E");
        }
        [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label:nth-child(4)::before {
            mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='3,17 9,11 13,13 21,5'/%3E%3Cpolyline points='17,5 21,5 21,9'/%3E%3C/svg%3E");
            -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='3,17 9,11 13,13 21,5'/%3E%3Cpolyline points='17,5 21,5 21,9'/%3E%3C/svg%3E");
        }
        [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label:nth-child(5)::before {
            mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 3l1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5z'/%3E%3Cline x1='19' y1='17' x2='19' y2='21'/%3E%3Cline x1='17' y1='19' x2='21' y2='19'/%3E%3C/svg%3E");
            -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 3l1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5z'/%3E%3Cline x1='19' y1='17' x2='19' y2='21'/%3E%3Cline x1='17' y1='19' x2='21' y2='19'/%3E%3C/svg%3E");
        }
        [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label:nth-child(6)::before {
            mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round'%3E%3Cline x1='4' y1='6' x2='10' y2='6'/%3E%3Cline x1='14' y1='6' x2='20' y2='6'/%3E%3Ccircle cx='12' cy='6' r='2'/%3E%3Cline x1='4' y1='18' x2='10' y2='18'/%3E%3Cline x1='14' y1='18' x2='20' y2='18'/%3E%3Ccircle cx='12' cy='18' r='2'/%3E%3Cline x1='20' y1='12' x2='14' y2='12'/%3E%3Cline x1='10' y1='12' x2='4' y2='12'/%3E%3Ccircle cx='12' cy='12' r='2'/%3E%3C/svg%3E");
            -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round'%3E%3Cline x1='4' y1='6' x2='10' y2='6'/%3E%3Cline x1='14' y1='6' x2='20' y2='6'/%3E%3Ccircle cx='12' cy='6' r='2'/%3E%3Cline x1='4' y1='18' x2='10' y2='18'/%3E%3Cline x1='14' y1='18' x2='20' y2='18'/%3E%3Ccircle cx='12' cy='18' r='2'/%3E%3Cline x1='20' y1='12' x2='14' y2='12'/%3E%3Cline x1='10' y1='12' x2='4' y2='12'/%3E%3Ccircle cx='12' cy='12' r='2'/%3E%3C/svg%3E");
        }

        /* Sidebar divider between nav and cards */
        .nav-divider {
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(248, 211, 79, 0.25), transparent);
            margin: 16px 0;
        }

        .sidebar-title {
            font-family: "Space Grotesk", sans-serif;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.18em;
            color: var(--text-2);
            margin-bottom: 6px;
        }

        [data-testid="stSidebar"] * {
            color: var(--text-0);
        }

        /* Sidebar brand header */
        .sidebar-brand {
            font-family: "Space Grotesk", sans-serif;
            font-size: 22px;
            font-weight: 700;
            letter-spacing: 0.06em;
            color: var(--text-0);
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 4px 0 0 0;
        }

        .brand-icon {
            color: var(--accent);
            font-size: 26px;
            line-height: 1;
        }

        .sidebar-subtitle {
            font-size: 12px;
            color: var(--text-2);
            letter-spacing: 0.12em;
            text-transform: uppercase;
            margin: -2px 0 18px 0;
            padding-left: 2px;
        }

        /* Navigation section labels */
        .nav-section-label {
            font-family: "Space Grotesk", sans-serif;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.18em;
            color: var(--text-2);
            margin: 4px 0 6px 0;
            padding: 0 2px;
            opacity: 0.7;
        }

        /* Session status card */
        .sidebar-card {
            background: rgba(2, 6, 23, 0.72);
            border: 1px solid rgba(248, 211, 79, 0.18);
            border-radius: 12px;
            padding: 12px 14px;
            margin-bottom: 10px;
            box-shadow: inset 0 0 18px rgba(248, 211, 79, 0.05);
        }

        .status-row {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 4px;
        }

        .status-dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--success);
            box-shadow: 0 0 8px rgba(34, 197, 94, 0.6);
            animation: pulse-dot 1.8s ease-in-out infinite;
            flex-shrink: 0;
        }

        .status-dot.offline {
            background: var(--warn);
            box-shadow: 0 0 8px rgba(245, 158, 11, 0.5);
            animation: none;
        }

        @keyframes pulse-dot {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.5; transform: scale(0.85); }
        }

        .session-user {
            color: var(--text-2);
            font-size: 13px;
            margin-top: 2px;
            padding-left: 18px;
        }

        .session-user strong {
            color: var(--text-0);
            font-weight: 600;
        }

        /* Quick Snapshot grid */
        .snapshot-grid {
            display: grid;
            grid-template-columns: 1fr auto 1fr auto 1fr;
            align-items: center;
            background: rgba(2, 6, 23, 0.72);
            border: 1px solid rgba(248, 211, 79, 0.18);
            border-radius: 12px;
            padding: 10px 12px;
            margin-bottom: 10px;
            box-shadow: inset 0 0 18px rgba(248, 211, 79, 0.05);
        }

        .snapshot-item {
            text-align: center;
        }

        .snapshot-label {
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 0.14em;
            color: var(--text-2);
            margin-bottom: 2px;
        }

        .snapshot-value {
            font-family: "Space Grotesk", sans-serif;
            font-size: 17px;
            font-weight: 700;
            color: var(--text-0);
            line-height: 1.2;
        }

        .snapshot-vsep {
            width: 1px;
            height: 32px;
            background: linear-gradient(180deg, transparent, rgba(248, 211, 79, 0.3), transparent);
        }

        .app-hero,
        .hero-panel {
            background: linear-gradient(135deg, rgba(248, 211, 79, 0.18), rgba(34, 211, 238, 0.12));
            border: 1px solid rgba(248, 211, 79, 0.35);
            border-radius: 18px;
            padding: 22px 24px;
            margin-bottom: 18px;
            box-shadow: 0 0 30px rgba(248, 211, 79, 0.18);
        }

        .eyebrow {
            color: var(--accent);
            font-size: 0.8rem;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            margin-bottom: 0.35rem;
            font-weight: 700;
        }

        .app-hero h1,
        .hero-panel h1 {
            font-family: "Space Grotesk", sans-serif;
            font-size: 28px;
            margin-bottom: 6px;
        }

        .app-hero p,
        .hero-panel p {
            color: var(--text-2);
            margin: 0;
        }

        .card {
            background: linear-gradient(180deg, rgba(2, 6, 23, 0.95), rgba(15, 23, 42, 0.95));
            border: 1px solid rgba(148, 163, 184, 0.2);
            border-radius: 16px;
            padding: 16px 18px;
            margin-bottom: 14px;
            box-shadow: 0 0 24px rgba(15, 23, 42, 0.6);
        }

        .card h3 {
            font-family: "Space Grotesk", sans-serif;
            margin: 0 0 6px 0;
            font-size: 16px;
            color: var(--text-1);
        }

        .card .value {
            font-size: 22px;
            font-weight: 600;
            color: var(--text-0);
        }

        .card .meta {
            font-size: 13px;
            color: var(--text-2);
        }

        .pill {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.02em;
        }

        .pill.success { background: rgba(34, 197, 94, 0.2); color: var(--success); }
        .pill.warn { background: rgba(245, 158, 11, 0.2); color: var(--warn); }
        .pill.danger { background: rgba(239, 68, 68, 0.2); color: var(--danger); }
        .pill.info { background: rgba(248, 211, 79, 0.2); color: var(--accent); }

        .section-title {
            font-family: "Space Grotesk", sans-serif;
            font-size: 18px;
            margin-top: 8px;
            margin-bottom: 8px;
        }

        .stButton > button {
            border-radius: 12px;
            border: 1px solid rgba(248, 211, 79, 0.6);
            background: linear-gradient(180deg, rgba(248, 211, 79, 0.35), rgba(248, 211, 79, 0.12));
            color: #0b0f1a;
            font-weight: 700;
            font-family: "Space Grotesk", sans-serif;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }

        .stButton > button:hover {
            border-color: rgba(248, 211, 79, 0.9);
            color: #0b0f1a;
        }

        .stTextInput > div > div > input,
        .stNumberInput > div > div > input {
            border-radius: 10px;
            background-color: rgba(7, 10, 18, 0.9);
            border: 1px solid rgba(248, 211, 79, 0.3);
            color: var(--text-0);
        }

        .stSlider > div {
            color: var(--text-0);
        }

        .summary-bar {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px;
            margin-bottom: 16px;
        }

        .summary-tile {
            background: linear-gradient(180deg, rgba(2, 6, 23, 0.98), rgba(15, 23, 42, 0.98));
            border: 1px solid rgba(248, 211, 79, 0.4);
            border-radius: 14px;
            padding: 14px 16px;
            box-shadow: inset 0 0 22px rgba(248, 211, 79, 0.08);
        }

        .summary-label {
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            color: var(--text-2);
        }

        .summary-value {
            font-size: 22px;
            font-weight: 700;
            color: var(--text-0);
        }

        .summary-meta {
            font-size: 12px;
            color: var(--text-2);
        }

        .hero-split {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 14px;
            margin-bottom: 18px;
        }

        .hero-stat {
            background: linear-gradient(180deg, rgba(2, 6, 23, 0.92), rgba(15, 23, 42, 0.96));
            border: 1px solid rgba(248, 211, 79, 0.22);
            border-radius: 18px;
            padding: 18px;
            box-shadow: 0 22px 60px rgba(2, 6, 23, 0.35);
        }

        .hero-stat-label {
            font-family: "Space Grotesk", sans-serif;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.14em;
            color: var(--text-2);
            margin-bottom: 8px;
        }

        .hero-stat-value {
            font-family: "Space Grotesk", sans-serif;
            font-size: 30px;
            font-weight: 700;
            color: var(--text-0);
            line-height: 1.1;
        }

        .hero-stat-meta {
            margin-top: 6px;
            color: var(--text-2);
            font-size: 13px;
        }

        .card-shell {
            background: linear-gradient(180deg, rgba(2, 6, 23, 0.95), rgba(15, 23, 42, 0.96));
            border: 1px solid rgba(148, 163, 184, 0.14);
            border-radius: 18px;
            padding: 16px 18px;
            margin-bottom: 12px;
            box-shadow: 0 18px 45px rgba(2, 6, 23, 0.24);
        }

        .card-shell.compact {
            min-height: 108px;
        }

        .panel-title {
            font-family: "Space Grotesk", sans-serif;
            font-size: 16px;
            font-weight: 700;
            color: var(--text-1);
            margin-bottom: 4px;
        }

        .panel-subtitle {
            color: var(--text-2);
            font-size: 13px;
            line-height: 1.5;
        }

        .card-stack {
            display: grid;
            gap: 12px;
        }

        .mini-stat-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 12px;
        }

        .mini-stat {
            background: rgba(10, 15, 26, 0.8);
            border: 1px solid rgba(248, 211, 79, 0.12);
            border-radius: 14px;
            padding: 14px;
        }

        .mini-label {
            color: var(--text-2);
            font-size: 11px;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            margin-bottom: 6px;
        }

        .mini-value {
            color: var(--text-0);
            font-family: "Space Grotesk", sans-serif;
            font-size: 20px;
            font-weight: 700;
            line-height: 1.15;
        }

        .mini-meta {
            margin-top: 4px;
            color: var(--text-2);
            font-size: 12px;
        }

        .meta-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 10px;
            padding: 6px 0;
            color: var(--text-1);
            font-size: 13px;
            border-bottom: 1px dashed rgba(148, 163, 184, 0.12);
        }

        .meta-row:last-child {
            border-bottom: 0;
        }

        .meta-row strong {
            color: var(--text-0);
            font-family: "Space Grotesk", sans-serif;
        }

        [data-testid="stMetric"] {
            background: linear-gradient(180deg, rgba(2, 6, 23, 0.88), rgba(15, 23, 42, 0.94));
            border: 1px solid rgba(248, 211, 79, 0.14);
            border-radius: 16px;
            padding: 12px 14px;
        }

        [data-testid="stTabs"] [role="tablist"] {
            gap: 8px;
        }

        [data-testid="stTabs"] [role="tab"] {
            border-radius: 999px;
            background: rgba(2, 6, 23, 0.78);
            border: 1px solid rgba(248, 211, 79, 0.18);
            padding: 8px 16px;
        }

        [data-testid="stTabs"] [aria-selected="true"] {
            background: rgba(248, 211, 79, 0.16);
            border-color: rgba(248, 211, 79, 0.55);
        }

        [data-testid="stSegmentedControl"] {
            margin-bottom: 12px;
        }

        /* Horizontal radio (symbol selector on Strategy page) — main area only */
        section.main [data-testid="stRadio"][role="radiogroup"] {
            display: flex;
            flex-direction: row;
            gap: 6px;
            background: rgba(2, 6, 23, 0.5);
            border-radius: 12px;
            padding: 4px;
            border: 1px solid rgba(248, 211, 79, 0.12);
        }

        section.main [data-testid="stRadio"][role="radiogroup"] label {
            flex: 1;
            text-align: center;
            padding: 8px 16px !important;
            border-radius: 9px !important;
            cursor: pointer;
            transition: all 0.2s ease;
            color: var(--text-2) !important;
            font-weight: 500 !important;
            font-size: 13px;
            background: transparent !important;
            border: none !important;
            margin: 0 !important;
        }

        section.main [data-testid="stRadio"][role="radiogroup"] label:has(input:checked) {
            background: rgba(248, 211, 79, 0.15) !important;
            color: var(--accent) !important;
            font-weight: 700 !important;
            box-shadow: 0 2px 8px rgba(248, 211, 79, 0.1);
        }

        section.main [data-testid="stRadio"][role="radiogroup"] label:hover {
            color: var(--text-0) !important;
        }

        section.main [data-testid="stRadio"][role="radiogroup"] label > div:first-child {
            display: none !important;
        }

        /* Dashboard metric cards */
        .metric-row {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            margin-bottom: 12px;
        }

        .metric-card {
            flex: 1;
            min-width: 140px;
            background: linear-gradient(180deg, rgba(2, 6, 23, 0.95), rgba(15, 23, 42, 0.95));
            border: 1px solid rgba(148, 163, 184, 0.15);
            border-radius: 14px;
            padding: 14px 16px;
            box-shadow: 0 2px 12px rgba(0, 0, 0, 0.2);
        }

        .metric-label {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            color: var(--text-2);
            margin-bottom: 4px;
        }

        .metric-value {
            font-family: "Space Grotesk", sans-serif;
            font-size: 24px;
            font-weight: 700;
            color: var(--text-0);
            line-height: 1.2;
        }

        .metric-value.positive { color: var(--success); }
        .metric-value.negative { color: var(--danger); }
        .metric-value.warning { color: var(--warn); }

        /* Dashboard health check table */
        .health-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }

        .health-table th {
            text-align: left;
            padding: 8px 10px;
            color: var(--text-2);
            font-weight: 600;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            border-bottom: 1px solid rgba(148, 163, 184, 0.12);
        }

        .health-table td {
            padding: 8px 10px;
            border-bottom: 1px solid rgba(148, 163, 184, 0.06);
            color: var(--text-1);
        }

        .health-table tr:last-child td {
            border-bottom: none;
        }

        .health-table .status-ok { color: var(--success); }
        .health-table .status-fail { color: var(--danger); }

        /* DataTable / DataFrame styling */
        [data-testid="stDataFrame"] {
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid rgba(148, 163, 184, 0.12);
        }

        [data-testid="stDataFrame"] table {
            font-size: 13px;
        }

        /* Tabs styling */
        .stTabs [data-baseweb="tab-list"] {
            gap: 2px;
            background: rgba(2, 6, 23, 0.4);
            border-radius: 12px;
            padding: 4px;
            border: 1px solid rgba(148, 163, 184, 0.08);
        }

        .stTabs [data-baseweb="tab"] {
            border-radius: 9px;
            padding: 8px 18px;
            font-size: 13px;
            font-weight: 500;
            color: var(--text-2);
            transition: all 0.2s ease;
        }

        .stTabs [data-baseweb="tab"][aria-selected="true"] {
            background: rgba(248, 211, 79, 0.12);
            color: var(--accent);
            font-weight: 600;
        }

        .stTabs [data-baseweb="tab"]:hover {
            color: var(--text-0);
        }

        /* Expander styling */
        .streamlit-expanderHeader {
            font-weight: 600;
            color: var(--text-1);
            border-radius: 10px;
        }

        .streamlit-expanderContent {
            border: 1px solid rgba(148, 163, 184, 0.08);
            border-top: none;
            border-radius: 0 0 10px 10px;
            padding: 8px 12px;
        }

        /* Alert / Info boxes */
        .stAlert {
            border-radius: 12px;
            border: 1px solid rgba(148, 163, 184, 0.15);
        }

        /* Number input / text input */
        input[type="text"], input[type="number"], select, textarea {
            border-radius: 10px !important;
            border: 1px solid rgba(148, 163, 184, 0.2) !important;
            background: rgba(2, 6, 23, 0.6) !important;
            color: var(--text-0) !important;
        }

        input[type="text"]:focus, input[type="number"]:focus, select:focus, textarea:focus {
            border-color: rgba(248, 211, 79, 0.5) !important;
            box-shadow: 0 0 0 2px rgba(248, 211, 79, 0.1) !important;
        }

        /* Checkbox */
        .stCheckbox label {
            color: var(--text-1) !important;
        }

        /* Progress bar */
        .stProgress > div > div {
            background: linear-gradient(90deg, var(--accent), var(--accent-2)) !important;
            border-radius: 999px !important;
        }

        .stProgress > div {
            border-radius: 999px !important;
            background: rgba(148, 163, 184, 0.1) !important;
        }

        /* Select slider */
        [data-testid="stSelectSlider"] {
            padding: 8px 0;
        }

        /* Toast / notification styling */
        [data-baseweb="toast"] {
            background: var(--card) !important;
            border: 1px solid rgba(248, 211, 79, 0.3) !important;
            border-radius: 12px !important;
            color: var(--text-0) !important;
        }

        /* Multiselect */
        [data-baseweb="select"] > div {
            background: rgba(2, 6, 23, 0.6) !important;
            border: 1px solid rgba(148, 163, 184, 0.2) !important;
            border-radius: 10px !important;
            color: var(--text-0) !important;
        }

        /* Page transition */
        section.main > div {
            animation: fadeIn 0.3s ease;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(6px); }
            to { opacity: 1; transform: translateY(0); }
        }

        /* Custom scrollbar */
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: var(--bg-0); }
        ::-webkit-scrollbar-thumb { background: rgba(248, 211, 79, 0.3); border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: rgba(248, 211, 79, 0.5); }
        </style>
        """,
        unsafe_allow_html=True,
    )
