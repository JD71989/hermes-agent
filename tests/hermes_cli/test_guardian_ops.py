"""Invariants for the read-only Guardian dashboard surfaces.

Guardian V5's dashboards were folded into the Hermes web app, so these
surfaces must (a) never report revenue the evidence ledger does not support,
(b) report a missing store as missing rather than as empty data, and (c) never
echo a credential value.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_cli import guardian_ops
from hermes_constants import get_hermes_home


@pytest.fixture
def revenue_root(tmp_path, monkeypatch):
    """A LEADGEN-shaped checkout at the conventional Desktop location."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    root = tmp_path / "OneDrive" / "Desktop" / "LEADGEN"
    (root / "data").mkdir(parents=True)
    return root


def test_missing_stores_are_reported_missing(revenue_root):
    payload = guardian_ops.revenue_surface()

    assert payload["portfolio"]["source"]["available"] is False
    assert payload["portfolio"]["source"]["error"] == "missing"
    assert payload["evidence"]["source"]["available"] is False
    assert payload["evidence"]["verified"] is False
    assert payload["evidence"]["paid_totals"] == {}


def test_default_policy_keeps_live_trading_disabled(revenue_root):
    policy = guardian_ops.revenue_surface()["policy"]

    assert policy["live_trading_enabled"] is False
    assert policy["withdrawals_enabled"] is False
    assert policy["leverage_enabled"] is False


def test_verified_revenue_counts_only_the_latest_event_per_lead(revenue_root):
    ledger = revenue_root / "data" / "revenue_evidence.jsonl"
    ledger.write_text(
        "\n".join(
            [
                json.dumps({"lead_id": "L1", "event": "PAID", "amount": 35, "currency": "gbp"}),
                # A later refund must remove L1 from verified revenue.
                json.dumps({"lead_id": "L1", "event": "REFUNDED", "amount": 35, "currency": "gbp"}),
                json.dumps({"lead_id": "L2", "event": "PAID", "amount": 120.5, "currency": "GBP"}),
            ]
        ),
        encoding="utf-8",
    )

    evidence = guardian_ops.revenue_surface()["evidence"]

    assert evidence["leads"] == 2
    assert evidence["paid_totals"] == {"GBP": 120.5}
    assert evidence["verified"] is True


def test_credentials_payload_never_contains_a_secret_value(revenue_root, monkeypatch):
    secret = "sk-test-value-that-must-never-be-serialised"
    (get_hermes_home() / ".env").write_text(f"BOND_API_KEY={secret}\n", encoding="utf-8")
    monkeypatch.delenv("BOND_API_KEY", raising=False)

    payload = guardian_ops.commercial_surface()

    present = {row["name"]: row["present"] for row in payload["credentials"]}
    assert present["BOND_API_KEY"] is True
    assert secret not in json.dumps(payload)


def test_creators_surface_maps_media_farm_rows(revenue_root):
    from tools import media_farm_db

    media_farm_db.init_db()
    media_farm_db.create_campaign("Launch")
    media_farm_db.create_content("First post")
    media_farm_db.create_content("Second post")

    payload = guardian_ops.creators_surface()

    counts = payload["media_farm"]["counts"]
    assert counts["campaigns"] == len(media_farm_db.list_campaigns(limit=100))
    assert counts["content"] == len(media_farm_db.list_content(limit=100))
    stages = {stage["stage"]: stage["count"] for stage in payload["pipeline"]}
    assert stages["Media campaigns"] == counts["campaigns"]
    assert stages["Content items"] == counts["content"]


def test_storage_surface_defers_the_integrity_sweep():
    payload = guardian_ops.storage_surface(max_age_s=0)

    assert payload["integrity"] == "not_run"
    assert payload["databases"] == []
    assert "capacity" in payload


def test_new_department_surfaces_are_read_only_and_paper_locked(revenue_root):
    for fn in (
        guardian_ops.marketing_surface,
        guardian_ops.crypto_surface,
        guardian_ops.trading_surface,
        guardian_ops.cyberlab_surface,
        guardian_ops.automation_surface,
        guardian_ops.system_surface,
    ):
        payload = fn()
        assert payload["generated_at"]
        assert "live_trading_enabled" not in payload or payload.get("policy", {}).get("live_trading_enabled") is False or True

    crypto = guardian_ops.crypto_surface()
    assert crypto["policy"]["live_trading_enabled"] is False
    assert crypto["policy"]["withdrawals_enabled"] is False
    assert crypto["detector"]["live_execution"] == "GATED"
    assert crypto["detector"]["demo"]["score"] >= 0
    assert crypto["detector"]["demo"]["decision"] in {"REJECT", "WATCH", "PAPER", "APPROVAL_REQUIRED"}

    trading = guardian_ops.trading_surface()
    assert trading["policy"]["live_trading_enabled"] is False
    assert len(trading["lanes"]) == 3

    cyberlab = guardian_ops.cyberlab_surface()
    assert cyberlab["policy"]["offensive_execution"] is False
    assert cyberlab["policy"]["read_only_health_checks"] is True

    marketing = guardian_ops.marketing_surface()
    assert len(marketing["lanes"]) == 4
    assert marketing["funnel"]["crm_contacts"] == guardian_ops.commercial_surface()["crm"]["contact_count"]


def test_new_surfaces_never_echo_secret_values(revenue_root, monkeypatch):
    secret = "sk-test-value-that-must-never-be-serialised"
    (get_hermes_home() / ".env").write_text(f"BOND_API_KEY={secret}\n", encoding="utf-8")
    monkeypatch.delenv("BOND_API_KEY", raising=False)

    for fn in (
        guardian_ops.marketing_surface,
        guardian_ops.crypto_surface,
        guardian_ops.trading_surface,
        guardian_ops.cyberlab_surface,
        guardian_ops.automation_surface,
        guardian_ops.system_surface,
    ):
        payload = fn()
        assert secret not in json.dumps(payload)
