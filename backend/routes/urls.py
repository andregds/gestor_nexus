# backend/routes/urls.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from core.dependencies import get_db, get_current_user
from models import User, MonitoredURL
from schemas.url import URLCreate, URLResponse

router = APIRouter(prefix="/urls", tags=["URLs"])

@router.post("/", response_model=URLResponse, status_code=status.HTTP_201_CREATED)
def create_url(
    url: URLCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Cria a nova URL vinculada ao usuário logado
    db_url = MonitoredURL(**url.dict(), user_id=current_user.id)
    db.add(db_url)
    db.commit()
    db.refresh(db_url)
    return db_url

@router.get("/", response_model=List[URLResponse])
def read_urls(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Retorna apenas as URLs do usuário logado
    urls = db.query(MonitoredURL).filter(MonitoredURL.user_id == current_user.id).offset(skip).limit(limit).all()
    return urls

# --- ADICIONE ESTA ROTA DE DELETE ABAIXO ---
@router.delete("/{url_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_url(
    url_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Deleta uma URL monitorada."""
    # Busca a URL garantindo que ela pertence ao usuário logado
    url_to_delete = db.query(MonitoredURL).filter(
        MonitoredURL.id == url_id,
        MonitoredURL.user_id == current_user.id
    ).first()

    if url_to_delete is None:
        raise HTTPException(status_code=404, detail="URL não encontrada ou você não tem permissão.")

    db.delete(url_to_delete)
    db.commit()
    return None