# backend/routes/categories.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import models, schemas
from database import get_db
from auth import get_current_user

router = APIRouter()

@router.post("/", response_model=schemas.Category)
def create_category(category: schemas.CategoryCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db_category = models.Category(**category.dict(), user_id=current_user.id)
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category

@router.get("/", response_model=List[schemas.Category])
def read_categories(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    categories = db.query(models.Category).filter(models.Category.user_id == current_user.id).offset(skip).limit(limit).all()
    return categories

@router.put("/{category_id}", response_model=schemas.Category)
def update_category(category_id: int, category: schemas.CategoryUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db_category = db.query(models.Category).filter(models.Category.id == category_id, models.Category.user_id == current_user.id).first()
    if not db_category:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    if category.name is not None:
        db_category.name = category.name
    if category.description is not None:
        db_category.description = category.description
    db.commit()
    db.refresh(db_category)
    return db_category

@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db_category = db.query(models.Category).filter(models.Category.id == category_id, models.Category.user_id == current_user.id).first()
    if not db_category:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    linked_products = db.query(models.Product).filter(
        models.Product.category_id == category_id,
        models.Product.user_id == current_user.id
    ).count()
    if linked_products:
        raise HTTPException(status_code=409, detail=f"Esta categoria está vinculada a {linked_products} produto(s).")
    db.delete(db_category)
    db.commit()
