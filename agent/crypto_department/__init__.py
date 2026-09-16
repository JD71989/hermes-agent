"""Crypto Intelligence Department for Guardian 2.

Provides market intelligence, ecosystem research, opportunity discovery,
event tracking, and opportunity scoring for cryptocurrency activities.
"""

from agent.crypto_department.opportunity_models import (
    Opportunity,
    OpportunityType,
    OpportunityStatus,
    OpportunitySource,
)
from agent.crypto_department.opportunity_scorer import score_opportunity
from agent.crypto_department.opportunity_store import OpportunityStore

__all__ = [
    "Opportunity",
    "OpportunityType",
    "OpportunityStatus",
    "OpportunitySource",
    "score_opportunity",
    "OpportunityStore",
]
