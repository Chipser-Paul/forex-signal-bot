from __future__ import annotations

from datetime import datetime

import streamlit as st  # pyright: ignore[reportMissingImports]

from utils.ai_assistant import (
    ANALYST_SYSTEM_PROMPT,
    CHAT_AGENT_SYSTEM_PROMPT,
    build_chat_context,
    build_daily_summary_prompt,
    build_no_trade_prompt,
    build_trade_prompt,
    load_recent_no_trade_blocks,
    load_recent_trade_reviews,
)
from utils.groq_client import generate_chat as groq_generate_chat
from utils.groq_client import generate_text as groq_generate_text
from utils.groq_client import groq_status
from utils.ollama_client import generate_chat as ollama_generate_chat
from utils.ollama_client import generate_text, list_models, ollama_status


def _default_day() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def _preferred_model(models: list[str]) -> str:
    preferred = [
        "qwen2.5:0.5b",
        "qwen2.5:1.5b",
        "tinyllama",
        "gemma3:1b",
    ]
    for name in preferred:
        if name in models:
            return name
    return models[0] if models else "gemma3:1b"


def _generate_response(
    *,
    provider: str,
    model_name: str,
    prompt: str,
    temperature: float,
) -> str:
    if provider == "Groq":
        return groq_generate_text(
            model=model_name,
            prompt=prompt,
            system=ANALYST_SYSTEM_PROMPT,
            temperature=temperature,
            max_tokens=360,
            timeout=45,
        )
    return generate_text(
        model=model_name,
        prompt=prompt,
        system=ANALYST_SYSTEM_PROMPT,
        temperature=temperature,
        num_predict=360,
        timeout=180,
    )


def _generate_chat_response(
    *,
    provider: str,
    model_name: str,
    messages: list[dict[str, str]],
    temperature: float,
) -> str:
    if provider == "Groq":
        return groq_generate_chat(
            model=model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=420,
            timeout=45,
        )
    return ollama_generate_chat(
        model=model_name,
        messages=messages,
        temperature=temperature,
        num_predict=420,
        timeout=180,
    )


def ai_page() -> None:
    st.markdown(
        """
        <div class="app-hero">
            <h1>AI Copilot</h1>
            <p>Use Groq or Ollama to review trades, explain skipped setups, summarize a day, and chat with your bot's history.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    ollama_ready, ollama_msg = ollama_status()
    groq_ready, groq_msg = groq_status()
    models = list_models()
    provider_options = ["Ollama", "Groq"]

    with st.sidebar:
        st.markdown(
            """
            <div class="sidebar-card">
                <div class="sidebar-title">Local LLM</div>
                <div style="color: var(--text-2); font-size: 12px;">Uses Ollama on this laptop, no cloud API required.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        provider = st.selectbox("Provider", provider_options, index=1 if groq_ready else 0)

        if provider == "Groq":
            if groq_ready:
                st.markdown(f'<span class="pill success">{groq_msg}</span>', unsafe_allow_html=True)
            else:
                st.markdown(f'<span class="pill warn">{groq_msg}</span>', unsafe_allow_html=True)
            groq_models = [
                "llama-3.1-8b-instant",
                "llama-3.3-70b-versatile",
                "meta-llama/llama-4-scout-17b-16e-instruct",
            ]
            model_name = st.selectbox("Model", groq_models, index=0)
        else:
            if ollama_ready:
                st.markdown(f'<span class="pill success">{ollama_msg}</span>', unsafe_allow_html=True)
            else:
                st.markdown(f'<span class="pill warn">{ollama_msg}</span>', unsafe_allow_html=True)
            default_model = _preferred_model(models)
            options = models or [default_model]
            model_name = st.selectbox(
                "Model",
                options,
                index=options.index(default_model) if default_model in options else 0,
            )
        temperature = st.slider("Temperature", 0.0, 1.0, 0.2, 0.1)
        st.caption("Lower temperature keeps analysis tighter and more factual.")
        st.caption("Groq is best for speed. Ollama stays available as local fallback.")

    metric1, metric2, metric3 = st.columns(3)
    metric1.markdown(
        """
        <div class="card-shell compact" style="border-left: 4px solid var(--accent);">
            <div class="panel-title">Trade Review</div>
            <div class="panel-subtitle">Audit a closed trade against your SMC logic and exit behavior.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    metric2.markdown(
        """
        <div class="card-shell compact" style="border-left: 4px solid var(--accent-2);">
            <div class="panel-title">No-Trade Explainer</div>
            <div class="panel-subtitle">Understand exactly which rule blocked an entry and whether it was healthy.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    metric3.markdown(
        """
        <div class="card-shell compact" style="border-left: 4px solid var(--success);">
            <div class="panel-title">Chat Agent</div>
            <div class="panel-subtitle">Ask natural-language questions about recent trades, exits, and skipped setups.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    trade_tab, skip_tab, daily_tab, chat_tab = st.tabs(
        ["Trade Review", "No-Trade Explainer", "Daily Summary", "Chat Agent"]
    )

    with trade_tab:
        trade_reviews = load_recent_trade_reviews(limit=40)
        if not trade_reviews:
            st.info("No closed trade journal entries found yet.")
        else:
            trade_options = {item["label"]: item for item in trade_reviews}
            trade_label = st.selectbox("Closed Trade", list(trade_options.keys()))
            trade = trade_options[trade_label]

            col1, col2 = st.columns(2)
            with col1:
                st.metric("P/L", f"{float(trade['close_pnl'] or 0.0):.2f}")
                st.caption(f"Reason: {trade['close_reason']}")
            with col2:
                st.metric("Setup R:R", f"{float(trade['rr'] or 0.0):.2f}")
                st.caption(
                    f"{str(trade['direction']).upper()} | {trade['symbol']} | Ticket {trade['ticket']}"
                )

            with st.expander("Trade context payload", expanded=False):
                st.json(trade)

            if st.button("Analyze Trade", key="analyze_trade", width="stretch"):
                if provider == "Groq" and not groq_ready:
                    st.error("Groq is not ready. Set GROQ_API_KEY first.")
                elif provider == "Ollama" and not ollama_ready:
                    st.error("Ollama is not available. Start it first.")
                else:
                    try:
                        with st.spinner("Analyzing trade..."):
                            prompt = build_trade_prompt(trade)
                            answer = _generate_response(
                                provider=provider,
                                model_name=model_name,
                                prompt=prompt,
                                temperature=temperature,
                            )
                        st.markdown(answer or "No response from the local model.")
                    except Exception as exc:
                        st.error(f"{provider} request failed: {exc}")

    with skip_tab:
        blocks = load_recent_no_trade_blocks(limit=30)
        if not blocks:
            st.info("No recent no-trade blocks found in `logs/ui_bot.log`.")
        else:
            block_options = {item["label"]: item for item in blocks}
            block_label = st.selectbox("No-Trade Loop", list(block_options.keys()))
            block = block_options[block_label]

            st.caption(f"Latest reason: {block['reason']}")
            st.code(block["raw_block"], language="text")

            if st.button("Explain No-Trade", key="analyze_no_trade", width="stretch"):
                if provider == "Groq" and not groq_ready:
                    st.error("Groq is not ready. Set GROQ_API_KEY first.")
                elif provider == "Ollama" and not ollama_ready:
                    st.error("Ollama is not available. Start it first.")
                else:
                    try:
                        with st.spinner("Explaining skipped trade..."):
                            prompt = build_no_trade_prompt(block)
                            answer = _generate_response(
                                provider=provider,
                                model_name=model_name,
                                prompt=prompt,
                                temperature=temperature,
                            )
                        st.markdown(answer or "No response from the local model.")
                    except Exception as exc:
                        st.error(f"{provider} request failed: {exc}")

    with daily_tab:
        day = st.text_input("UTC day", value=_default_day(), help="Format: YYYY-MM-DD")
        if st.button("Summarize Day", key="daily_summary", width="stretch"):
            if provider == "Groq" and not groq_ready:
                st.error("Groq is not ready. Set GROQ_API_KEY first.")
            elif provider == "Ollama" and not ollama_ready:
                st.error("Ollama is not available. Start it first.")
            else:
                try:
                    with st.spinner("Summarizing the day..."):
                        prompt = build_daily_summary_prompt(day)
                        answer = _generate_response(
                            provider=provider,
                            model_name=model_name,
                            prompt=prompt,
                            temperature=temperature,
                        )
                    st.markdown(answer or "No response from the local model.")
                except Exception as exc:
                    st.error(f"{provider} request failed: {exc}")

    with chat_tab:
        st.markdown("Ask questions about recent trades, skipped setups, and bot behavior.")

        if "ai_chat_messages" not in st.session_state:
            st.session_state["ai_chat_messages"] = [
                {
                    "role": "assistant",
                    "content": (
                        "I’m ready. Ask me about recent performance, skipped trades, setup quality, "
                        "or what the bot seems to be doing well or badly."
                    ),
                }
            ]

        if st.button("Clear Chat", key="clear_ai_chat"):
            st.session_state["ai_chat_messages"] = [
                {
                    "role": "assistant",
                    "content": (
                        "Chat cleared. Ask me about trades, no-trade decisions, risk management, "
                        "or recent patterns in the bot."
                    ),
                }
            ]

        for message in st.session_state["ai_chat_messages"]:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        user_prompt = st.chat_input("Ask the trading copilot a question")
        if user_prompt:
            if provider == "Groq" and not groq_ready:
                st.error("Groq is not ready. Set GROQ_API_KEY first.")
            elif provider == "Ollama" and not ollama_ready:
                st.error("Ollama is not available. Start it first.")
            else:
                st.session_state["ai_chat_messages"].append({"role": "user", "content": user_prompt})
                with st.chat_message("user"):
                    st.markdown(user_prompt)

                context = build_chat_context()
                messages = [
                    {"role": "system", "content": CHAT_AGENT_SYSTEM_PROMPT},
                    {
                        "role": "system",
                        "content": (
                            "Recent context:\n"
                            f"{context}\n\n"
                            "Use this recent context when helpful, but say clearly if the answer "
                            "needs data that is not present."
                        ),
                    },
                ]
                messages.extend(
                    {
                        "role": item["role"],
                        "content": item["content"],
                    }
                    for item in st.session_state["ai_chat_messages"][-8:]
                )

                try:
                    with st.chat_message("assistant"):
                        with st.spinner("Thinking..."):
                            answer = _generate_chat_response(
                                provider=provider,
                                model_name=model_name,
                                messages=messages,
                                temperature=temperature,
                            )
                        st.markdown(answer or "No response returned.")
                    st.session_state["ai_chat_messages"].append(
                        {"role": "assistant", "content": answer or "No response returned."}
                    )
                except Exception as exc:
                    st.error(f"{provider} request failed: {exc}")
