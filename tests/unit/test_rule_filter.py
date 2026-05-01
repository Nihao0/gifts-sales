"""Unit tests for RuleLoader.match_gift and apply_rules."""
from types import SimpleNamespace


from app.rules.loader import RuleLoader
from app.schemas.rule import Rule, RuleFile, RuleMatch


def make_gift(**kwargs) -> SimpleNamespace:
    """
    Lightweight stand-in for Gift — uses SimpleNamespace to avoid SQLAlchemy
    ORM instrumentation that breaks when calling Gift.__new__(Gift) outside
    of a mapped session context.
    """
    defaults = dict(
        id=1,
        telegram_gift_id="abc123",
        msg_id=10,
        collectible_id=999,
        slug="CoolRocket-001",
        title="Cool Rocket",
        availability_issued=150,
        availability_total=1000,
        is_for_sale=False,
        resale_price_stars=None,
        resale_price_ton=None,
    )
    return SimpleNamespace(**{**defaults, **kwargs})


def make_rule(action="list", price_ton=10.0, **match_kwargs) -> Rule:
    return Rule(name="test", match=RuleMatch(**match_kwargs), action=action, price_ton=price_ton)


class TestMatchGift:
    def test_empty_match_hits_all(self):
        assert RuleLoader.match_gift(make_gift(), make_rule()) is True

    def test_title_contains_case_insensitive(self):
        rule = make_rule(title_contains="rocket")
        assert RuleLoader.match_gift(make_gift(title="Cool Rocket"), rule) is True
        assert RuleLoader.match_gift(make_gift(title="Cool Background"), rule) is False

    def test_title_contains_no_title(self):
        rule = make_rule(title_contains="rocket")
        assert RuleLoader.match_gift(make_gift(title=None), rule) is False

    def test_collectible_id_exact(self):
        rule = make_rule(collectible_id=999)
        assert RuleLoader.match_gift(make_gift(collectible_id=999), rule) is True
        assert RuleLoader.match_gift(make_gift(collectible_id=888), rule) is False

    def test_is_for_sale_false(self):
        rule = make_rule(is_for_sale=False)
        assert RuleLoader.match_gift(make_gift(is_for_sale=False), rule) is True
        assert RuleLoader.match_gift(make_gift(is_for_sale=True), rule) is False

    def test_is_for_sale_true(self):
        rule = make_rule(is_for_sale=True)
        assert RuleLoader.match_gift(make_gift(is_for_sale=True), rule) is True

    def test_min_availability_total(self):
        rule = make_rule(min_availability_total=500)
        assert RuleLoader.match_gift(make_gift(availability_total=500), rule) is True
        assert RuleLoader.match_gift(make_gift(availability_total=499), rule) is False
        assert RuleLoader.match_gift(make_gift(availability_total=None), rule) is False

    def test_max_availability_total(self):
        rule = make_rule(max_availability_total=1000)
        assert RuleLoader.match_gift(make_gift(availability_total=1000), rule) is True
        assert RuleLoader.match_gift(make_gift(availability_total=1001), rule) is False

    def test_availability_range(self):
        rule = make_rule(min_availability_total=100, max_availability_total=500)
        assert RuleLoader.match_gift(make_gift(availability_total=300), rule) is True
        assert RuleLoader.match_gift(make_gift(availability_total=50), rule) is False
        assert RuleLoader.match_gift(make_gift(availability_total=600), rule) is False

    def test_min_availability_issued(self):
        rule = make_rule(min_availability_issued=100)
        assert RuleLoader.match_gift(make_gift(availability_issued=100), rule) is True
        assert RuleLoader.match_gift(make_gift(availability_issued=99), rule) is False

    def test_max_availability_issued(self):
        rule = make_rule(max_availability_issued=200)
        assert RuleLoader.match_gift(make_gift(availability_issued=200), rule) is True
        assert RuleLoader.match_gift(make_gift(availability_issued=201), rule) is False

    def test_multi_criteria_and(self):
        rule = make_rule(title_contains="rocket", max_availability_total=1000, is_for_sale=False)
        assert RuleLoader.match_gift(
            make_gift(title="Cool Rocket", availability_total=500, is_for_sale=False), rule
        ) is True
        assert RuleLoader.match_gift(
            make_gift(title="Cool Rocket", availability_total=500, is_for_sale=True), rule
        ) is False


class TestApplyRules:
    def test_first_match_wins(self):
        gifts = [make_gift(id=1, title="Cool Rocket"), make_gift(id=2, title="Nice Background")]
        rule_file = RuleFile(
            rules=[
                Rule(name="r1", match=RuleMatch(title_contains="Rocket"), action="list", price_ton=10.0),
                Rule(name="r2", match=RuleMatch(), action="list", price_ton=5.0),
            ]
        )
        matched = RuleLoader.apply_rules(gifts, rule_file)
        assert len(matched) == 2
        g1, r1 = matched[0]
        assert g1.id == 1
        assert r1.name == "r1"
        g2, r2 = matched[1]
        assert g2.id == 2
        assert r2.name == "r2"

    def test_no_match(self):
        gifts = [make_gift(title="Background")]
        rule_file = RuleFile(
            rules=[Rule(name="r1", match=RuleMatch(title_contains="Rocket"), action="list", price_ton=10.0)]
        )
        matched = RuleLoader.apply_rules(gifts, rule_file)
        assert matched == []

    def test_empty_gifts(self):
        rule_file = RuleFile(rules=[Rule(name="r1", match=RuleMatch(), action="list", price_ton=1.0)])
        assert RuleLoader.apply_rules([], rule_file) == []
