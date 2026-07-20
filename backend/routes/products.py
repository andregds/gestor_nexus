from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import models, schemas
from database import get_db
from auth import get_current_user

router = APIRouter()


def _get_owned_category(db: Session, category_id: int, user_id: int):
    return db.query(models.Category).filter(
        models.Category.id == category_id,
        models.Category.user_id == user_id
    ).first()


def _get_owned_plan(db: Session, plan_id: int, user_id: int):
    return db.query(models.Plan).filter(
        models.Plan.id == plan_id,
        models.Plan.user_id == user_id
    ).first()


@router.post("/", response_model=schemas.Product)
def create_product(product: schemas.ProductCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    category = _get_owned_category(db, product.category_id, current_user.id)
    if not category:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    plan = _get_owned_plan(db, product.plan_id, current_user.id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plano não encontrado")

    db_product = models.Product(**product.dict(), user_id=current_user.id)
    db_product.price = plan.price
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product


@router.get("/", response_model=List[schemas.Product])
def read_products(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    products = db.query(models.Product).filter(models.Product.user_id == current_user.id).offset(skip).limit(limit).all()
    return products


@router.put("/{product_id}", response_model=schemas.Product)
def update_product(product_id: int, product: schemas.ProductUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db_product = db.query(models.Product).filter(models.Product.id == product_id, models.Product.user_id == current_user.id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    if product.name is not None:
        db_product.name = product.name
    if product.description is not None:
        db_product.description = product.description
    if product.category_id is not None:
        category = _get_owned_category(db, product.category_id, current_user.id)
        if not category:
            raise HTTPException(status_code=404, detail="Categoria não encontrada")
        db_product.category_id = product.category_id

    effective_plan_id = product.plan_id if product.plan_id is not None else db_product.plan_id
    if effective_plan_id is None:
        raise HTTPException(status_code=404, detail="Plano não encontrado")
    plan = _get_owned_plan(db, effective_plan_id, current_user.id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plano não encontrado")
    db_product.plan_id = effective_plan_id
    db_product.price = plan.price

    db.commit()
    db.refresh(db_product)
    return db_product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db_product = db.query(models.Product).filter(models.Product.id == product_id, models.Product.user_id == current_user.id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    db.delete(db_product)
    db.commit()
