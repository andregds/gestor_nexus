# backend/routes/resellers.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel, Field

from schemas.user import UserResponse, UserCreate, BlockUserRequest
from core.security import get_password_hash
from core.dependencies import get_db, get_current_user
from models import User

router = APIRouter(prefix="/resellers", tags=["Revendedores"])


# ... (Schemas PromoteRequest, ResellerUpdate, PasswordResetRequest mantêm-se iguais) ...
class PromoteRequest(BaseModel):
    credits: int


class ResellerUpdate(BaseModel):
    name: str
    email: str
    client_limit: int


class PasswordResetRequest(BaseModel):
    new_password: str = Field(..., min_length=6)


def get_reseller_or_super_admin(current_user: User = Depends(get_current_user)):
    if current_user.role not in ["reseller", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado."
        )
    return current_user


# --- ROTA: Criar um novo usuário (com vínculo de pai/filho) ---
@router.post("/create-user", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_new_user(
        user_in: UserCreate,
        db: Session = Depends(get_db),
        current_admin: User = Depends(get_reseller_or_super_admin)
):
    db_user = db.query(User).filter(User.email == user_in.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Este email já está cadastrado.")

    hashed_password = get_password_hash(user_in.password)

    # AQUI ESTÁ A MUDANÇA: Salvamos o owner_id
    new_user = User(
        name=user_in.name,
        email=user_in.email,
        hashed_password=hashed_password,
        role="user",
        client_limit=0,
        owner_id=current_admin.id  # <--- Vínculo criado
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


# --- Rotas de Leitura (COM FILTRO DE PRIVACIDADE) ---

@router.get("/", response_model=List[UserResponse], dependencies=[Depends(get_reseller_or_super_admin)])
def list_all_resellers(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_reseller_or_super_admin)
):
    """
    Lista revendedores.
    - Super Admin: Vê TODOS os revendedores.
    - Revendedor: Vê apenas os revendedores que ELE criou (sub-revendedores).
    """
    query = db.query(User).filter(User.role == 'reseller')

    if current_user.role != 'super_admin':
        # Filtra apenas os filhos deste usuário
        query = query.filter(User.owner_id == current_user.id)

    return query.all()


@router.get("/promotable", response_model=List[UserResponse], dependencies=[Depends(get_reseller_or_super_admin)])
def list_promotable_users(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_reseller_or_super_admin)
):
    """
    Lista usuários comuns para promoção.
    - Super Admin: Vê TODOS.
    - Revendedor: Vê apenas os usuários que ELE criou.
    """
    query = db.query(User).filter(User.role == 'user')

    if current_user.role != 'super_admin':
        # Filtra apenas os filhos deste usuário
        query = query.filter(User.owner_id == current_user.id)

    return query.all()


# ... (O restante das rotas promote, update, reset-password, toggle-active continuam iguais) ...
# Apenas certifique-se de manter as importações e a lógica de saldo que já corrigimos anteriormente.

@router.put("/promote/{user_id}", response_model=UserResponse)
def promote_user_to_reseller(
        user_id: int,
        promote_data: PromoteRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_reseller_or_super_admin)
):
    admin_user = db.query(User).filter(User.id == current_user.id).first()

    # Adicionar filtro de segurança: Revendedor só pode promover seus próprios usuários
    query = db.query(User).filter(User.id == user_id)
    if current_user.role != 'super_admin':
        query = query.filter(User.owner_id == current_user.id)

    user_to_promote = query.first()

    if not user_to_promote:
        raise HTTPException(status_code=404, detail="Usuário não encontrado ou você não tem permissão.")

    if user_to_promote.role != "user":
        raise HTTPException(status_code=400, detail="Apenas usuários 'user' podem ser promovidos.")

    credits_to_give = promote_data.credits
    if credits_to_give < 0:
        raise HTTPException(status_code=400, detail="O limite não pode ser negativo.")

    if admin_user.role == 'reseller':
        if admin_user.client_limit < credits_to_give:
            raise HTTPException(status_code=400, detail=f"Saldo insuficiente. Você tem {admin_user.client_limit}.")
        admin_user.client_limit -= credits_to_give

    user_to_promote.role = "reseller"
    user_to_promote.client_limit = credits_to_give

    db.commit()
    db.refresh(user_to_promote)
    db.refresh(admin_user)
    return user_to_promote


@router.put("/{user_id}", response_model=UserResponse)
def update_reseller(
        user_id: int,
        update_data: ResellerUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_reseller_or_super_admin)
):
    # Filtro de segurança
    query = db.query(User).filter(User.id == user_id)
    if current_user.role != 'super_admin':
        # Permite editar a si mesmo OU seus filhos
        if user_id != current_user.id:
            query = query.filter(User.owner_id == current_user.id)

    target_user = query.first()

    if not target_user:
        raise HTTPException(status_code=404, detail="Revendedor não encontrado.")

    admin_user = db.query(User).filter(User.id == current_user.id).first()

    if target_user.id == admin_user.id:
        pass  # Auto-edição ignora limite

    old_limit = target_user.client_limit
    new_limit = update_data.client_limit
    diff = new_limit - old_limit

    if diff != 0:
        if admin_user.role != 'super_admin':
            if diff > 0:
                if admin_user.client_limit < diff:
                    raise HTTPException(status_code=400, detail="Saldo insuficiente.")
                admin_user.client_limit -= diff
            else:
                admin_user.client_limit += abs(diff)
        target_user.client_limit = new_limit

    target_user.name = update_data.name
    target_user.email = update_data.email

    db.commit()
    db.refresh(target_user)
    if admin_user.id != target_user.id:
        db.refresh(admin_user)

    return target_user


@router.put("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_reseller_password(
        user_id: int,
        request_body: PasswordResetRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_reseller_or_super_admin)
):
    query = db.query(User).filter(User.id == user_id)
    if current_user.role != 'super_admin':
        query = query.filter(User.owner_id == current_user.id)

    target_user = query.first()

    if not target_user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    target_user.hashed_password = get_password_hash(request_body.new_password)
    db.commit()
    return


@router.put("/{user_id}/toggle-active", response_model=UserResponse)
def toggle_reseller_status(
        user_id: int,
        block_data: BlockUserRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_reseller_or_super_admin)
):
    query = db.query(User).filter(User.id == user_id)
    if current_user.role != 'super_admin':
        query = query.filter(User.owner_id == current_user.id)

    target_user = query.first()

    if not target_user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    if target_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Você não pode bloquear a si mesmo.")

    if target_user.is_active:
        target_user.is_active = False
        target_user.block_reason = block_data.reason if block_data.reason else "Bloqueio administrativo."
    else:
        target_user.is_active = True
        target_user.block_reason = None

    db.commit()
    db.refresh(target_user)
    return target_user