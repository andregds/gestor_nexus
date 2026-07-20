# backend/routes/plans.py
from fastapi import APIRouter, Depends, HTTPException, status
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

@router.put("/{plan_id}", response_model=schemas.Plan)
def update_plan(plan_id: int, plan: schemas.PlanUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db_plan = db.query(models.Plan).filter(models.Plan.id == plan_id, models.Plan.user_id == current_user.id).first()
    if not db_plan:
        raise HTTPException(status_code=404, detail="Plano não encontrado")
    if plan.name is not None:
        db_plan.name = plan.name
    if plan.description is not None:
        db_plan.description = plan.description
    if plan.price is not None:
        db_plan.price = plan.price
    if plan.billing_cycle is not None:
        db_plan.billing_cycle = plan.billing_cycle
    db.commit()
    db.refresh(db_plan)
    return db_plan

@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(plan_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db_plan = db.query(models.Plan).filter(models.Plan.id == plan_id, models.Plan.user_id == current_user.id).first()
    if not db_plan:
        raise HTTPException(status_code=404, detail="Plano não encontrado")
    linked_products = db.query(models.Product).filter(
        models.Product.plan_id == plan_id,
        models.Product.user_id == current_user.id
    ).count()
    if linked_products:
        raise HTTPException(status_code=409, detail=f"Este plano está vinculado a {linked_products} produto(s).")
    db.delete(db_plan)
    db.commit()
