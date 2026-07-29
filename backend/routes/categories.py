from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.dependencies import get_current_user, get_db
from models import Category, Product, User
from schemas.category import Category as CategoryResponse
from schemas.category import CategoryCreate, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["Categorias"])
catalog_router = APIRouter(prefix="/users/me/catalog", tags=["Catálogo"])


@router.post("/", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
@catalog_router.post("/categories/", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    category: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_category = Category(**category.dict(), user_id=current_user.id)
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category


@router.get("/", response_model=List[CategoryResponse])
@catalog_router.get("/categories/", response_model=List[CategoryResponse])
def read_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Category)
        .filter(Category.user_id == current_user.id)
        .order_by(Category.name.asc())
        .all()
    )


@router.put("/{category_id}", response_model=CategoryResponse)
@catalog_router.put("/categories/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: int,
    category: CategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_category = (
        db.query(Category)
        .filter(Category.id == category_id, Category.user_id == current_user.id)
        .first()
    )
    if not db_category:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    update_data = category.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_category, key, value)

    db.commit()
    db.refresh(db_category)
    return db_category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
@catalog_router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_category = (
        db.query(Category)
        .filter(Category.id == category_id, Category.user_id == current_user.id)
        .first()
    )
    if not db_category:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    linked_products = (
        db.query(Product)
        .filter(Product.category_id == category_id, Product.user_id == current_user.id)
        .count()
    )
    if linked_products:
        raise HTTPException(
            status_code=409,
            detail=f"Esta categoria está vinculada a {linked_products} produto(s).",
        )

    db.delete(db_category)
    db.commit()
    return None
