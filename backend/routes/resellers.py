# backend/routes/resellers.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

# --- ATUALIZAÇÃO: Importe o schema de criação e a função de hash ---
# Certifique-se de que UserCreate existe em schemas.user e get_password_hash em core.security
from schemas.user import UserResponse, UserCreate
from core.security import get_password_hash
# --- Fim da Atualização ---

from core.dependencies import get_db, get_current_user
from models import User

router = APIRouter(prefix="/resellers", tags=["Revendedores"])

# --- Dependência de Segurança ---
def get_reseller_or_super_admin(current_user: User = Depends(get_current_user)):
    """
    Verifica se o usuário logado é 'reseller' ou 'super_admin'.
    Se não for, bloqueia o acesso.
    """
    if current_user.role not in ["reseller", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado. Apenas revendedores ou administradores podem acessar este recurso."
        )
    return current_user

# --- ROTA NOVA: Criar um novo usuário (com role 'user') ---
@router.post("/create-user", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_new_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_reseller_or_super_admin) # Garante que só admin/revendedor pode criar
):
    """
    (Apenas Revendedores/Super Admin) Cria um novo usuário com a função padrão 'user'.
    Este usuário poderá então ser promovido.
    """
    # Verifica se o email já existe
    db_user = db.query(User).filter(User.email == user_in.email).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este email já está cadastrado no sistema."
        )

    # Gera o hash da senha e cria o usuário
    hashed_password = get_password_hash(user_in.password)
    new_user = User(
        name=user_in.name,
        email=user_in.email,
        hashed_password=hashed_password,
        role="user"  # O usuário é criado como 'user' por padrão
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

# --- Rotas de Revendedores ---

@router.get("/", response_model=List[UserResponse], dependencies=[Depends(get_reseller_or_super_admin)])
def list_all_resellers(db: Session = Depends(get_db)):
    """
    (Apenas Revendedores/Super Admin) Retorna uma lista de todos os usuários que são revendedores.
    """
    resellers = db.query(User).filter(User.role == 'reseller').all()
    return resellers

@router.get("/promotable", response_model=List[UserResponse], dependencies=[Depends(get_reseller_or_super_admin)])
def list_promotable_users(db: Session = Depends(get_db)):
    """
    (Apenas Revendedores/Super Admin) Retorna uma lista de usuários comuns que podem ser promovidos.
    """
    return db.query(User).filter(User.role == 'user').all()

@router.put("/promote/{user_id}", response_model=UserResponse, dependencies=[Depends(get_reseller_or_super_admin)])
def promote_user_to_reseller(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    (Apenas Revendedores/Super Admin) Promove um usuário para o nível 'reseller'.
    """
    user_to_promote = db.query(User).filter(User.id == user_id).first()

    if not user_to_promote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário com ID {user_id} não encontrado."
        )

    if user_to_promote.role not in ["user"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Apenas usuários com a função 'user' podem ser promovidos a revendedor."
        )

    # Altera a role e salva no banco
    user_to_promote.role = "reseller"
    db.commit()
    db.refresh(user_to_promote)

    return user_to_promote