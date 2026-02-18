# backend/routes/features.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

import models, schemas
from database import get_db
from auth import get_current_user

router = APIRouter()


@router.post("/", response_model=schemas.Feature)
def create_feature(
    feature: schemas.FeatureCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    db_feature = models.Feature(**feature.dict(), user_id=current_user.id)
    db.add(db_feature)
    db.commit()
    db.refresh(db_feature)
    return db_feature


@router.get("/", response_model=List[schemas.Feature])
def read_features(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    features = (
        db.query(models.Feature)
        .filter(models.Feature.user_id == current_user.id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return features
