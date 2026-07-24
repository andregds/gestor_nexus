from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.dependencies import get_current_user, get_db
from models import Plan, Product, User
from schemas.plan import Plan as PlanResponse
from schemas.plan import PlanCreate, PlanUpdate

router = APIRouter(prefix="/plans", tags=["Planos"])


@router.post("/", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
def create_plan(
    plan: PlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_plan = Plan(**plan.dict(), user_id=current_user.id)
    db.add(db_plan)
    db.commit()
    db.refresh(db_plan)
    return db_plan


@router.get("/", response_model=List[PlanResponse])
def read_plans(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Plan)
        .filter(Plan.user_id == current_user.id)
        .order_by(Plan.name.asc())
        .all()
    )


@router.put("/{plan_id}", response_model=PlanResponse)
def update_plan(
    plan_id: int,
    plan: PlanUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_plan = (
        db.query(Plan)
        .filter(Plan.id == plan_id, Plan.user_id == current_user.id)
        .first()
    )
    if not db_plan:
        raise HTTPException(status_code=404, detail="Plano não encontrado")

    update_data = plan.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_plan, key, value)

    db.commit()
    db.refresh(db_plan)
    return db_plan


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_plan = (
        db.query(Plan)
        .filter(Plan.id == plan_id, Plan.user_id == current_user.id)
        .first()
    )
    if not db_plan:
        raise HTTPException(status_code=404, detail="Plano não encontrado")

    linked_products = (
        db.query(Product)
        .filter(Product.plan_id == plan_id, Product.user_id == current_user.id)
        .count()
    )
    if linked_products:
        raise HTTPException(
            status_code=409,
            detail=f"Este plano está vinculado a {linked_products} produto(s).",
        )

    db.delete(db_plan)
    db.commit()
    return None
