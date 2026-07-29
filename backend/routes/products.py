from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.dependencies import get_current_user, get_db
from models import Category, Plan, Product, User
from schemas.product import Product as ProductResponse
from schemas.product import ProductCreate, ProductUpdate

router = APIRouter(prefix="/products", tags=["Produtos"])
catalog_router = APIRouter(prefix="/users/me/catalog", tags=["Catálogo"])


def _get_owned_category(db: Session, category_id: int, user_id: int):
    return (
        db.query(Category)
        .filter(Category.id == category_id, Category.user_id == user_id)
        .first()
    )


def _get_owned_plan(db: Session, plan_id: int, user_id: int):
    return (
        db.query(Plan)
        .filter(Plan.id == plan_id, Plan.user_id == user_id)
        .first()
    )


@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
@catalog_router.post("/products/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    product: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    category = _get_owned_category(db, product.category_id, current_user.id)
    if not category:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    plan = _get_owned_plan(db, product.plan_id, current_user.id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plano não encontrado")

    db_product = Product(**product.dict(), user_id=current_user.id)
    db_product.price = plan.price
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product


@router.get("/", response_model=List[ProductResponse])
@catalog_router.get("/products/", response_model=List[ProductResponse])
def read_products(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Product)
        .filter(Product.user_id == current_user.id)
        .order_by(Product.name.asc())
        .all()
    )


@router.put("/{product_id}", response_model=ProductResponse)
@catalog_router.put("/products/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    product: ProductUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.user_id == current_user.id)
        .first()
    )
    if not db_product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    update_data = product.dict(exclude_unset=True)

    if "category_id" in update_data:
        category = _get_owned_category(db, update_data["category_id"], current_user.id)
        if not category:
            raise HTTPException(status_code=404, detail="Categoria não encontrada")

    target_plan_id = update_data.get("plan_id", db_product.plan_id)
    plan = _get_owned_plan(db, target_plan_id, current_user.id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plano não encontrado")

    for key, value in update_data.items():
        setattr(db_product, key, value)
    db_product.price = plan.price

    db.commit()
    db.refresh(db_product)
    return db_product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
@catalog_router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.user_id == current_user.id)
        .first()
    )
    if not db_product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    db.delete(db_product)
    db.commit()
    return None
