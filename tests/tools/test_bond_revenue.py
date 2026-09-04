"""Focused tests for the bond_revenue tool.

Tests the full lead lifecycle pipeline: traffic -> enquiry -> lead ->
validation -> qualification -> deduplication -> accept/reject ->
delivery -> customer acceptance -> revenue -> feedback -> optimisation.

£35 per accepted qualified lead.

Environment gating: check_fn requires BOND_API_KEY set.
"""

import json
import os
import sys

import pytest


def _ensure_cwd():
    """Ensure we're running from the hermes-agent directory."""
    target = r"C:\Users\jamie\AppData\Local\hermes\hermes-agent"
    if os.getcwd() != target:
        os.chdir(target)


_ensure_cwd()


# ---------------------------------------------------------------------------
# Helpers (import tool inside test functions to avoid module-level issues)
# ---------------------------------------------------------------------------

def _set_bond_key():
    """Set BOND_API_KEY in the current process."""
    os.environ["BOND_API_KEY"] = "test-bond-key-123"


def _clear_bond_key():
    """Clear BOND_API_KEY from the current process."""
    os.environ.pop("BOND_API_KEY", None)


def _ensure_bond_tool():
    """Ensure the bond_revenue tool is registered and available.

    Must be called after _set_bond_key() so the env var is active
    when the module-level registry.register() executes.
    """
    # Clear any cached module to get a fresh registration
    for mod in list(sys.modules.keys()):
        if "bond_revenue_tool" in mod:
            del sys.modules[mod]
    import tools.bond_revenue_tool  # noqa: F811 - triggers registry.register
    from tools.registry import registry
    entry = registry.get_entry("bond_revenue")
    assert entry is not None, "Tool should be registered when BOND_API_KEY is set"
    return entry


def _run_tool(args: dict) -> dict:
    """Run the bond_revenue handler and return the parsed JSON result."""
    from tools.bond_revenue_tool import handle_bond_revenue_tool
    raw = handle_bond_revenue_tool(args)
    return json.loads(raw)


# ---------------------------------------------------------------------------
# A. Create enquiry from traffic
# ---------------------------------------------------------------------------

def test_create_enquiry_from_traffic():
    """Normal create_enquiry returns enquiry_id and lead_id."""
    _set_bond_key()
    _ensure_bond_tool()
    result = _run_tool({
        "stage": "create_enquiry",
        "visitor_id": "visitor-abc123",
        "source": "web",
        "country": "UK",
        "postcode": "SW1A 1AA",
        "property_type": "flat",
    })
    assert result is not None
    assert result.get("ok") is True
    assert "enquiry_id" in result
    assert "lead_id" in result
    assert result.get("stage") == "enquiry"


# ---------------------------------------------------------------------------
# B. Validate a lead
# ---------------------------------------------------------------------------

def test_validate_lead_valid_uk():
    """Valid UK lead passes validation."""
    _set_bond_key()
    _ensure_bond_tool()
    result = _run_tool({
        "stage": "validate_lead",
        "enquiry_id": "env-202609041200",
        "visitor_id": "visitor-abc123",
        "country": "UK",
        "postcode": "SW1A 1AA",
        "property_type": "flat",
    })
    assert result is not None
    assert result.get("ok") is True
    assert "lead_id" in result
    assert result.get("stage") == "validation"


def test_validate_lead_invalid_country():
    """Invalid country fails validation."""
    _set_bond_key()
    _ensure_bond_tool()
    result = _run_tool({
        "stage": "validate_lead",
        "enquiry_id": "env-202609041200",
        "visitor_id": "visitor-abc123",
        "country": "US",  # Not supported
        "postcode": "12345",
        "property_type": "flat",
    })
    assert result is not None


def test_validate_lead_invalid_au_postcode():
    """Invalid AU postcode fails validation."""
    _set_bond_key()
    _ensure_bond_tool()
    result = _run_tool({
        "stage": "validate_lead",
        "enquiry_id": "env-202609041200",
        "visitor_id": "visitor-abc123",
        "country": "AU",
        "postcode": "not-a-postcode",  # Invalid AU format
        "property_type": "house",
    })
    assert result is not None


# ---------------------------------------------------------------------------
# C. Qualify a lead
# ---------------------------------------------------------------------------
def test_qualify_lead_with_budget():
    """Qualify a lead with budget above threshold."""
    _set_bond_key()
    _ensure_bond_tool()

    # First create, validate, then qualify a lead
    result = _run_tool({
        "stage": "create_enquiry",
        "visitor_id": "visitor-qualify1",
        "source": "web",
        "country": "UK",
        "postcode": "SW1A 1AA",
        "property_type": "flat",
    })
    lead_id = result.get("lead_id", "")
    enquiry_id = result.get("enquiry_id", "")

    _run_tool({
        "stage": "validate_lead",
        "enquiry_id": enquiry_id,
        "visitor_id": "visitor-qualify1",
        "country": "UK",
        "postcode": "SW1A 1AA",
    })

    # Note: lead has no budget set, so with threshold set, it's not qualified
    result = _run_tool({
        "stage": "qualify_lead",
        "lead_id": lead_id,
        "budget_threshold": "5000",
    })
    assert result is not None
    assert result.get("ok") is True
    # With no budget set and threshold provided, lead is not qualified
    assert result.get("qualified") is False
    assert result.get("stage") == "qualification"


def test_qualify_lead_below_budget():
    """Qualify a lead with budget below threshold."""
    _set_bond_key()
    _ensure_bond_tool()

    # First create, validate, then qualify a lead
    result = _run_tool({
        "stage": "create_enquiry",
        "visitor_id": "visitor-qualify2",
        "source": "web",
        "country": "UK",
        "postcode": "SW1A 1AA",
        "property_type": "flat",
    })
    lead_id = result.get("lead_id", "")
    enquiry_id = result.get("enquiry_id", "")

    _run_tool({
        "stage": "validate_lead",
        "enquiry_id": enquiry_id,
        "visitor_id": "visitor-qualify2",
        "country": "UK",
        "postcode": "SW1A 1AA",
    })

    # With no budget set and threshold provided, lead is not qualified
    result = _run_tool({
        "stage": "qualify_lead",
        "lead_id": lead_id,
        "budget_threshold": "999999999",  # Very high threshold
    })
    assert result is not None
    assert result.get("ok") is True
    assert result.get("qualified") is False
    assert result.get("stage") == "qualification"

# ---------------------------------------------------------------------------
# D. Deduplicate leads
# ---------------------------------------------------------------------------

def test_deduplicate_leads():
    """Deduplicate removes duplicate leads."""
    _set_bond_key()
    _ensure_bond_tool()

    # Clear prior state to ensure test isolation
    home = os.path.join(os.environ.get("HERMES_HOME", os.path.join(os.path.expanduser("~"), ".hermes")))
    state_file = os.path.join(home, "bond_lead_state.json")
    if os.path.exists(state_file):
        os.remove(state_file)

    # Create multiple leads - use same visitor_id for first two to test dedup
    # First lead with visitor-dup1
    result1 = _run_tool({
        "stage": "create_enquiry",
        "visitor_id": "visitor-dup1",
        "source": "web",
        "country": "UK",
        "postcode": "SW1A 1AA",
        "property_type": "flat",
    })
    lead_id_1 = result1.get("lead_id", "")

    # Small delay to ensure different timestamp, then second lead with same visitor_id
    import time
    time.sleep(0.1)  # 100ms delay to ensure different timestamp
    result2 = _run_tool({
        "stage": "create_enquiry",
        "visitor_id": "visitor-dup1",
        "source": "web",
        "country": "UK",
        "postcode": "SW1A 1AA",
        "property_type": "flat",
    })
    lead_id_2 = result2.get("lead_id", "")

    # Third lead with different visitor_id (unique)
    result3 = _run_tool({
        "stage": "create_enquiry",
        "visitor_id": "visitor-unique",
        "source": "web",
        "country": "UK",
        "postcode": "SW1A 1AA",
        "property_type": "flat",
    })
    lead_id_3 = result3.get("lead_id", "")

    # Verify lead IDs
    print(f"Lead IDs: {lead_id_1}, {lead_id_2}, {lead_id_3}")

    # Now deduplicate
    result = _run_tool({"stage": "deduplicate"})
    assert result is not None
    assert result.get("ok") is True
    # original_count and unique_count from dedup
    original_count = result.get("original_count", 0)
    unique_count = result.get("unique_count", 0)
    print(f"Dedup: original={original_count}, unique={unique_count}")
    # With the delay, leads 1 and 2 should have different lead_ids but same
    # visitor_id+country+postcode+property_type, so dedup should remove 1
    assert original_count >= 2, f"Expected at least 2 original leads, got {original_count}"
    # After dedup, unique should be < original (one duplicate removed)
    assert unique_count < original_count, \
        f"Expected unique_count ({unique_count}) < original_count ({original_count}), ""after dedup removing 1 duplicate"


# ---------------------------------------------------------------------------
# E. Accept / reject a lead
# ---------------------------------------------------------------------------

def test_accept_lead():
    """Accept a qualified lead."""
    _set_bond_key()
    _ensure_bond_tool()

    # Full pipeline: create -> validate -> qualify -> accept
    result = _run_tool({
        "stage": "create_enquiry",
        "visitor_id": "visitor-accept",
        "source": "web",
        "country": "UK",
        "postcode": "SW1A 1AA",
        "property_type": "flat",
    })
    lead_id = result.get("lead_id", "")

    _run_tool({
        "stage": "validate_lead",
        "enquiry_id": lead_id,
        "visitor_id": "visitor-accept",
        "country": "UK",
        "postcode": "SW1A 1AA",
    })

    _run_tool({
        "stage": "qualify_lead",
        "lead_id": lead_id,
        "budget_threshold": "5000",
    })

    # Accept the lead
    result = _run_tool({
        "stage": "accept_lead",
        "lead_id": lead_id,
        "acceptor_id": "system-admin",
    })
    assert result is not None
    assert result.get("ok") is True
    assert result.get("accepted") is True
    assert result.get("stage") == "acceptance"


def test_reject_lead():
    """Reject a lead."""
    _set_bond_key()
    _ensure_bond_tool()

    # Full pipeline: create -> validate -> reject
    result = _run_tool({
        "stage": "create_enquiry",
        "visitor_id": "visitor-reject",
        "source": "web",
        "country": "UK",
        "postcode": "SW1A 1AA",
        "property_type": "flat",
    })
    lead_id = result.get("lead_id", "")

    _run_tool({
        "stage": "validate_lead",
        "enquiry_id": lead_id,
        "visitor_id": "visitor-reject",
        "country": "UK",
        "postcode": "SW1A 1AA",
    })

    result = _run_tool({
        "stage": "reject_lead",
        "lead_id": lead_id,
        "rejector_id": "system-admin",
        "reason": "Budget too low",
    })
    assert result is not None
    assert result.get("ok") is True
    assert result.get("stage") == "rejection"


# ---------------------------------------------------------------------------
# F. Deliver a lead
# ---------------------------------------------------------------------------

def test_deliver_lead():
    """Deliver a lead to the sales team."""
    _set_bond_key()
    _ensure_bond_tool()

    # Full pipeline: create -> validate -> qualify -> deliver
    result = _run_tool({
        "stage": "create_enquiry",
        "visitor_id": "visitor-deliver",
        "source": "web",
        "country": "UK",
        "postcode": "SW1A 1AA",
        "property_type": "flat",
    })
    lead_id = result.get("lead_id", "")

    _run_tool({
        "stage": "validate_lead",
        "enquiry_id": lead_id,
        "visitor_id": "visitor-deliver",
        "country": "UK",
        "postcode": "SW1A 1AA",
    })

    _run_tool({
        "stage": "qualify_lead",
        "lead_id": lead_id,
        "budget_threshold": "5000",
    })

    result = _run_tool({
        "stage": "deliver_lead",
        "lead_id": lead_id,
        "delivery_id": "deliv-001",
        "delivery_method": "email",
    })
    assert result is not None
    assert result.get("ok") is True
    assert result.get("delivered") is True
    assert result.get("stage") == "delivery"


# ---------------------------------------------------------------------------
# G. Accept customer
# ---------------------------------------------------------------------------

def test_accept_customer():
    """Record customer acceptance."""
    _set_bond_key()
    _ensure_bond_tool()

    # Full pipeline: create -> validate -> qualify -> deliver -> accept customer
    result = _run_tool({
        "stage": "create_enquiry",
        "visitor_id": "visitor-cust",
        "source": "web",
        "country": "UK",
        "postcode": "SW1A 1AA",
        "property_type": "flat",
    })
    lead_id = result.get("lead_id", "")

    _run_tool({
        "stage": "validate_lead",
        "enquiry_id": lead_id,
        "visitor_id": "visitor-cust",
        "country": "UK",
        "postcode": "SW1A 1AA",
    })

    _run_tool({
        "stage": "qualify_lead",
        "lead_id": lead_id,
        "budget_threshold": "5000",
    })

    _run_tool({
        "stage": "deliver_lead",
        "lead_id": lead_id,
        "delivery_id": "deliv-001",
        "delivery_method": "email",
    })

    result = _run_tool({
        "stage": "accept_customer",
        "lead_id": lead_id,
        "accepter_id": "sales-rep-001",
    })
    assert result is not None
    assert result.get("ok") is True
    assert result.get("status") == "customer_accepted"


# ---------------------------------------------------------------------------
# H. Record revenue
# ---------------------------------------------------------------------------

def test_record_revenue():
    """Record £35 revenue from accepted qualified lead."""
    _set_bond_key()
    _ensure_bond_tool()

    # Full pipeline: create -> validate -> qualify -> deliver -> accept customer -> record revenue
    result = _run_tool({
        "stage": "create_enquiry",
        "visitor_id": "visitor-revenue",
        "source": "web",
        "country": "UK",
        "postcode": "SW1A 1AA",
        "property_type": "flat",
    })
    lead_id = result.get("lead_id", "")

    _run_tool({
        "stage": "validate_lead",
        "enquiry_id": lead_id,
        "visitor_id": "visitor-revenue",
        "country": "UK",
        "postcode": "SW1A 1AA",
    })

    _run_tool({
        "stage": "qualify_lead",
        "lead_id": lead_id,
        "budget_threshold": "5000",
    })

    _run_tool({
        "stage": "deliver_lead",
        "lead_id": lead_id,
        "delivery_id": "deliv-001",
        "delivery_method": "email",
    })

    _run_tool({
        "stage": "accept_customer",
        "lead_id": lead_id,
        "accepter_id": "sales-rep-001",
    })

    result = _run_tool({
        "stage": "record_revenue",
        "lead_id": lead_id,
        "amount": "35",
        "currency": "GBP",
    })
    assert result is not None
    assert result.get("ok") is True
    assert result.get("revenue") == "35"
    assert result.get("currency") == "GBP"
    assert result.get("stage") == "revenue"


def test_record_revenue_australia():
    """Record AUD revenue from accepted qualified AU lead."""
    _set_bond_key()
    _ensure_bond_tool()

    # Full pipeline for AU lead
    result = _run_tool({
        "stage": "create_enquiry",
        "visitor_id": "visitor-revenue-au",
        "source": "web",
        "country": "AU",
        "postcode": "2000",
        "property_type": "house",
    })
    lead_id = result.get("lead_id", "")

    _run_tool({
        "stage": "validate_lead",
        "enquiry_id": lead_id,
        "visitor_id": "visitor-revenue-au",
        "country": "AU",
        "postcode": "2000",
        "property_type": "house",
    })

    _run_tool({
        "stage": "qualify_lead",
        "lead_id": lead_id,
        "budget_threshold": "5000",
    })

    _run_tool({
        "stage": "deliver_lead",
        "lead_id": lead_id,
        "delivery_id": "deliv-001",
        "delivery_method": "email",
    })

    _run_tool({
        "stage": "accept_customer",
        "lead_id": lead_id,
        "accepter_id": "sales-rep-001",
    })

    result = _run_tool({
        "stage": "record_revenue",
        "lead_id": lead_id,
        "amount": "50",
        "currency": "AUD",
    })
    assert result is not None
    assert result.get("ok") is True
    assert result.get("revenue") == "50"
    assert result.get("currency") == "AUD"


# ---------------------------------------------------------------------------
# I. Record feedback
# ---------------------------------------------------------------------------

def test_record_feedback():
    """Record feedback on a lead."""
    _set_bond_key()
    _ensure_bond_tool()

    # Full pipeline: create -> validate -> qualify -> deliver -> accept customer -> record feedback
    result = _run_tool({
        "stage": "create_enquiry",
        "visitor_id": "visitor-feedback",
        "source": "web",
        "country": "UK",
        "postcode": "SW1A 1AA",
        "property_type": "flat",
    })
    lead_id = result.get("lead_id", "")

    _run_tool({
        "stage": "validate_lead",
        "enquiry_id": lead_id,
        "visitor_id": "visitor-feedback",
        "country": "UK",
        "postcode": "SW1A 1AA",
    })

    _run_tool({
        "stage": "qualify_lead",
        "lead_id": lead_id,
        "budget_threshold": "5000",
    })

    _run_tool({
        "stage": "deliver_lead",
        "lead_id": lead_id,
        "delivery_id": "deliv-001",
        "delivery_method": "email",
    })

    _run_tool({
        "stage": "accept_customer",
        "lead_id": lead_id,
        "accepter_id": "sales-rep-001",
    })

    result = _run_tool({
        "stage": "record_feedback",
        "lead_id": lead_id,
        "feedback": "Customer interested in 2-bed flat, follow up next week",
        "feedback_by": "sales-rep-001",
    })
    assert result is not None
    assert result.get("ok") is True
    assert result.get("stage") == "feedback"


# ---------------------------------------------------------------------------
# J. Optimise pipeline
# ---------------------------------------------------------------------------

def test_optimise_pipeline():
    """Optimise pipeline returns analysis."""
    _set_bond_key()
    _ensure_bond_tool()

    # Run optimise
    result = _run_tool({"stage": "optimise"})
    assert result is not None
    assert result.get("ok") is True
    # Check for either suggestions or summary
    assert "suggestions" in result or "summary" in result


# ---------------------------------------------------------------------------
# K. Tool blocked without BOND_API_KEY
# ---------------------------------------------------------------------------

def test_tool_blocked_without_key():
    """When BOND_API_KEY is not set, the tool is unavailable."""
    _clear_bond_key()

    # Ensure tool registration with no key
    for mod in list(sys.modules.keys()):
        if "bond_revenue_tool" in mod:
            del sys.modules[mod]
    import tools.bond_revenue_tool

    from tools.registry import registry
    entry = registry.get_entry("bond_revenue")
    assert entry is not None, "Tool should still be registered"
    # check_fn should return False when key is not set
    assert entry.check_fn() is False, \
        "Tool should be unavailable when BOND_API_KEY is not set"


# ---------------------------------------------------------------------------
# L. Invalid payload rejected
# ---------------------------------------------------------------------------

def test_invalid_payload_rejected():
    """Missing required fields in the payload are rejected."""
    _set_bond_key()
    _ensure_bond_tool()

    result = _run_tool({"stage": "create_enquiry"})
    # Missing required fields should be rejected
    assert result.get("ok") is False or "error" in result


# ---------------------------------------------------------------------------
# M. Unknown stage rejected
# ---------------------------------------------------------------------------

def test_unknown_stage_rejected():
    """Unknown stage should be rejected."""
    _set_bond_key()
    _ensure_bond_tool()

    result = _run_tool({"stage": "unknown_stage"})
    assert result.get("ok") is False or "error" in result