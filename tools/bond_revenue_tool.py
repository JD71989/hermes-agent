"""Bond ↔ Hermes revenue and lead pipeline.

Manages the full lead lifecycle from initial traffic through to revenue
realisation, with UK and Australia support.

Pipeline: traffic → enquiry → lead → validation → qualification →
deduplication → accept/reject → delivery → customer acceptance →
revenue → feedback → optimisation.

£35 per accepted qualified lead.

Environment gating: check_fn requires BOND_API_KEY set.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tools.registry import registry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment check
# ---------------------------------------------------------------------------

BOND_API_KEY_ENV = "BOND_API_KEY"


def check_requirements() -> bool:
    """Check_fn for the bond_revenue tool.

    Returns True when BOND_API_KEY is set, indicating the environment
    is configured for Bond integration. The tool is only available when
    the required env var is present.
    """
    return bool(os.getenv(BOND_API_KEY_ENV))


# ---------------------------------------------------------------------------
# Pipeline stage types (internal constants)
# ---------------------------------------------------------------------------

TrafficSource = str
EnquiryData = Dict[str, Any]
LeadStatus = str
RevenueResult = Dict[str, Any]


# ---------------------------------------------------------------------------
# Pipeline data models
# ---------------------------------------------------------------------------

class BondLead:
    """Represents a qualified lead through the pipeline."""

    def __init__(
        self,
        lead_id: str,
        enquiry_id: str,
        source: TrafficSource,
        visitor_id: str,
        country: str,  # "UK" or "AU"
        postcode: Optional[str] = None,
        property_type: Optional[str] = None,
        budget: Optional[Decimal] = None,
        created_at: Optional[datetime] = None,
        status: LeadStatus = "enquiry",
        qualified: bool = False,
        accepted: bool = False,
        delivered: bool = False,
        revenue: Optional[Decimal] = None,
        feedback: Optional[str] = None,
    ):
        self.lead_id = lead_id
        self.enquiry_id = enquiry_id
        self.source = source
        self.visitor_id = visitor_id
        self.country = country
        self.postcode = postcode
        self.property_type = property_type
        self.budget = budget
        self.created_at = created_at or datetime.utcnow()
        self.status = status
        self.qualified = qualified
        self.accepted = accepted
        self.delivered = delivered
        self.revenue = revenue
        self.feedback = feedback

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lead_id": self.lead_id,
            "enquiry_id": self.enquiry_id,
            "source": self.source,
            "visitor_id": self.visitor_id,
            "country": self.country,
            "postcode": self.postcode,
            "property_type": self.property_type,
            "budget": str(self.budget) if self.budget else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "status": self.status,
            "qualified": self.qualified,
            "accepted": self.accepted,
            "delivered": self.delivered,
            "revenue": str(self.revenue) if self.revenue else None,
            "feedback": self.feedback,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BondLead":
        return cls(
            lead_id=data["lead_id"],
            enquiry_id=data["enquiry_id"],
            source=data["source"],
            visitor_id=data["visitor_id"],
            country=data["country"],
            postcode=data.get("postcode"),
            property_type=data.get("property_type"),
            budget=Decimal(data["budget"]) if data.get("budget") else None,
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            status=data.get("status", "enquiry"),
            qualified=data.get("qualified", False),
            accepted=data.get("accepted", False),
            delivered=data.get("delivered", False),
            revenue=Decimal(data["revenue"]) if data.get("revenue") else None,
            feedback=data.get("feedback"),
        )


# ---------------------------------------------------------------------------
# Pipeline state management (persisted to HERMES_HOME)
# ---------------------------------------------------------------------------

_guardian_task_state_path = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))) / "bond_lead_state.json"


def _load_lead_state() -> Dict[str, Any]:
    """Load the persisted lead state from disk (across restarts)."""
    try:
        if _guardian_task_state_path.exists():
            with open(_guardian_task_state_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as exc:
        logger.debug("Failed to load bond lead state: %s", exc)
    return {"leads": {}, "next_lead_id": 1}


def _save_lead_state(state: Dict[str, Any]) -> None:
    """Persist the lead state to disk."""
    try:
        _guardian_task_state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(_guardian_task_state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.debug("Failed to save bond lead state: %s", exc)


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------

def create_enquiry(
    visitor_id: str,
    source: TrafficSource,
    country: str,
    postcode: Optional[str] = None,
    property_type: Optional[str] = None,
) -> str:
    """Stage 1: Create an enquiry from traffic.

    Args:
        visitor_id: Unique visitor identifier
        source: Traffic source (e.g., "web", "social", "referral")
        country: "UK" or "AU"
        postcode: Optional postcode
        property_type: Optional property type

    Returns:
        enquiry_id for tracking
    """
    # In a real system, this would create an enquiry record
    # For now, we just log and return a tracking ID
    enquiry_id = f"env-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{visitor_id[-6:]}"
    logger.info(
        "Enquiry created: id=%s visitor=%s source=%s country=%s",
        enquiry_id, visitor_id, source, country,
    )
    return enquiry_id


def validate_lead(
    enquiry_id: str,
    visitor_id: str,
    country: str,
    postcode: Optional[str] = None,
    property_type: Optional[str] = None,
) -> Optional[BondLead]:
    """Stage 3: Validate a lead from enquiry.

    Performs basic validation including:
    - Country must be UK or AU
    - Postcode must be valid format for country
    - Property type must be relevant

    Returns:
        BondLead if valid, None if invalid
    """
    import re
    if country not in ("UK", "AU"):
        logger.warning("Validation failed: country=%s not supported", country)
        return None

    # Postcode validation by country
    if postcode:
        p = postcode.strip().upper()
        if country == "UK":
            # UK postcode format: e.g., "SW1A 1AA"
            import re
            if not re.match(r"^[A-Z]{1,2}[0-9][0-9A-Z]?\s?[0-9][A-Z]{2}$", p):
                logger.warning("Validation failed: UK postcode=%s invalid", postcode)
                return None
        elif country == "AU":
            # Australian postcode format: e.g., "2000"
            if not re.match(r"^[0-9]{4}$", p):
                logger.warning("Validation failed: AU postcode=%s invalid", postcode)
                return None

    lead_id = f"lead-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{enquiry_id[-6:]}"
    lead = BondLead(
        lead_id=lead_id,
        enquiry_id=enquiry_id,
        source="validated",  # Will be updated
        visitor_id=visitor_id,
        country=country,
        postcode=postcode,
        property_type=property_type,
        status="validation",
    )
    logger.info("Lead validated: id=%s", lead_id)
    return lead


def qualify_lead(
    lead: BondLead,
    budget_threshold: Optional[Decimal] = Decimal("10000"),
) -> BondLead:
    """Stage 4: Qualify a lead.

    Qualification criteria:
    - Country is UK or AU (already validated)
    - Postcode is valid (already validated)
    - Budget meets minimum threshold (optional)

    Args:
        lead: The lead to qualify
        budget_threshold: Minimum budget in GBP/AUD for qualification

    Returns:
        Qualified BondLead or lead with qualification=False
    """
    lead.status = "qualification"

    # Check budget if threshold provided
    if budget_threshold is not None:
        if lead.budget is None:
            lead.qualified = False
            logger.info(
                "Lead %s not qualified: budget not set, cannot verify against threshold %.2f",
                lead.lead_id, budget_threshold,
            )
            return lead
        if lead.budget < budget_threshold:
            lead.qualified = False
            logger.info(
                "Lead %s not qualified: budget %.2f below threshold %.2f",
                lead.lead_id, lead.budget, budget_threshold,
            )
            return lead

    lead.qualified = True
    lead.status = "qualified"
    logger.info("Lead %s qualified", lead.lead_id)
    return lead


def deduplicate_leads(
    leads: List[BondLead],
) -> List[BondLead]:
    """Stage 5: Deduplicate leads.

    Removes duplicate leads based on visitor_id + postcode + property_type
    combination for the same country.

    Returns:
        List of unique leads
    """
    seen: set = set()
    unique: List[BondLead] = []

    for lead in leads:
        key = (lead.visitor_id, lead.country, lead.postcode, lead.property_type)
        if key in seen:
            logger.info("Lead %s is a duplicate (key=%s)", lead.lead_id, key)
            continue
        seen.add(key)
        unique.append(lead)

    if len(unique) < len(leads):
        logger.info(
            "Deduplication removed %d duplicate leads",
            len(leads) - len(unique),
        )

    return unique


def accept_lead(
    lead: BondLead,
    acceptor_id: str,
) -> BondLead:
    """Stage 6: Accept a lead.

    Moves lead from qualified to accepted state.

    Args:
        lead: The lead to accept
        acceptor_id: ID of the person/ system accepting the lead

    Returns:
        Updated BondLead with accepted=True
    """
    lead.accepted = True
    lead.status = "accepted"
    logger.info("Lead %s accepted by %s", lead.lead_id, acceptor_id)
    return lead


def reject_lead(
    lead: BondLead,
    rejector_id: str,
    reason: str = "",
) -> BondLead:
    """Stage 6: Reject a lead.

    Moves lead to rejected state.

    Args:
        lead: The lead to reject
        rejector_id: ID of the person/ system rejecting the lead
        reason: Optional rejection reason

    Returns:
        Updated BondLead with accepted=False
    """
    lead.status = "rejected"
    logger.info(
        "Lead %s rejected by %s: %s",
        lead.lead_id, rejector_id, reason or "(no reason)",
    )
    return lead


def deliver_lead(
    lead: BondLead,
    delivery_id: str,
    delivery_method: str = "email",
) -> BondLead:
    """Stage 7: Deliver the lead to the sales team.

    Args:
        lead: The lead to deliver
        delivery_id: Unique delivery identifier
        delivery_method: "email", "sms", "portal", etc.

    Returns:
        Updated BondLead with delivered=True
    """
    lead.delivered = True
    lead.status = "delivered"
    logger.info(
        "Lead %s delivered via %s (id=%s)",
        lead.lead_id, delivery_method, delivery_id,
    )
    return lead


def accept_customer(
    lead: BondLead,
    accepter_id: str,
) -> BondLead:
    """Stage 8: Customer acceptance.

    Marks that the customer has accepted the offer/proposal.

    Args:
        lead: The lead
        accepter_id: ID of the person recording acceptance

    Returns:
        Updated BondLead
    """
    lead.status = "customer_accepted"
    logger.info(
        "Lead %s customer accepted by %s",
        lead.lead_id, accepter_id,
    )
    return lead


def record_revenue(
    lead: BondLead,
    amount: Decimal,
    currency: str = "GBP",
) -> BondLead:
    """Stage 9: Record revenue from accepted lead.

    £35 per accepted qualified lead.

    Args:
        lead: The lead
        amount: Revenue amount
        currency: "GBP" for UK, "AUD" for Australia

    Returns:
        Updated BondLead with revenue recorded
    """
    lead.revenue = amount
    lead.status = "revenue_recorded"
    logger.info(
        "Lead %s revenue recorded: %.2f %s",
        lead.lead_id, amount, currency,
    )
    return lead


def record_feedback(
    lead: BondLead,
    feedback: str,
    feedback_by: str,
) -> BondLead:
    """Stage 10: Record feedback.

    Args:
        lead: The lead
        feedback: Feedback text
        feedback_by: Who provided the feedback

    Returns:
        Updated BondLead
    """
    lead.feedback = feedback
    logger.info(
        "Lead %s feedback by %s: %s",
        lead.lead_id, feedback_by, feedback[:80] if feedback else "",
    )
    return lead


def optimise_pipeline(
    state: Dict[str, Any],
) -> Dict[str, Any]:
    """Stage 11: Optimise the pipeline.

    Analyzes pipeline performance and returns optimization suggestions.

    Args:
        state: Current pipeline state

    Returns:
        Optimization suggestions dict
    """
    leads = state.get("leads", [])
    if not leads:
        return {"suggestions": [], "summary": "No leads to analyze"}

    total = len(leads)
    qualified = sum(1 for l in leads if l.get("qualified"))
    accepted = sum(1 for l in leads if l.get("accepted"))
    revenue_total = sum(
        Decimal(l.get("revenue", "0")) for l in leads if l.get("revenue")
    )

    conversion_rate = (accepted / total * 100) if total > 0 else 0
    qualification_rate = (qualified / total * 100) if total > 0 else 0
    revenue_per_lead = (revenue_total / accepted) if accepted > 0 else Decimal("0")

    suggestions: List[str] = []

    if qualification_rate < 50:
        suggestions.append(
            "Low qualification rate - review validation criteria"
        )

    if conversion_rate < 20:
        suggestions.append(
            "Low acceptance rate - review lead quality or offer"
        )

    if revenue_per_lead < Decimal("35"):
        suggestions.append(
            f"Revenue per lead (£{revenue_per_lead:.2f}) below target (£35) - "
            "review qualification criteria or pricing"
        )

    # Country breakdown
    uk_leads = [l for l in leads if l.get("country") == "UK"]
    au_leads = [l for l in leads if l.get("country") == "AU"]

    if uk_leads and au_leads:
        uk_accepted = sum(1 for l in uk_leads if l.get("accepted"))
        au_accepted = sum(1 for l in au_leads if l.get("accepted"))
        uk_rate = (uk_accepted / len(uk_leads) * 100) if uk_leads else 0
        au_rate = (au_accepted / len(au_leads) * 100) if au_leads else 0
        suggestions.append(
            f"UK acceptance rate: {uk_rate:.1f}%, AU acceptance rate: {au_rate:.1f}%"
        )

    return {
        "suggestions": suggestions,
        "summary": {
            "total_leads": total,
            "qualified": qualified,
            "accepted": accepted,
            "revenue_total": str(revenue_total),
            "conversion_rate_pct": round(conversion_rate, 2),
            "qualification_rate_pct": round(qualification_rate, 2),
            "revenue_per_lead": str(revenue_per_lead),
        },
    }


# ---------------------------------------------------------------------------
# Tool handler
# ---------------------------------------------------------------------------

def handle_bond_revenue_tool(
    args: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> str:
    """Handle the bond_revenue tool call.

    This is the handler called by the tool registry when the bond_revenue
    tool is invoked. Dispatches to the appropriate pipeline stage based
    on the request type.

    Args:
        args: Command arguments containing "stage" and stage-specific params
        **kwargs: Additional kwargs (task_id, etc.)

    Returns:
        JSON string result
    """
    if args is None:
        args = {}

    stage = args.get("stage", "")
    request_id = args.get("request_id", "")

    # Load persisted state
    state = _load_lead_state()

    # Dispatch to appropriate stage handler
    if stage == "create_enquiry":
        visitor_id = args.get("visitor_id", "")
        source = args.get("source", "web")
        country = args.get("country", "")
        postcode = args.get("postcode")
        property_type = args.get("property_type")

        if not visitor_id or not country:
            return json.dumps({
                "ok": False,
                "error": "visitor_id and country are required",
            })

        enquiry_id = create_enquiry(
            visitor_id=visitor_id,
            source=source,
            country=country,
            postcode=postcode,
            property_type=property_type,
        )

        # Persist the enquiry as a lead in initial state
        lead_id = f"lead-{enquiry_id}"
        state.setdefault("leads", {})[lead_id] = BondLead(
            lead_id=lead_id,
            enquiry_id=enquiry_id,
            source=source,
            visitor_id=visitor_id,
            country=country,
            postcode=postcode,
            property_type=property_type,
            status="enquiry",
        ).to_dict()
        _save_lead_state(state)

        return json.dumps({
            "ok": True,
            "enquiry_id": enquiry_id,
            "lead_id": lead_id,
            "stage": "enquiry",
        })

    elif stage == "validate_lead":
        enquiry_id = args.get("enquiry_id", "")
        visitor_id = args.get("visitor_id", "")
        country = args.get("country", "")
        postcode = args.get("postcode")
        property_type = args.get("property_type")

        if not enquiry_id or not country:
            return json.dumps({
                "ok": False,
                "error": "enquiry_id and country are required",
            })

        lead = validate_lead(
            enquiry_id=enquiry_id,
            visitor_id=visitor_id,
            country=country,
            postcode=postcode,
            property_type=property_type,
        )

        if lead is None:
            return json.dumps({
                "ok": False,
                "error": "Lead validation failed - check country/postcode format",
            })

        # Update state
        lead_dict = lead.to_dict()
        lead_key = lead.lead_id
        state.setdefault("leads", {})[lead_key] = lead_dict
        _save_lead_state(state)

        return json.dumps({
            "ok": True,
            "lead_id": lead_key,
            "lead": lead_dict,
            "stage": "validation",
        })

    elif stage == "qualify_lead":
        lead_id = args.get("lead_id", "")
        budget_threshold_str = args.get("budget_threshold")

        if not lead_id:
            return json.dumps({
                "ok": False,
                "error": "lead_id is required",
            })

        budget_threshold = None
        if budget_threshold_str:
            try:
                budget_threshold = Decimal(budget_threshold_str)
            except Exception:
                pass

        lead_dict = state.get("leads", {}).get(lead_id)
        if lead_dict is None:
            return json.dumps({
                "ok": False,
                "error": f"Lead {lead_id} not found",
            })

        lead = BondLead.from_dict(lead_dict)
        lead = qualify_lead(lead, budget_threshold=budget_threshold)
        lead_dict = lead.to_dict()
        state.setdefault("leads", {})[lead_id] = lead_dict
        _save_lead_state(state)

        return json.dumps({
            "ok": True,
            "lead_id": lead_id,
            "lead": lead_dict,
            "stage": "qualification",
            "qualified": lead.qualified,
        })

    elif stage == "deduplicate":
        leads_data = state.get("leads", {})
        leads = [BondLead.from_dict(l) for l in leads_data.values()]
        unique = deduplicate_leads(leads)
        unique_dicts = [l.to_dict() for l in unique]

        # Replace state with deduplicated leads
        state["leads"] = {l.lead_id: l.to_dict() for l in unique}
        _save_lead_state(state)

        return json.dumps({
            "ok": True,
            "original_count": len(leads_data),
            "unique_count": len(unique_dicts),
            "removed": len(leads_data) - len(unique_dicts),
            "stage": "deduplication",
        })

    elif stage == "accept_lead":
        lead_id = args.get("lead_id", "")
        acceptor_id = args.get("acceptor_id", "")

        if not lead_id or not acceptor_id:
            return json.dumps({
                "ok": False,
                "error": "lead_id and acceptor_id are required",
            })

        lead_dict = state.get("leads", {}).get(lead_id)
        if lead_dict is None:
            return json.dumps({
                "ok": False,
                "error": f"Lead {lead_id} not found",
            })

        lead = BondLead.from_dict(lead_dict)
        lead = accept_lead(lead, acceptor_id=acceptor_id)
        lead_dict = lead.to_dict()
        state.setdefault("leads", {})[lead_id] = lead_dict
        _save_lead_state(state)

        return json.dumps({
            "ok": True,
            "lead_id": lead_id,
            "lead": lead_dict,
            "stage": "acceptance",
            "accepted": lead.accepted,
        })

    elif stage == "reject_lead":
        lead_id = args.get("lead_id", "")
        rejector_id = args.get("rejector_id", "")
        reason = args.get("reason", "")

        if not lead_id or not rejector_id:
            return json.dumps({
                "ok": False,
                "error": "lead_id and rejector_id are required",
            })

        lead_dict = state.get("leads", {}).get(lead_id)
        if lead_dict is None:
            return json.dumps({
                "ok": False,
                "error": f"Lead {lead_id} not found",
            })

        lead = BondLead.from_dict(lead_dict)
        lead = reject_lead(lead, rejector_id=rejector_id, reason=reason)
        lead_dict = lead.to_dict()
        state.setdefault("leads", {})[lead_id] = lead_dict
        _save_lead_state(state)

        return json.dumps({
            "ok": True,
            "lead_id": lead_id,
            "lead": lead_dict,
            "stage": "rejection",
            "accepted": lead.accepted,
        })

    elif stage == "deliver_lead":
        lead_id = args.get("lead_id", "")
        delivery_id = args.get("delivery_id", "")
        delivery_method = args.get("delivery_method", "email")

        if not lead_id or not delivery_id:
            return json.dumps({
                "ok": False,
                "error": "lead_id and delivery_id are required",
            })

        lead_dict = state.get("leads", {}).get(lead_id)
        if lead_dict is None:
            return json.dumps({
                "ok": False,
                "error": f"Lead {lead_id} not found",
            })

        lead = BondLead.from_dict(lead_dict)
        lead = deliver_lead(lead, delivery_id=delivery_id, delivery_method=delivery_method)
        lead_dict = lead.to_dict()
        state.setdefault("leads", {})[lead_id] = lead_dict
        _save_lead_state(state)

        return json.dumps({
            "ok": True,
            "lead_id": lead_id,
            "lead": lead_dict,
            "stage": "delivery",
            "delivered": lead.delivered,
        })

    elif stage == "accept_customer":
        lead_id = args.get("lead_id", "")
        accepter_id = args.get("accepter_id", "")

        if not lead_id or not accepter_id:
            return json.dumps({
                "ok": False,
                "error": "lead_id and accepter_id are required",
            })

        lead_dict = state.get("leads", {}).get(lead_id)
        if lead_dict is None:
            return json.dumps({
                "ok": False,
                "error": f"Lead {lead_id} not found",
            })

        lead = BondLead.from_dict(lead_dict)
        lead = accept_customer(lead, accepter_id=accepter_id)
        lead_dict = lead.to_dict()
        state.setdefault("leads", {})[lead_id] = lead_dict
        _save_lead_state(state)

        return json.dumps({
            "ok": True,
            "lead_id": lead_id,
            "lead": lead_dict,
            "stage": "customer_acceptance",
            "status": lead.status,
        })

    elif stage == "record_revenue":
        lead_id = args.get("lead_id", "")
        amount_str = args.get("amount", "")
        currency = args.get("currency", "GBP")

        if not lead_id or not amount_str:
            return json.dumps({
                "ok": False,
                "error": "lead_id and amount are required",
            })

        try:
            amount = Decimal(amount_str)
        except Exception:
            return json.dumps({
                "ok": False,
                "error": f"Invalid amount: {amount_str}",
            })

        lead_dict = state.get("leads", {}).get(lead_id)
        if lead_dict is None:
            return json.dumps({
                "ok": False,
                "error": f"Lead {lead_id} not found",
            })

        lead = BondLead.from_dict(lead_dict)
        lead = record_revenue(lead, amount=amount, currency=currency)
        lead_dict = lead.to_dict()
        state.setdefault("leads", {})[lead_id] = lead_dict
        _save_lead_state(state)

        return json.dumps({
            "ok": True,
            "lead_id": lead_id,
            "lead": lead_dict,
            "stage": "revenue",
            "revenue": str(lead.revenue),
            "currency": currency,
        })

    if stage == "record_feedback":
        lead_id = args.get("lead_id", "")
        feedback = args.get("feedback", "")
        feedback_by = args.get("feedback_by", "")

        if not lead_id or not feedback:
            return json.dumps({
                "ok": False,
                "error": "lead_id and feedback are required",
            })

        lead_dict = state.get("leads", {}).get(lead_id)
        if lead_dict is None:
            return json.dumps({
                "ok": False,
                "error": f"Lead {lead_id} not found",
            })

        lead = BondLead.from_dict(lead_dict)
        lead = record_feedback(lead, feedback=feedback, feedback_by=feedback_by)
        lead_dict = lead.to_dict()
        state.setdefault("leads", {})[lead_id] = lead_dict
        _save_lead_state(state)

    if stage == "record_feedback":
        return json.dumps({
            "ok": True,
            "lead_id": lead_id,
            "lead": lead_dict,
            "stage": "feedback",
            "feedback": lead.feedback,
        })

    elif stage == "optimise":
        suggestions = optimise_pipeline(state)
        return json.dumps({
            "ok": True,
            "stage": "optimisation",
            **suggestions,
        })

    else:
        return json.dumps({
            "ok": False,
            "error": f"Unknown stage: {stage}",
            "available_stages": [
                "create_enquiry",
                "validate_lead",
                "qualify_lead",
                "deduplicate",
                "accept_lead",
                "reject_lead",
                "deliver_lead",
                "accept_customer",
                "record_revenue",
                "record_feedback",
                "optimise",
            ],
        })


# ---------------------------------------------------------------------------
# Tool registration at module level (auto-discovered on import)
# ---------------------------------------------------------------------------

registry.register(
    name="bond_revenue",
    toolset="bond",
    schema={
        "type": "object",
        "properties": {
            "stage": {
                "type": "string",
                "enum": [
                    "create_enquiry",
                    "validate_lead",
                    "qualify_lead",
                    "deduplicate",
                    "accept_lead",
                    "reject_lead",
                    "deliver_lead",
                    "accept_customer",
                    "record_revenue",
                    "record_feedback",
                    "optimise",
                ],
                "description": "Pipeline stage to execute",
            },
            "request_id": {
                "type": "string",
                "description": "Unique request identifier for tracking",
            },
            "visitor_id": {
                "type": "string",
                "description": "Unique visitor identifier from traffic",
            },
            "source": {
                "type": "string",
                "description": "Traffic source (e.g., web, social, referral)",
            },
            "country": {
                "type": "string",
                "description": "Country: UK or AU",
            },
            "postcode": {
                "type": "string",
                "description": "Postcode (UK format: SW1A 1AA, AU format: 2000)",
            },
            "property_type": {
                "type": "string",
                "description": "Property type (e.g., flat, house, apartment)",
            },
            "lead_id": {
                "type": "string",
                "description": "Existing lead identifier",
            },
            "acceptor_id": {
                "type": "string",
                "description": "ID of person/system accepting the lead",
            },
            "rejector_id": {
                "type": "string",
                "description": "ID of person/system rejecting the lead",
            },
            "reason": {
                "type": "string",
                "description": "Optional rejection reason",
            },
            "delivery_id": {
                "type": "string",
                "description": "Unique delivery identifier",
            },
            "delivery_method": {
                "type": "string",
                "description": "Delivery method (email, sms, portal)",
            },
            "accepter_id": {
                "type": "string",
                "description": "ID of person recording customer acceptance",
            },
            "amount": {
                "type": "string",
                "description": "Revenue amount (e.g., '35' for £35)",
            },
            "currency": {
                "type": "string",
                "description": "Currency: GBP or AUD",
            },
            "feedback": {
                "type": "string",
                "description": "Feedback text",
            },
            "feedback_by": {
                "type": "string",
                "description": "Who provided the feedback",
            },
            "budget_threshold": {
                "type": "string",
                "description": "Minimum budget threshold for qualification",
            },
        },
        "required": ["stage"],
        "description": "Bond revenue pipeline tool - manage lead lifecycle from traffic to revenue",
    },
    handler=handle_bond_revenue_tool,
    check_fn=check_requirements,
    requires_env=[BOND_API_KEY_ENV],
    description="Bond revenue and lead pipeline - traffic to revenue with UK/AU support",
)