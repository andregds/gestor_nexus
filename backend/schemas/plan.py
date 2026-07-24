from pydantic import BaseModel
from typing import Optional


class PlanBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    billing_cycle: str


class PlanCreate(PlanBase):
    pass


class PlanUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    billing_cycle: Optional[str] = None


class Plan(PlanBase):
    id: int
    user_id: int

    class Config:
        from_attributes = True
