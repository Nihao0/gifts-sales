from pydantic import BaseModel, model_validator


class PortalsMatchPolicy(BaseModel):
    owner_peer: str = "self"
    include_for_sale: bool = False
    title_contains: str | None = None
    exclude_title_contains: list[str] = []
    min_availability_total: int | None = None
    max_availability_total: int | None = None


class PortalsApprovalPolicy(BaseModel):
    max_availability_total_below: int | None = None
    title_contains: list[str] = []


class PortalsPolicy(BaseModel):
    name: str = "default_portals"
    recipient: str | None = None
    auto_approve: bool = False
    max_requests_per_plan: int = 10
    match: PortalsMatchPolicy = PortalsMatchPolicy()
    require_approval_if: PortalsApprovalPolicy = PortalsApprovalPolicy()

    @model_validator(mode="after")
    def validate_limits(self) -> "PortalsPolicy":
        if self.max_requests_per_plan <= 0:
            raise ValueError("max_requests_per_plan must be greater than 0")
        return self


class AutomationPolicyFile(BaseModel):
    portals: PortalsPolicy = PortalsPolicy()
