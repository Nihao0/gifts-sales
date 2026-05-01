"""YAML rule loader and gift-to-rule matcher."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from app.schemas.rule import Rule, RuleFile

if TYPE_CHECKING:
    from app.models.gift import Gift


class RuleLoader:
    @staticmethod
    def load(path: str | Path) -> RuleFile:
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        return RuleFile.model_validate(raw)

    @staticmethod
    def match_gift(gift: "Gift", rule: Rule) -> bool:
        m = rule.match

        if m.title_contains is not None:
            if not gift.title or m.title_contains.lower() not in gift.title.lower():
                return False

        if m.collectible_id is not None:
            if gift.collectible_id != m.collectible_id:
                return False

        if m.is_for_sale is not None:
            if gift.is_for_sale != m.is_for_sale:
                return False

        if m.min_availability_issued is not None:
            if gift.availability_issued is None or gift.availability_issued < m.min_availability_issued:
                return False

        if m.max_availability_issued is not None:
            if gift.availability_issued is None or gift.availability_issued > m.max_availability_issued:
                return False

        if m.min_availability_total is not None:
            if gift.availability_total is None or gift.availability_total < m.min_availability_total:
                return False

        if m.max_availability_total is not None:
            if gift.availability_total is None or gift.availability_total > m.max_availability_total:
                return False

        return True

    @staticmethod
    def apply_rules(gifts: "list[Gift]", rule_file: RuleFile) -> list[tuple["Gift", Rule]]:
        """Return [(gift, matched_rule)] — first matching rule per gift wins."""
        matched: list[tuple[Gift, Rule]] = []
        for gift in gifts:
            for rule in rule_file.rules:
                if RuleLoader.match_gift(gift, rule):
                    matched.append((gift, rule))
                    break
        return matched
