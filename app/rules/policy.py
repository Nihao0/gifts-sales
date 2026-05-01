from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from app.models.gift import Gift
from app.schemas.policy import AutomationPolicyFile, PortalsPolicy


@dataclass(frozen=True)
class PolicyDecision:
    gift: Gift
    auto_approved: bool
    reason: str


class AutomationPolicyLoader:
    @staticmethod
    def load(path: str | Path) -> AutomationPolicyFile:
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        return AutomationPolicyFile.model_validate(raw)


class PortalsPolicyEngine:
    @staticmethod
    def plan(gifts: list[Gift], policy: PortalsPolicy) -> list[PolicyDecision]:
        decisions: list[PolicyDecision] = []
        for gift in gifts:
            if not _matches(gift, policy):
                continue
            requires_approval, reason = _requires_approval(gift, policy)
            decisions.append(
                PolicyDecision(
                    gift=gift,
                    auto_approved=policy.auto_approve and not requires_approval,
                    reason=reason,
                )
            )
            if len(decisions) >= policy.max_requests_per_plan:
                break
        return decisions


def _matches(gift: Gift, policy: PortalsPolicy) -> bool:
    match = policy.match
    if gift.owner_peer != match.owner_peer:
        return False
    if gift.transferred_at is not None:
        return False
    if gift.is_for_sale and not match.include_for_sale:
        return False
    if match.title_contains:
        if not gift.title or match.title_contains.lower() not in gift.title.lower():
            return False
    for excluded in match.exclude_title_contains:
        if gift.title and excluded.lower() in gift.title.lower():
            return False
    if match.min_availability_total is not None:
        if gift.availability_total is None or gift.availability_total < match.min_availability_total:
            return False
    if match.max_availability_total is not None:
        if gift.availability_total is None or gift.availability_total > match.max_availability_total:
            return False
    return True


def _requires_approval(gift: Gift, policy: PortalsPolicy) -> tuple[bool, str]:
    rules = policy.require_approval_if
    if (
        rules.max_availability_total_below is not None
        and gift.availability_total is not None
        and gift.availability_total < rules.max_availability_total_below
    ):
        return True, f"availability_total below {rules.max_availability_total_below}"
    for needle in rules.title_contains:
        if gift.title and needle.lower() in gift.title.lower():
            return True, f"title contains {needle!r}"
    return False, "matched portals policy"
