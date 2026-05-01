from types import SimpleNamespace

from app.rules.policy import PortalsPolicyEngine
from app.schemas.policy import PortalsPolicy


def gift(
    gift_id: int,
    title: str,
    total: int,
    *,
    owner_peer: str = "self",
    is_for_sale: bool = False,
):
    return SimpleNamespace(
        id=gift_id,
        title=title,
        availability_total=total,
        owner_peer=owner_peer,
        is_for_sale=is_for_sale,
        transferred_at=None,
    )


def test_portals_policy_matches_and_limits():
    policy = PortalsPolicy.model_validate(
        {
            "max_requests_per_plan": 1,
            "match": {"min_availability_total": 1000},
        }
    )

    decisions = PortalsPolicyEngine.plan(
        [
            gift(1, "Rare", 500),
            gift(2, "Common", 5000),
            gift(3, "Common 2", 6000),
        ],
        policy,
    )

    assert len(decisions) == 1
    assert decisions[0].gift.id == 2


def test_portals_policy_auto_approval_respects_manual_rules():
    policy = PortalsPolicy.model_validate(
        {
            "auto_approve": True,
            "require_approval_if": {"max_availability_total_below": 5000},
        }
    )

    decisions = PortalsPolicyEngine.plan(
        [
            gift(1, "Needs Review", 1000),
            gift(2, "Auto OK", 9000),
        ],
        policy,
    )

    assert decisions[0].auto_approved is False
    assert decisions[1].auto_approved is True
