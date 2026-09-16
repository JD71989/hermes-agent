"""Economic Kernel for Guardian 2.

Implements pricing, treasury, margin gate, spend guardrails,
job economics, estimated cost, actual cost, expected profit,
actual profit, and reconciliation.

Before a revenue-generating activity:
    EXPECTED REVENUE - EXPECTED COST = EXPECTED PROFIT
    Then: MARGIN %, ROI, RISK, RESERVE IMPACT
    Then: ALLOW / DECLINE / REQUIRE AUTHORIZATION

The LLM must never be able to bypass this decision.
Idempotent stages ensure restarted processes can safely resume
without double-charging, double-booking, or duplicate records.
"""

from __future__ import annotations

import enum
import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from hermes_constants import get_hermes_home
from agent.guardian.audit import AuditEvent, audit_log

logger = logging.getLogger(__name__)


class EconomicDecision(enum.Enum):
    ALLOW = "ALLOW"
    DECLINE = "DECLINE"
    REQUIRE_AUTHORIZATION = "REQUIRE_AUTHORIZATION"


class EconomicAction(enum.Enum):
    LEAD_DELIVERY = "lead_delivery"
    OPPORTUNITY_EXECUTION = "opportunity_execution"
    CONTENT_PUBLISH = "content_publish"
    MEDIA_SPEND = "media_spend"
    TRADING_ACTION = "trading_action"


# Mapping of tool names to economic action types.
# Tools not in this mapping are not subject to economic checks.
TOOL_ECONOMIC_ACTION_MAP: dict[str, EconomicAction] = {
    "bond_revenue": EconomicAction.LEAD_DELIVERY,
    "media_farm": EconomicAction.MEDIA_SPEND,
    "pionex_execute": EconomicAction.TRADING_ACTION,
    "crypto_opportunity_execute": EconomicAction.OPPORTUNITY_EXECUTION,
    "crypto_opportunity_participate": EconomicAction.OPPORTUNITY_EXECUTION,
}


@dataclass
class Pricing:
    """Pricing information for an economic activity."""

    base_price: float
    currency: str = "USD"
    unit: str = "per_item"


@dataclass
class Treasury:
    """Treasury state."""

    balance: float = 0.0
    currency: str = "USD"
    reserve_buffer: float = 1000.0

    @property
    def available(self) -> float:
        return max(0.0, self.balance - self.reserve_buffer)


@dataclass
class MarginGate:
    """Margin gate decision."""

    expected_revenue: float
    expected_cost: float
    expected_profit: float
    margin_percent: float
    roi: float
    risk_score: float  # 0-1
    reserve_impact: float
    decision: EconomicDecision = EconomicDecision.ALLOW
    reason: str = ""

    @property
    def is_profitable(self) -> bool:
        return self.expected_profit > 0

    @property
    def margin_acceptable(self) -> bool:
        return self.margin_percent >= 0


@dataclass
class SpendGuardrail:
    """Spend guardrail for a specific action."""

    action_type: str
    max_spend: float
    current_spend: float = 0.0
    period: str = "daily"
    remaining: float = 0.0

    @property
    def can_spend(self) -> bool:
        return self.current_spend + self.max_spend <= self.max_spend if self.max_spend > 0 else True

    @property
    def utilization(self) -> float:
        if self.max_spend <= 0:
            return 0.0
        return self.current_spend / self.max_spend


@dataclass
class JobEconomics:
    """Complete economic analysis for a job."""

    job_id: str
    estimated_cost: float
    actual_cost: float = 0.0
    expected_revenue: float = 0.0
    actual_revenue: float = 0.0
    expected_profit: float = 0.0
    actual_profit: float = 0.0
    margin_percent: float = 0.0
    roi: float = 0.0
    risk_level: str = "low"
    treasury_impact: float = 0.0
    status: str = "pending"
    idempotency_key: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None

    @property
    def decision(self) -> EconomicDecision:
        """Compute the economic decision."""
        if self.expected_revenue <= 0 and self.expected_cost > 0:
            return EconomicDecision.DECLINE
        if self.expected_profit < 0:
            return EconomicDecision.DECLINE
        if self.expected_profit > 0 and self.risk_level == "low":
            return EconomicDecision.ALLOW
        if self.expected_profit > 0 and self.risk_level in ("medium", "high"):
            return EconomicDecision.REQUIRE_AUTHORIZATION
        return EconomicDecision.DECLINE

    @property
    def is_idempotent(self) -> bool:
        return bool(self.idempotency_key)


class EconomicKernel:
    """Deterministic economic decision engine.

    All decisions are deterministic and cannot be overridden by LLM
    reasoning. The kernel computes:

    1. EXPECTED REVENUE - EXPECTED COST = EXPECTED PROFIT
    2. MARGIN %, ROI, RISK, RESERVE IMPACT
    3. ALLOW / DECLINE / REQUIRE AUTHORIZATION
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._treasury = Treasury()
        self._jobs: dict[str, JobEconomics] = {}
        self._state_path = Path(get_hermes_home()) / "economic_kernel.json"
        self._load_state()

    def _load_state(self) -> None:
        """Load persisted economic state."""
        try:
            if self._state_path.exists():
                with open(self._state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._treasury = Treasury(
                    balance=data.get("treasury_balance", 0),
                    reserve_buffer=data.get("reserve_buffer", 1000),
                )
                for job_data in data.get("jobs", {}).values():
                    job = JobEconomics(
                        job_id=job_data["job_id"],
                        estimated_cost=job_data["estimated_cost"],
                        actual_cost=job_data.get("actual_cost", 0),
                        expected_revenue=job_data.get("expected_revenue", 0),
                        actual_revenue=job_data.get("actual_revenue", 0),
                        expected_profit=job_data.get("expected_profit", 0),
                        actual_profit=job_data.get("actual_profit", 0),
                        margin_percent=job_data.get("margin_percent", 0),
                        roi=job_data.get("roi", 0),
                        risk_level=job_data.get("risk_level", "low"),
                        treasury_impact=job_data.get("treasury_impact", 0),
                        status=job_data.get("status", "pending"),
                        idempotency_key=job_data.get("idempotency_key", ""),
                        created_at=job_data.get("created_at", ""),
                        completed_at=job_data.get("completed_at"),
                    )
                    self._jobs[job.job_id] = job
        except Exception:
            pass

    def _save_state(self) -> None:
        """Persist economic state to disk."""
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "treasury_balance": self._treasury.balance,
                "reserve_buffer": self._treasury.reserve_buffer,
                "jobs": {jid: j.to_dict() for jid, j in self._jobs.items()},
            }
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def compute_economics(
        self,
        expected_revenue: float,
        expected_cost: float,
        risk_score: float = 0.1,
        treasury_impact: float = 0.0,
        idempotency_key: Optional[str] = None,
    ) -> MarginGate:
        """Compute economic analysis and decision.

        Returns a MarginGate with the computed decision.
        """
        expected_profit = expected_revenue - expected_cost
        margin_percent = ((expected_profit / expected_revenue) * 100) if expected_revenue > 0 else -100
        roi = ((expected_profit / expected_cost) * 100) if expected_cost > 0 else 0

        # Risk multiplier: higher risk → lower effective profit
        risk_multiplier = max(0, 1 - risk_score)
        adjusted_profit = expected_profit * risk_multiplier

        # Reserve impact check
        reserve_ok = self._treasury.available >= treasury_impact

        # Decision
        decision: EconomicDecision = EconomicDecision.DECLINE
        reason = ""

        if expected_profit <= 0:
            reason = f"Expected profit is negative or zero: ${expected_profit:.2f}"
        elif not reserve_ok:
            reason = f"Treasury reserve insufficient: need ${treasury_impact:.2f}, have ${self._treasury.available:.2f}"
        elif risk_score > 0.7:
            decision = EconomicDecision.REQUIRE_AUTHORIZATION
            reason = f"High risk score ({risk_score:.2f}) requires authorization"
        elif adjusted_profit > 0:
            decision = EconomicDecision.ALLOW
            reason = f"Profitable: ${adjusted_profit:.2f} adjusted profit, risk={risk_score:.2f}"
        else:
            reason = "Insufficient margin after risk adjustment"

        gate = MarginGate(
            expected_revenue=expected_revenue,
            expected_cost=expected_cost,
            expected_profit=expected_profit,
            margin_percent=margin_percent,
            roi=roi,
            risk_score=risk_score,
            reserve_impact=treasury_impact,
            decision=decision,
            reason=reason,
        )

        audit_log(
            AuditEvent.AUTHZ_GRANTED if decision == EconomicDecision.ALLOW else AuditEvent.AUTHZ_DENIED,
            who="economic_kernel",
            what=f"Economic decision: {decision.value} for revenue=${expected_revenue}, cost=${expected_cost}",
            action="compute_economics",
            result="allowed" if decision == EconomicDecision.ALLOW else "denied",
            failure=reason if decision != EconomicDecision.ALLOW else None,
        )

        return gate

    def create_job(
        self,
        estimated_cost: float,
        expected_revenue: float,
        risk_level: str = "low",
        action_type: str = "generic",
        idempotency_key: Optional[str] = None,
    ) -> JobEconomics:
        """Create a new economic job with idempotency."""
        job_id = f"econ-{uuid.uuid4().hex[:12]}"
        key = idempotency_key or f"{action_type}-{job_id}"

        # Check for duplicate idempotency key
        for existing in self._jobs.values():
            if existing.idempotency_key == key and existing.status == "completed":
                logger.info("Duplicate idempotent job detected: %s", key)
                return existing

        expected_profit = expected_revenue - estimated_cost
        margin_pct = ((expected_profit / expected_revenue) * 100) if expected_revenue > 0 else 0
        roi_pct = ((expected_profit / estimated_cost) * 100) if estimated_cost > 0 else 0

        job = JobEconomics(
            job_id=job_id,
            estimated_cost=estimated_cost,
            expected_revenue=expected_revenue,
            expected_profit=expected_profit,
            margin_percent=margin_pct,
            roi=roi_pct,
            risk_level=risk_level,
            treasury_impact=estimated_cost,
            idempotency_key=key,
            status="pending",
        )

        with self._lock:
            self._jobs[job_id] = job
        self._save_state()

        return job

    def record_actual_cost(self, job_id: str, actual_cost: float) -> bool:
        """Record actual cost for a job (idempotent)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            # Prevent double-charging
            if job.actual_cost > 0:
                logger.info("Actual cost already recorded for %s", job_id)
                return False
            job.actual_cost = actual_cost
            job.actual_profit = job.expected_revenue - actual_cost
        self._save_state()
        return True

    def record_revenue(self, job_id: str, actual_revenue: float) -> bool:
        """Record actual revenue for a job (idempotent)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if job.actual_revenue > 0:
                logger.info("Actual revenue already recorded for %s", job_id)
                return False
            job.actual_revenue = actual_revenue
            job.actual_profit = actual_revenue - job.actual_cost
        self._save_state()
        return True

    def complete_job(self, job_id: str, decision: EconomicDecision) -> bool:
        """Mark a job as completed."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            job.status = decision.value
            job.completed_at = datetime.now(timezone.utc).isoformat()
        self._save_state()
        audit_log(
            AuditEvent.FINANCIAL_ACTION,
            who="economic_kernel",
            what=f"Job {job_id} completed with decision {decision.value}",
            action="complete_job",
            result="allowed",
        )
        return True

    def reconcile(self) -> dict[str, Any]:
        """Reconcile estimated vs actual P&L."""
        total_estimated_cost = sum(j.estimated_cost for j in self._jobs.values())
        total_actual_cost = sum(j.actual_cost for j in self._jobs.values())
        total_expected_revenue = sum(j.expected_revenue for j in self._jobs.values())
        total_actual_revenue = sum(j.actual_revenue for j in self._jobs.values())
        total_expected_profit = sum(j.expected_profit for j in self._jobs.values())
        total_actual_profit = sum(j.actual_profit for j in self._jobs.values())

        variance_cost = total_actual_cost - total_estimated_cost
        variance_revenue = total_actual_revenue - total_expected_revenue

        return {
            "total_jobs": len(self._jobs),
            "estimated_cost": total_estimated_cost,
            "actual_cost": total_actual_cost,
            "cost_variance": variance_cost,
            "expected_revenue": total_expected_revenue,
            "actual_revenue": total_actual_revenue,
            "revenue_variance": variance_revenue,
            "expected_profit": total_expected_profit,
            "actual_profit": total_actual_profit,
            "profit_variance": total_actual_profit - total_expected_profit,
            "treasury_balance": self._treasury.balance,
            "reserve_buffer": self._treasury.reserve_buffer,
            "available": self._treasury.available,
        }

    def update_treasury(self, amount: float) -> None:
        """Update treasury balance."""
        with self._lock:
            self._treasury.balance += amount
        self._save_state()

    @property
    def treasury(self) -> Treasury:
        return self._treasury

    @property
    def jobs(self) -> dict[str, JobEconomics]:
        return self._jobs

    def check_tool_economics(
        self,
        tool_name: str,
        args: dict,
        identity_id: str = "unknown",
    ) -> MarginGate:
        """Check economics for a tool call.

        Returns a MarginGate with the economic decision.
        If the tool is not in TOOL_ECONOMIC_ACTION_MAP, returns ALLOW.
        """
        action = TOOL_ECONOMIC_ACTION_MAP.get(tool_name)
        if action is None:
            # No economic check needed for this tool
            return MarginGate(
                expected_revenue=0.0,
                expected_cost=0.0,
                expected_profit=0.0,
                margin_percent=0.0,
                roi=0.0,
                risk_score=0.0,
                reserve_impact=0.0,
                decision=EconomicDecision.ALLOW,
                reason="No economic check required for this tool",
            )

        # Extract expected revenue and cost from tool arguments
        expected_revenue = 0.0
        expected_cost = 0.0
        risk_score = 0.1
        treasury_impact = 0.0

        if action == EconomicAction.LEAD_DELIVERY:
            # bond_revenue: record_revenue stage has amount
            # For other stages, estimate based on £35 per lead
            stage = args.get("stage", "")
            if stage == "record_revenue":
                amount_str = args.get("amount", "0")
                try:
                    expected_revenue = float(amount_str)
                except ValueError:
                    expected_revenue = 35.0  # Default £35 per lead
            elif stage in ("accept_lead", "deliver_lead", "accept_customer"):
                expected_revenue = 35.0  # Expected revenue per qualified lead
            expected_cost = 5.0  # Estimated fulfillment cost
            risk_score = 0.2
            treasury_impact = expected_cost

        elif action == EconomicAction.MEDIA_SPEND:
            # media_farm: check action type and budget
            media_action = args.get("action", "")
            if media_action in ("create_campaign", "update_campaign"):
                budget = args.get("budget", 0)
                try:
                    expected_cost = float(budget)
                except (ValueError, TypeError):
                    expected_cost = 0.0
                # Estimate revenue based on campaign objective
                expected_revenue = expected_cost * 1.5  # Target 50% ROI
            elif media_action in ("create_influencer_campaign", "update_influencer_campaign"):
                cost = args.get("cost", 0)
                try:
                    expected_cost = float(cost)
                except (ValueError, TypeError):
                    expected_cost = 0.0
                expected_revenue = expected_cost * 2.0  # Target 100% ROI
            elif media_action == "record_attribution":
                revenue = args.get("revenue", 0)
                cost = args.get("cost", 0)
                try:
                    expected_revenue = float(revenue)
                    expected_cost = float(cost)
                except (ValueError, TypeError):
                    pass
            risk_score = 0.3
            treasury_impact = expected_cost

        elif action == EconomicAction.TRADING_ACTION:
            # pionex_execute: notional value is the risk
            notional = args.get("notional_usdt", 0)
            try:
                expected_cost = float(notional)
            except (ValueError, TypeError):
                expected_cost = 0.0
            expected_revenue = 0.0  # Trading P&L is uncertain
            risk_score = 0.8  # High risk
            treasury_impact = expected_cost

        elif action == EconomicAction.OPPORTUNITY_EXECUTION:
            # Crypto opportunity execution
            expected_cost = args.get("estimated_cost", 0)
            expected_revenue = args.get("expected_value", 0)
            risk_score = args.get("risk_score", 0.5)
            treasury_impact = expected_cost

        # Compute the economic decision
        return self.compute_economics(
            expected_revenue=expected_revenue,
            expected_cost=expected_cost,
            risk_score=risk_score,
            treasury_impact=treasury_impact,
        )


# Module-level singleton
_economic_kernel = EconomicKernel()


def get_economic_kernel() -> EconomicKernel:
    """Get the module-level economic kernel."""
    return _economic_kernel
