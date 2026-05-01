from typing import Literal

from pydantic import BaseModel, model_validator


class RuleMatch(BaseModel):
    title_contains: str | None = None
    collectible_id: int | None = None
    min_availability_issued: int | None = None
    max_availability_issued: int | None = None
    min_availability_total: int | None = None
    max_availability_total: int | None = None
    is_for_sale: bool | None = None


class Rule(BaseModel):
    name: str
    match: RuleMatch = RuleMatch()
    action: Literal["list", "delist"]
    price_ton: float | None = None
    dry_run: bool = False
    max_attempts: int = 5

    @model_validator(mode="after")
    def price_required_for_list(self) -> "Rule":
        if self.action == "list" and self.price_ton is None:
            raise ValueError("price_ton is required when action='list'")
        if self.price_ton is not None and self.price_ton <= 0:
            raise ValueError("price_ton must be greater than 0")
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be greater than 0")
        return self


class RuleFile(BaseModel):
    rules: list[Rule]
