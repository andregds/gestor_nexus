# backend/schemas/feature.py
from pydantic import BaseModel
from typing import Optional

class FeatureBase(BaseModel):
    name: str
    description: Optional[str] = None

class FeatureCreate(FeatureBase):
    pass

class Feature(FeatureBase):
    id: int
    user_id: int

    class Config:
        from_attributes = True
