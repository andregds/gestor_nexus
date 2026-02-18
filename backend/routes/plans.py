# backend/routes/plans.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import models, schemas
from database import get_db
from auth import get_current_user

router = APIRouter()

@router.post("/", response_model=schemas.Plan)
def create_plan(plan: schemas.PlanCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db_plan = models.Plan(**plan.dict(), user_id=current_user.id)
    db.add(db_plan)
    db.commit()
    db.refresh(db_plan)
    return db_plan

@router.get("/", response_model=List[schemas.Plan])
def read_plans(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    plans = db.query(models.Plan).filter(models.Plan.user_id == current_user.id).offset(skip).limit(limit).all()
    return plans

