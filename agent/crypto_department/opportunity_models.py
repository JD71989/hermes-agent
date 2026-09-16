"""Data models for the Crypto Intelligence Department.

Defines opportunity types, scoring dimensions, and status tracking
for the Guardian 2 crypto opportunity engine.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class OpportunityType(str, Enum):
    AIRDROP = "airdrop"
    QUEST = "quest"
    FAUCET = "faucet"
    REWARD = "reward"
    CAMPAIGN = "campaign"
    GRANT = "grant"
    ECOSYSTEM_INCENTIVE = "ecosystem_incentive"
    LIQUIDITY_MINING = "liquidity_mining"
    STAKING_REWARD = "staking_reward"
    TESTNET = "testnet"
    REFERRAL = "referral"
    TRADING_COMPETITION = "trading_competition"
    OTHER = "other"


class OpportunityStatus(str, Enum):
    DISCOVERED = "discovered"
    ELIGIBLE = "eligible"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    CLAIMED = "claimed"
    EXPIRED = "expired"
    INELIGIBLE = "ineligible"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RiskLevel(str, Enum):
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class AutomationPermitted(str, Enum):
    NONE = "none"
    READ_ONLY = "read_only"
    PARTIAL = "partial"
    FULL = "full"


@dataclass
class OpportunitySource:
    """Source metadata for an opportunity."""
    name: str = "unknown"
    url: str = ""
    reliability: float = 0.5
    last_verified: Optional[str] = None
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "OpportunitySource":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ScoringDimensions:
    """Quantitative scoring dimensions for an opportunity."""
    expected_reward_usd: float = 0.0
    fees_usd: float = 0.0
    time_cost_hours: float = 0.0
    time_cost_usd: float = 0.0
    risk_score: float = 0.0
    risk_level: RiskLevel = RiskLevel.MEDIUM
    confidence: float = 0.5
    automation_permit: AutomationPermitted = AutomationPermitted.NONE
    upfront_cost_usd: float = 0.0
    gas_cost_usd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["risk_level"] = self.risk_level.value
        d["automation_permit"] = self.automation_permit.value
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ScoringDimensions":
        rd = dict(d)
        if "risk_level" in rd:
            rd["risk_level"] = RiskLevel(rd["risk_level"])
        if "automation_permit" in rd:
            rd["automation_permit"] = AutomationPermitted(rd["automation_permit"])
        return cls(**{k: v for k, v in rd.items() if k in cls.__dataclass_fields__})


@dataclass
class ScoringResult:
    """Result of opportunity scoring."""
    expected_value_usd: float = 0.0
    total_cost_usd: float = 0.0
    net_value_usd: float = 0.0
    expected_value_per_hour: float = 0.0
    risk_adjusted_value: float = 0.0
    composite_score: float = 0.0
    recommendation: str = ""
    cost_breakdown: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ScoringResult":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Opportunity:
    """A crypto opportunity to discover, score, and track."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    type: OpportunityType = OpportunityType.OTHER
    name: str = ""
    description: str = ""
    project: str = ""
    chain: str = ""
    status: OpportunityStatus = OpportunityStatus.DISCOVERED
    source: OpportunitySource = field(default_factory=OpportunitySource)
    scoring: ScoringDimensions = field(default_factory=ScoringDimensions)
    result: Optional[ScoringResult] = None
    rank: int = 0
    required_actions: List[str] = field(default_factory=list)
    eligibility: List[str] = field(default_factory=list)
    eligibility_met: bool = False
    deadline: Optional[str] = None
    estimated_reward: str = ""
    evidence: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["type"] = self.type.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Opportunity":
        rd = dict(d)
        if "type" in rd:
            rd["type"] = OpportunityType(rd["type"])
        if "status" in rd:
            rd["status"] = OpportunityStatus(rd["status"])
        if "source" in rd and isinstance(rd["source"], dict):
            rd["source"] = OpportunitySource.from_dict(rd["source"])
        if "scoring" in rd and isinstance(rd["scoring"], dict):
            rd["scoring"] = ScoringDimensions.from_dict(rd["scoring"])
        if "result" in rd and isinstance(rd["result"], dict):
            rd["result"] = ScoringResult.from_dict(rd["result"])
        return cls(**{k: v for k, v in rd.items() if k in cls.__dataclass_fields__})

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, s: str) -> "Opportunity":
        return cls.from_dict(json.loads(s))

    def is_active(self) -> bool:
        return self.status not in (
            OpportunityStatus.EXPIRED,
            OpportunityStatus.INELIGIBLE,
            OpportunityStatus.COMPLETED,
            OpportunityStatus.FAILED,
            OpportunityStatus.SKIPPED,
        )

    def is_deadline_approaching(self, hours: int = 24) -> bool:
        if not self.deadline:
            return False
        try:
            dl = datetime.fromisoformat(self.deadline)
            now = datetime.now(timezone.utc)
            delta = dl - now
            return 0 < delta.total_seconds() < hours * 3600
        except (ValueError, TypeError):
            return False
