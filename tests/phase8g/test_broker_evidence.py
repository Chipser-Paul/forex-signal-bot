"""Phase 8G focused tests: broker-conditions evidence intake.

Synthetic/fictional fixtures only - no network, no MT5, no strategy
evaluation, no holdout access, and no owner evidence embedded in Git.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bot.acquisition import broker_evidence as be  # noqa: E402
from bot.acquisition.evidence_contracts import (  # noqa: E402
    EvidenceError,
    canonical_hash,
)
from bot.acquisition.evidence_store import EvidenceStoreError  # noqa: E402

# ---------------------------------------------------------------------------
# Synthetic transcript fixture (fictional, unmistakably non-real). It carries
# every marker the real classifier requires, plus URL-embedded digit runs and
# two rollover questions with no answer.
# ---------------------------------------------------------------------------

SYNTHETIC_TRANSCRIPT = "\r\n".join(
    [
        "Connecting you to one of our agents.",
        "Bot 13:15",
        "Chat transferred to FakeAgent",
        "For Standard MT5 XAUUSDm during 2024, please confirm: zero commission; "
        "historical swap-long/short values and change dates; rollover at 21:00 UTC; "
        "daytime/nighttime session times; margin rules.",
        "Here is the available information regarding XAUUSDm (Gold) on a Standard MT5 account:",
        "Spread/Commission: On Standard accounts, there is no fixed trading commission for XAUUSDm; "
        "instead, the trading cost is included in the spread. The spread is variable and depends "
        "on market conditions. Exness does not provide archived spread data by email.",
        "Swap: Swap is applied for positions held overnight, with a triple swap charged on Wednesdays. "
        "The swap schedule may change due to public or bank holidays. "
        "The actual swap rates for specific dates can be checked in your MT5 platform.",
        "Contract Conditions:",
        "Contract size: 100 troy ounces",
        "Pip size: 0.01",
        "Minimum trading volume: 0.01 lot",
        "Maximum trading volume: 200 lots (daytime), 20 lots (nighttime)",
        "Fixed margin requirement: 1:200 (0.5%)",
        "Hedged margin: 0%",
        "Market execution",
        "There is no ticket/reference number or record of an investigation or email sent.",
        "The Standard MT5 XAUUSDm pricing rules include a trading commission of "
        "5.5 USD for Zero accounts and 3.5 USD for Raw Spread accounts.",
        "Bot 13:50",
        "Chat started at 14:12",
        "I'm not quite sure if it'll stretch to 2024",
        "rollover at 21:00 UTC and Wednesday triple swap applied throughout 2024, "
        "or whether these are current conditions only",
        "Please also confirm whether the same rules applied; see "
        "https://get.exness.help/hc/en-us/articles/4405235684498-Instrument-trading-hours "
        "and https://example.org/calculator",
    ]
)


def _write_transcript(tmp_path: Path, text: str = SYNTHETIC_TRANSCRIPT, suffix: str = ".txt") -> Path:
    support = tmp_path / "Support"
    support.mkdir(parents=True, exist_ok=True)
    path = support / f"Exness_Support_2024_Conditions_2099-01-01{suffix}"
    path.write_text(text, encoding="utf-8")
    return path


def _transcript_file(tmp_path: Path) -> be.EvidenceFile:
    path = _write_transcript(tmp_path)
    return be.stat_evidence_file(path, "support_transcript")


def _claims(tmp_path: Path) -> list[be.BrokerClaim]:
    _, claims = be.load_transcript_claims(_write_transcript(tmp_path))
    return claims


def _screenshot(tmp_path: Path, name: str = "Exness_Standard_XAUUSDm_Specification_2099-01-01_01.png") -> dict:
    path = tmp_path / name
    path.write_bytes(b"\x89PNG-fixture")
    file = be.stat_evidence_file(path, "mt5_screenshot")
    return be.build_screenshot_record(
        file=file,
        ocr_note="synthetic OCR fixture",
        observed={
            "digits": "3",
            "swap_type": "In points",
            "swap_long": "-534.9",
            "swap_short": "0",
        },
        not_readable=(),
    )


def _spread_identity() -> tuple[str, str]:
    return (
        "evidence-observed_spread-v1-fake000000000000",
        "f" * 64,
    )


def _package(tmp_path: Path) -> dict:
    return be.build_broker_evidence_package(
        transcript_file=_transcript_file(tmp_path),
        claims=_claims(tmp_path),
        screenshots=[_screenshot(tmp_path)],
        observed_spread_package_id=_spread_identity()[0],
        observed_spread_canonical_sha256=_spread_identity()[1],
        margin_conflicts=[
            {
                "conflict_id": "fixture.conflict",
                "support_statement": "1:200 (0.5%)",
                "current_display": "1.0000000",
                "classification": "REJECTED_CONFLICTING",
                "resolution": "unresolved by design",
            }
        ],
    )


# ---------------------------------------------------------------------------
# Discovery + sensitive scanning
# ---------------------------------------------------------------------------


def test_transcript_discovery_hidden_txt_extension(tmp_path):
    path = _write_transcript(tmp_path, suffix="")
    resolved = be.discover_transcript_file(tmp_path, base_name=path.name)
    assert resolved == path.resolve()
    assert resolved.suffix == ""


def test_transcript_discovery_visible_txt_extension(tmp_path):
    path = _write_transcript(tmp_path, suffix=".txt")
    assert be.discover_transcript_file(tmp_path, base_name=path.stem) == path.resolve()


def test_transcript_discovery_missing_fails_closed(tmp_path):
    with pytest.raises(EvidenceError):
        be.discover_transcript_file(tmp_path, base_name="No_Such_Transcript")


def test_transcript_discovery_rejects_directory(tmp_path):
    support = tmp_path / "Support"
    (support / "Exness_Support_2024_Conditions_2099-01-01.txt").mkdir(parents=True)
    with pytest.raises(EvidenceError):
        be.discover_transcript_file(
            tmp_path, base_name="Exness_Support_2024_Conditions_2099-01-01"
        )


@pytest.mark.parametrize(
    "sensitive_text",
    [
        "reach me at owner@example.com anytime",
        "support PIN: 123456",
        "password: hunter2",
        "api_key: abc123",
        "account number 12345678 confirmed",
    ],
)
def test_sensitive_content_rejected(tmp_path, sensitive_text):
    with pytest.raises(EvidenceError):
        be.scan_for_sensitive_content(sensitive_text, "fixture")


def test_url_article_ids_are_not_account_numbers(tmp_path):
    be.scan_for_sensitive_content(
        "see https://get.exness.help/hc/en-us/articles/4405235684498-Instrument-trading-hours",
        "fixture",
    )


def test_agent_names_redacted_from_derived_quotes(tmp_path):
    file = _transcript_file(tmp_path)
    text = _write_transcript(tmp_path).read_text(encoding="utf-8").replace("FakeAgent", "Kuhlekonke")
    claims = be.classify_transcript(text, file)
    for claim in claims:
        assert "Kuhlekonke" not in claim.quote


def test_transcript_truncation_detected(tmp_path):
    truncated = SYNTHETIC_TRANSCRIPT.split("Chat started at 14:12")[0]
    path = _write_transcript(tmp_path, text=truncated)
    with pytest.raises(EvidenceError, match="truncated"):
        be.load_transcript_claims(path)


def test_evidence_file_hash_is_immutable_identity(tmp_path):
    file = _transcript_file(tmp_path)
    again = be.stat_evidence_file(file.path, "support_transcript")
    assert again.sha256 == file.sha256 == be.sha256_file(file.path)


def test_evidence_file_rejects_symlink(tmp_path):
    real = _write_transcript(tmp_path)
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(real)
    except OSError:
        pytest.skip("symlink creation not permitted on this Windows host")
    with pytest.raises(EvidenceError):
        be.stat_evidence_file(link, "support_transcript")


# ---------------------------------------------------------------------------
# Claim classification
# ---------------------------------------------------------------------------


def test_expected_claims_classified(tmp_path):
    claims = {c.claim_id: c.classification for c in _claims(tmp_path)}
    assert claims["support.account_type"] == "BROKER_SUPPORT_ASSERTED"
    assert claims["support.commission_none"] == "BROKER_SUPPORT_ASSERTED"
    assert claims["support.spread_costs_in_spread"] == "BROKER_SUPPORT_ASSERTED"
    assert claims["support.no_archived_spread_by_email"] == "BROKER_SUPPORT_ASSERTED"
    assert claims["support.contract_size_100_oz"] == "BROKER_SUPPORT_ASSERTED"
    assert claims["support.pip_size_0_01"] == "BROKER_SUPPORT_ASSERTED"
    assert claims["support.volume_min_0_01"] == "BROKER_SUPPORT_ASSERTED"
    assert claims["support.volume_max_day_night"] == "BROKER_SUPPORT_ASSERTED"
    assert claims["support.margin_fixed_1_200"] == "BROKER_SUPPORT_ASSERTED"
    assert claims["support.hedged_margin_zero"] == "BROKER_SUPPORT_ASSERTED"
    assert claims["support.market_execution"] == "BROKER_SUPPORT_ASSERTED"
    assert claims["support.triple_swap_wednesday"] == "BROKER_SUPPORT_ASSERTED"
    assert claims["support.historical_swap_values_unsupplied"] == "HISTORICAL_VALUE_UNAVAILABLE"
    assert claims["support.rollover_time_unanswered"] == "HISTORICAL_VALUE_UNAVAILABLE"
    assert claims["support.no_public_historical_specification_archive"] == "HISTORICAL_VALUE_UNAVAILABLE"
    assert claims["support.non_standard_commission_out_of_scope"] == "REJECTED_CONFLICTING"


def test_missing_statement_fails_closed(tmp_path):
    broken = SYNTHETIC_TRANSCRIPT.replace("triple swap charged on Wednesdays", "swap charged daily")
    path = _write_transcript(tmp_path, text=broken)
    with pytest.raises(EvidenceError):
        be.load_transcript_claims(path)


def test_rollover_answer_beyond_questions_fails_closed(tmp_path):
    answered = SYNTHETIC_TRANSCRIPT.replace(
        "Market execution",
        "Market execution. The rollover happens at 21:00 exactly.",
    )
    path = _write_transcript(tmp_path, text=answered)
    with pytest.raises(EvidenceError, match="rollover-time statement"):
        be.load_transcript_claims(path)


def test_claim_binds_source_hash(tmp_path):
    file = _transcript_file(tmp_path)
    claims = _claims(tmp_path)
    assert claims
    for claim in claims:
        assert claim.source_file_sha256 == file.sha256


# ---------------------------------------------------------------------------
# Unit normalization
# ---------------------------------------------------------------------------


def test_point_pip_contract_normalization():
    units = be.verify_unit_normalization()
    assert units["mt5_point"] == 0.001
    assert units["broker_pip"] == 0.01
    assert units["contract_size_xau"] == 100.0
    assert units["checks"][0]["one_pip_in_points"] == 10.0
    assert units["checks"][1]["pip_value_usd_per_lot"] == 1.0
    assert units["checks"][2]["point_value_usd_per_lot"] == 0.10


# ---------------------------------------------------------------------------
# Screenshot records
# ---------------------------------------------------------------------------


def test_screenshot_values_stay_current_only(tmp_path):
    record = _screenshot(tmp_path)
    assert record["classification"] == "CURRENT_ONLY_NOT_HISTORICAL"
    assert record["status"] == "CURRENT_ONLY_NOT_HISTORICAL"
    assert record["observed_values"]["swap_long"] == "-534.9"


def test_screenshot_truncated_fields_recorded_not_guessed(tmp_path):
    path = tmp_path / "Exness_Standard_XAUUSDm_Specification_2099-01-01_02.png"
    path.write_bytes(b"\x89PNG-fixture")
    file = be.stat_evidence_file(path, "mt5_screenshot")
    record = be.build_screenshot_record(
        file=file,
        ocr_note="synthetic truncated fixture",
        observed={"swap_long": "-534.9"},
        not_readable=("swap_short",),
    )
    assert record["not_readable_fields"] == ["swap_short"]
    assert "swap_short" not in record["observed_values"]


def test_screenshot_record_rejects_wrong_role(tmp_path):
    path = tmp_path / "Exness_Standard_XAUUSDm_Specification_2099-01-01_03.png"
    path.write_bytes(b"\x89PNG-fixture")
    file = be.stat_evidence_file(path, "support_transcript")
    with pytest.raises(EvidenceError):
        be.build_screenshot_record(
            file=file, ocr_note="x", observed={"digits": "3"}, not_readable=()
        )


# ---------------------------------------------------------------------------
# Package: commission, swap, stress template
# ---------------------------------------------------------------------------


def test_commission_none_representation(tmp_path):
    content = _package(tmp_path)
    commission = content["commission_none"]
    assert commission["mode"] == "NONE"
    assert commission["amount"] == 0
    assert commission["currency"] == "USD"
    assert commission["per_side_charge"] == 0
    assert commission["round_turn_charge"] == 0
    assert commission["minimum_charge"] == 0
    assert commission["effective_interval"]["established"] is False
    labels = {item["label"] for item in commission["stress_sensitivity_proposals"]}
    assert labels == {"commission_per_lot_round_turn_3_5", "commission_per_lot_round_turn_5_5"}


def test_swap_historical_values_unavailable_and_triple_wednesday(tmp_path):
    content = _package(tmp_path)
    swap = content["swap_rollover"]
    assert swap["status"] == "HISTORICAL_VALUE_UNAVAILABLE"
    assert swap["historical_2024"]["swap_long"] is None
    assert swap["historical_2024"]["swap_short"] is None
    assert swap["broker_asserted"]["triple_swap_weekday"] == "WEDNESDAY"
    assert swap["broker_asserted"]["classification"] == "BROKER_SUPPORT_ASSERTED"
    assert swap["rollover"]["rollover_time_utc_supplied"] is None
    assert swap["current_observation"]["swap_long"] == "-534.9"
    assert swap["current_observation"]["classification"] == "CURRENT_ONLY_NOT_HISTORICAL"


def test_swap_short_readability_recorded(tmp_path):
    content = _package(tmp_path)
    assert content["swap_rollover"]["current_observation"]["swap_short"] == "0"
    assert (
        content["swap_rollover"]["current_observation"]["swap_short_readability"]
        == "clearly readable"
    )
    path = tmp_path / "Exness_Standard_XAUUSDm_Specification_2099-01-01_04.png"
    path.write_bytes(b"\x89PNG-fixture")
    file = be.stat_evidence_file(path, "mt5_screenshot")
    truncated = be.build_screenshot_record(
        file=file,
        ocr_note="synthetic",
        observed={"swap_long": "-534.9"},
        not_readable=("swap_short",),
    )
    from bot.acquisition import broker_evidence as be2

    swap = be2.build_swap_unavailability_record(
        support_claims=_claims(tmp_path),
        screenshots=[truncated],
        transcript_sha256=file.sha256,
    )
    assert swap["current_observation"]["swap_short"] is None
    assert (
        swap["current_observation"]["swap_short_readability"]
        == "NOT_CLEARLY_READABLE_TRUNCATED"
    )


def test_margin_conflict_documented_not_resolved(tmp_path):
    content = _package(tmp_path)
    assert content["margin_conflicts"][0]["classification"] == "REJECTED_CONFLICTING"
    assert "unresolved" in content["margin_conflicts"][0]["resolution"]


def test_spread_linkage_points_to_observed_ticks(tmp_path):
    content = _package(tmp_path)
    linkage = content["spread_evidence_linkage"]
    assert linkage["primary_2024_spread_evidence"]["package_id"].startswith(
        "evidence-observed_spread-v1-"
    )
    assert linkage["primary_2024_spread_evidence"]["classification"] == "OBSERVED_EMPIRICAL"
    assert "screenshot spread display" in linkage["substitution_prohibited"]


def test_stress_template_proposed_inactive_and_adverse_only(tmp_path):
    content = _package(tmp_path)
    stress = content["swap_stress_policy_proposal"]
    assert stress["status"] == "PROPOSED_INACTIVE"
    assert stress["active"] is False
    assert stress["classification"] == "ASSUMPTION_ONLY"
    assert stress["activation_requires"] == "separate owner-authorized preregistration checkpoint"
    assert all(s["triple_swap_weekday"] == "WEDNESDAY" for s in stress["scenarios"])
    assert stress["policy_constraints"]["triple_charging_preserved"] is True
    assert stress["policy_constraints"]["no_favorable_positive_swap_credit"] is True
    labels = [s["label"] for s in stress["scenarios"]]
    assert labels == ["neutral_current_proxy", "adverse_x2", "severe_x3"]
    for scenario in stress["scenarios"]:
        assert scenario["classification"] == "ASSUMPTION_ONLY"
        assert scenario["swap_long_usd_per_lot"] <= 0
        assert scenario["swap_short_usd_per_lot"] == 0
    base = -534.9 * 0.001 * 100
    assert stress["scenarios"][0]["swap_long_usd_per_lot"] == pytest.approx(base)
    assert stress["scenarios"][1]["swap_long_usd_per_lot"] == pytest.approx(base * 2)
    assert stress["scenarios"][2]["swap_long_usd_per_lot"] == pytest.approx(base * 3)


def test_stress_template_requires_current_swap_long(tmp_path):
    from bot.acquisition import broker_evidence as be2

    with pytest.raises(EvidenceError):
        be2.build_swap_stress_template(
            swap_unavailability={"current_observation": {"swap_long": None}},
            unit_normalization={"mt5_point": 0.001, "contract_size_xau": 100.0},
        )


def test_stress_template_rejects_favorable_base(tmp_path):
    from bot.acquisition import broker_evidence as be2

    with pytest.raises(EvidenceError):
        be2.build_swap_stress_template(
            swap_unavailability={"current_observation": {"swap_long": "12.3"}},
            unit_normalization={"mt5_point": 0.001, "contract_size_xau": 100.0},
        )


def test_prior_snapshot_conflicts_surfaced(tmp_path):
    from bot.acquisition import broker_evidence as be2

    swap = be2.build_swap_unavailability_record(
        support_claims=_claims(tmp_path),
        screenshots=[],
        transcript_sha256="0" * 64,
        prior_swap_snapshots=[
            {"snapshot_id": "old", "swap_long": "-111.1", "swap_short": "-22.2"}
        ],
    )
    check = swap["prior_snapshot_conflict_check"]
    assert check["previous_metadata_snapshots_with_swap_values"] == 1
    assert check["conflicts_detected"][0]["snapshot"] == "old"
    assert check["conflicts_detected"][0]["swap_long"] == "-111.1"


# ---------------------------------------------------------------------------
# Package determinism + publication
# ---------------------------------------------------------------------------


def test_package_content_is_deterministic(tmp_path):
    first = _package(tmp_path)
    second = _package(tmp_path)
    assert first["record_canonical_sha256"] == second["record_canonical_sha256"]
    assert canonical_hash(
        {k: v for k, v in first.items() if k != "record_canonical_sha256"}
    ) == canonical_hash({k: v for k, v in second.items() if k != "record_canonical_sha256"})


def test_envelope_publication_idempotent_and_tamper_checked(tmp_path):
    content = _package(tmp_path)
    envelope = be.build_broker_evidence_envelope(content)
    envelope["ingestion"] = {"ingested_at_utc": "2099-01-01T00:00:00Z"}
    from bot.acquisition.evidence_store import publish_evidence_package

    target1, pid1 = publish_evidence_package(envelope, evidence_root=tmp_path / "ev")
    target2, pid2 = publish_evidence_package(envelope, evidence_root=tmp_path / "ev")
    assert pid1 == pid2
    assert target1 == target2
    assert (target1 / "PUBLISHED").is_file()
    # Tampering with the package content must be detected on load.
    package = json.loads((target1 / "package.json").read_text(encoding="utf-8"))
    package["content"]["claims"] = []
    (target1 / "package.json").write_text(json.dumps(package), encoding="utf-8")
    from bot.acquisition.evidence_store import load_evidence_package

    with pytest.raises(EvidenceStoreError):
        load_evidence_package(target1)


def test_screenshot_values_cannot_be_marked_historical(tmp_path):
    file = be.stat_evidence_file(_write_transcript(tmp_path), "support_transcript")
    fake = dict(_screenshot(tmp_path))
    fake["classification"] = "HISTORICAL_VALUE_UNAVAILABLE"
    with pytest.raises(EvidenceError):
        be.build_broker_evidence_package(
            transcript_file=file,
            claims=_claims(tmp_path),
            screenshots=[fake],
            observed_spread_package_id=_spread_identity()[0],
            observed_spread_canonical_sha256=_spread_identity()[1],
        )


# ---------------------------------------------------------------------------
# Safety / confinement
# ---------------------------------------------------------------------------


def test_no_mt5_network_or_execution_references_in_8g_modules():
    for module_name in (
        "bot/acquisition/broker_evidence.py",
        "bot/acquisition/broker_email_evidence.py",
        "backtests/broker_evidence_control.py",
    ):
        source = (REPO_ROOT / module_name).read_text(encoding="utf-8")
        for prohibited in (
            "requests",
            "urllib",
            "socket",
            "http.client",
            "MetaTrader5",
            "order_send",
            "initialize(",
        ):
            assert prohibited not in source, f"{module_name} references {prohibited}"


def test_mt5_is_not_imported_by_8g_modules():
    mt5_before = sys.modules.get("MetaTrader5")
    import bot.acquisition.broker_evidence  # noqa: F401
    import bot.acquisition.broker_email_evidence  # noqa: F401
    import backtests.broker_evidence_control  # noqa: F401

    assert sys.modules.get("MetaTrader5") is mt5_before


# ---------------------------------------------------------------------------
# Phase 8G extension: official support email + swap-unit conflict
# ---------------------------------------------------------------------------

from bot.acquisition import broker_email_evidence as bee  # noqa: E402

SYNTHETIC_EMAIL_BODY = "\r\n".join(
    [
        "Dear Sampleowner,",
        "",
        "Warm greetings from Exness.",
        "How Standard Accounts work:",
        "Stable spreads, reliable execution, and no trading commissions.",
        "Orders executed on market execution (no requotes).",
        "Commission on XAUUSDm - Standard account: Yes, commission is zero. "
        "The Standard account is commission-free; trading costs are built into "
        "the spread rather than charged per lot.",
        "Swap (rollover) on XAUUSDm - Standard account, per 1.00 lot:",
        "Swap long: -3.85 USD per lot per day",
        "Swap short: -0.25 USD per lot per day",
        "Weekly triple-swap applies on the third rollover day (Wednesday), i.e., "
        "three times the daily value is charged that day.",
        "On historical values and change dates:",
        "We cannot provide a dated record of what the swap was throughout 2024 "
        "or the dates it changed.",
        "The account's daily/monthly statements, which record the actual swap "
        "charged each day, might be helpful.",
        "Contact us at support-desk@example-broker.test if needed.",
        "Best regards,",
        "FakeAgent",
        "thread::fake-thread-id-0000::",
    ]
)


def _write_email(tmp_path: Path, body: str = SYNTHETIC_EMAIL_BODY, nested: bool = True) -> Path:
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["Subject"] = "Exness - Trading Inquiries"
    msg["From"] = "Exness Support <noreply@example-broker.test>"
    msg["To"] = "Owner <owner@example-mail.test>"
    msg["Date"] = "Mon, 14 Sep 2026 14:29:42 +0000"
    msg.set_content(body)
    target_dir = tmp_path / ("Support/Private" if nested else "Support")
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / "Exness_XAUUSDm_Standard_Conditions_2099-01-01.eml"
    path.write_bytes(msg.as_bytes())
    return path


def _email_fixture(tmp_path: Path):
    eml = _write_email(tmp_path)
    file, parsed = bee.parse_email_evidence(eml)
    claims = bee.classify_email_claims(parsed, file)
    return file, parsed, claims


def test_email_discovery_in_private_subdirectory(tmp_path):
    eml = _write_email(tmp_path)
    assert bee.discover_email_file(tmp_path, base_name=eml.stem) == eml.resolve()


def test_email_discovery_missing_fails_closed(tmp_path):
    with pytest.raises(EvidenceError):
        bee.discover_email_file(tmp_path, base_name="No_Such_Email")


def test_email_discovery_ambiguous_fails_closed(tmp_path):
    _write_email(tmp_path)
    _write_email(tmp_path, nested=False)
    with pytest.raises(EvidenceError, match="ambiguous"):
        bee.discover_email_file(tmp_path, base_name="Exness_XAUUSDm_Standard_Conditions_2099-01-01")


def test_email_parsed_identity_is_deterministic(tmp_path):
    first_file, first_parsed, _ = _email_fixture(tmp_path)
    eml = _write_email(tmp_path)
    second_file, second_parsed = bee.parse_email_evidence(eml)
    assert first_file.sha256 == second_file.sha256
    assert (
        first_parsed["record"]["record_canonical_sha256"]
        == second_parsed["record"]["record_canonical_sha256"]
    )
    assert first_parsed["record"]["sent_utc"] == "2026-09-14T14:29:42Z"
    assert first_parsed["record"]["sender_domain"].endswith("example-broker.test")


def test_email_personal_data_redacted_from_body_and_quotes(tmp_path):
    _, parsed, claims = _email_fixture(tmp_path)
    body = str(parsed["body"])
    assert "Dear Sampleowner" not in body
    assert "owner@example-mail.test" not in body
    assert "thread::fake-thread-id" not in body
    joined = " ".join(claim.quote for claim in claims)
    assert "Dear Sampleowner" not in joined
    assert "@" not in joined
    assert "thread::" not in joined


def test_redaction_mechanism_matches_generic_personal_patterns():
    # Mechanism test: the redactor neutralizes any greeting name, any email
    # address and any thread id without embedding real personal data here.
    redacted = bee._redact_personal(
        "Dear Anyname, write to box@host.example, ref thread::abc-123::"
    )
    assert "Anyname" not in redacted
    assert "box@host.example" not in redacted
    assert "abc-123" not in redacted
    assert bee._OWNER_GREETING_RE.search(redacted) is None
    assert bee._EMAIL_ADDRESS_RE.search(redacted) is None
    assert bee._THREAD_ID_RE.search(redacted) is None


def test_email_strict_scan_rejects_sensitive_content(tmp_path):
    bad = SYNTHETIC_EMAIL_BODY.replace("Warm greetings from Exness.", "support PIN: 123456")
    eml = _write_email(tmp_path, body=bad)
    with pytest.raises(EvidenceError, match="sensitive"):
        bee.parse_email_evidence(eml)


def test_email_wrong_subject_fails_closed(tmp_path):
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["Subject"] = "Something Else"
    msg["From"] = "a@example-broker.test"
    msg["To"] = "b@example-mail.test"
    msg["Date"] = "Mon, 14 Sep 2026 14:29:42 +0000"
    msg.set_content(SYNTHETIC_EMAIL_BODY)
    path = tmp_path / "Support" / "Exness_XAUUSDm_Standard_Conditions_2099-01-01.eml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(msg.as_bytes())
    with pytest.raises(EvidenceError, match="subject"):
        bee.parse_email_evidence(path)


def test_email_truncation_fails_closed(tmp_path):
    truncated = SYNTHETIC_EMAIL_BODY.split("Best regards,")[0]
    eml = _write_email(tmp_path, body=truncated)
    with pytest.raises(EvidenceError, match="truncated"):
        bee.parse_email_evidence(eml)


def test_email_claims_classified_per_contract(tmp_path):
    _, _, claims = _email_fixture(tmp_path)
    classes = {c.claim_id: c.classification for c in claims}
    assert classes["email.standard_no_trading_commission"] == "BROKER_SUPPORT_ASSERTED"
    assert classes["email.xauusdm_commission_zero"] == "BROKER_SUPPORT_ASSERTED"
    assert classes["email.costs_built_into_spread"] == "BROKER_SUPPORT_ASSERTED"
    assert classes["email.market_execution"] == "BROKER_SUPPORT_ASSERTED"
    assert classes["email.swap_long_usd_per_lot"] == "CURRENT_SUPPORT_REFERENCE"
    assert classes["email.swap_short_usd_per_lot"] == "CURRENT_SUPPORT_REFERENCE"
    assert classes["email.triple_swap_wednesday"] == "BROKER_SUPPORT_ASSERTED"
    assert classes["email.historical_swaps_unavailable"] == "HISTORICAL_VALUE_UNAVAILABLE"
    assert classes["email.statements_show_only_existing_trades"] == "BROKER_SUPPORT_ASSERTED"


def test_email_claims_bind_source_hash(tmp_path):
    file, _, claims = _email_fixture(tmp_path)
    assert all(c.source_file_sha256 == file.sha256 for c in claims)


def test_email_swap_value_extraction(tmp_path):
    _, _, claims = _email_fixture(tmp_path)
    values = bee.email_swap_values_from_claims(
        {c.claim_id: c.statement for c in claims}
    )
    assert values == ("-3.85", "-0.25")


def test_email_swap_value_extraction_tamper_fails(tmp_path):
    _, _, claims = _email_fixture(tmp_path)
    statements = {c.claim_id: c.statement for c in claims}
    statements["email.swap_long_usd_per_lot"] = "statement without the value"
    with pytest.raises(EvidenceError):
        bee.email_swap_values_from_claims(statements)


def test_pdf_attachment_hash_bound_or_honestly_absent(tmp_path):
    eml = _write_email(tmp_path)
    file, parsed = bee.parse_email_evidence(eml)
    assert parsed["record"]["pdf_attachment"] is None
    pdf = tmp_path / "Support" / "Exness_XAUUSDm_Standard_Conditions_2099-01-01.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.4 fake-but-valid-header")
    _, parsed_with_pdf = bee.parse_email_evidence(eml, pdf)
    attachment = parsed_with_pdf["record"]["pdf_attachment"]
    assert attachment["sha256"] == be.sha256_file(pdf)
    with pytest.raises(EvidenceError, match="PDF"):
        pdf.write_bytes(b"NOT-A-PDF")
        bee.parse_email_evidence(eml, pdf)


def test_swap_unit_conflict_record_is_verbatim_and_unresolved(tmp_path):
    file, parsed, claims = _email_fixture(tmp_path)
    values = bee.email_swap_values_from_claims(
        {c.claim_id: c.statement for c in claims}
    )
    screenshot = be.stat_evidence_file(tmp_path / "screenshot.png", "mt5_screenshot") \
        if (tmp_path / "screenshot.png").write_bytes(b"png") or True else None
    conflict = bee.finalize_conflict_record(
        bee.build_swap_unit_conflict_record(
            screenshot_file=screenshot,
            screenshot_swap_long_points="-534.9",
            screenshot_swap_short=None,
            screenshot_swap_short_readability="NOT_CLEARLY_READABLE_TRUNCATED",
            email_file=file,
            email_swap_long_usd=values[0],
            email_swap_short_usd=values[1],
            email_sent_utc=str(parsed["record"]["sent_utc"]),
        )
    )
    assert conflict["classification"] == "REJECTED_CONFLICTING"
    assert conflict["equivalence_established"] is False
    assert conflict["conflict_id"] == "swap.units_points_vs_usd_per_lot"
    shot = conflict["values"]["screenshot_current_observation"]
    mail = conflict["values"]["email_support_reference"]
    assert shot["units"] == "MT5 points per 1.00 lot per day"
    assert shot["swap_long"] == "-534.9"
    assert shot["source_file_sha256"] == screenshot.sha256
    assert mail["units"] == "USD per 1.00 lot per day"
    assert mail["swap_long"] == "-3.85"
    assert mail["swap_short"] == "-0.25"
    assert mail["source_file_sha256"] == file.sha256
    assert mail["observation_date_utc"] == "2026-09-14T14:29:42Z"
    assert any("conversion" in item for item in conflict["possible_explanations"])
    assert any("averaging" in item for item in conflict["reconciliation_prohibited"])
    again = bee.finalize_conflict_record(
        bee.build_swap_unit_conflict_record(
            screenshot_file=screenshot,
            screenshot_swap_long_points="-534.9",
            screenshot_swap_short=None,
            screenshot_swap_short_readability="NOT_CLEARLY_READABLE_TRUNCATED",
            email_file=file,
            email_swap_long_usd=values[0],
            email_swap_short_usd=values[1],
            email_sent_utc=str(parsed["record"]["sent_utc"]),
        )
    )
    assert again["record_canonical_sha256"] == conflict["record_canonical_sha256"]


def test_email_stress_template_is_conflict_gated_and_adverse_only(tmp_path):
    stress = be.build_email_stress_template(
        email_swap_long_usd="-3.85",
        unit_normalization=be.verify_unit_normalization(),
    )
    assert stress["status"] == "PROPOSED_INACTIVE_CONFLICT_GATED"
    assert stress["active"] is False
    assert stress["classification"] == "ASSUMPTION_ONLY"
    assert stress["conflict_gate"] == "swap.units_points_vs_usd_per_lot"
    assert "USD per 1.00 lot per day" in stress["units"]
    assert stress["base_observation"]["classification"] == "CURRENT_SUPPORT_REFERENCE"
    assert [s["label"] for s in stress["scenarios"]] == [
        "neutral_current_proxy",
        "adverse_x2",
        "severe_x3",
    ]
    for scenario, expected in zip(stress["scenarios"], (-3.85, -7.7, -11.55)):
        assert scenario["classification"] == "ASSUMPTION_ONLY"
        assert scenario["swap_long_usd_per_lot_per_day"] == pytest.approx(expected)
        assert scenario["swap_short_usd_per_lot_per_day"] == 0.0
        assert scenario["triple_swap_weekday"] == "WEDNESDAY"
        assert scenario["triple_weekday_multiplier"] == 3
    assert stress["policy_constraints"]["no_favorable_positive_swap_credit"] is True


def test_email_stress_template_rejects_favorable_base(tmp_path):
    with pytest.raises(EvidenceError):
        be.build_email_stress_template(
            email_swap_long_usd="1.25",
            unit_normalization=be.verify_unit_normalization(),
        )


def test_package_with_email_is_deterministic_and_conflict_gated(tmp_path):
    content = be.build_broker_evidence_package(
        transcript_file=_transcript_file(tmp_path),
        claims=_claims(tmp_path),
        screenshots=[_screenshot(tmp_path)],
        observed_spread_package_id=_spread_identity()[0],
        observed_spread_canonical_sha256=_spread_identity()[1],
        margin_conflicts=[],
        email_file=_email_fixture(tmp_path)[0],
        email_claims=_email_fixture(tmp_path)[2],
        email_record=_email_fixture(tmp_path)[1]["record"],
        swap_unit_conflict={
            "schema_version": bee.SWAP_UNIT_CONFLICT_SCHEMA_VERSION,
            "classification": "REJECTED_CONFLICTING",
            "conflict_id": "swap.units_points_vs_usd_per_lot",
            "equivalence_established": False,
        },
        email_stress_template=be.build_email_stress_template(
            email_swap_long_usd="-3.85",
            unit_normalization=be.verify_unit_normalization(),
        ),
    )
    again = be.build_broker_evidence_package(
        transcript_file=_transcript_file(tmp_path),
        claims=_claims(tmp_path),
        screenshots=[_screenshot(tmp_path)],
        observed_spread_package_id=_spread_identity()[0],
        observed_spread_canonical_sha256=_spread_identity()[1],
        margin_conflicts=[],
        email_file=_email_fixture(tmp_path)[0],
        email_claims=_email_fixture(tmp_path)[2],
        email_record=_email_fixture(tmp_path)[1]["record"],
        swap_unit_conflict={
            "schema_version": bee.SWAP_UNIT_CONFLICT_SCHEMA_VERSION,
            "classification": "REJECTED_CONFLICTING",
            "conflict_id": "swap.units_points_vs_usd_per_lot",
            "equivalence_established": False,
        },
        email_stress_template=be.build_email_stress_template(
            email_swap_long_usd="-3.85",
            unit_normalization=be.verify_unit_normalization(),
        ),
    )
    assert content["record_canonical_sha256"] == again["record_canonical_sha256"]
    assert len(content["claims"]) == len(_claims(tmp_path)) + 9
    assert content["swap_stress_policy_proposal"]["status"] == "PROPOSED_INACTIVE_CONFLICT_GATED"
    assert content["support_email"]["classification"] == "CURRENT_SUPPORT_REFERENCE"
    assert (
        content["commission_email_corroboration"]["claim_ids"]
        == [
            "email.costs_built_into_spread",
            "email.standard_no_trading_commission",
            "email.xauusdm_commission_zero",
        ]
    )


def test_package_conflict_and_template_must_travel_together(tmp_path):
    gated_template = be.build_email_stress_template(
        email_swap_long_usd="-3.85",
        unit_normalization=be.verify_unit_normalization(),
    )
    base = dict(
        transcript_file=_transcript_file(tmp_path),
        claims=_claims(tmp_path),
        screenshots=[_screenshot(tmp_path)],
        observed_spread_package_id=_spread_identity()[0],
        observed_spread_canonical_sha256=_spread_identity()[1],
        margin_conflicts=[],
    )
    with pytest.raises(EvidenceError, match="requires the swap-unit conflict"):
        be.build_broker_evidence_package(email_stress_template=gated_template, **base)
    with pytest.raises(EvidenceError, match="requires the parsed record"):
        be.build_broker_evidence_package(
            email_file=_email_fixture(tmp_path)[0],
            email_claims=_email_fixture(tmp_path)[2],
            **base,
        )
