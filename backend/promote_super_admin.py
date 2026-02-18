"""
Uso:
    python promote_super_admin.py <email_do_usuario>

Promove o usuário informado para `super_admin` e garante que o flag de admin
esteja habilitado. Use dentro do venv com as variáveis de conexão já
configuradas.
"""
import sys
from sqlalchemy.exc import SQLAlchemyError
from database import SessionLocal
from models import User


def promote(email: str) -> int:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            print(f"Usuário com email '{email}' não encontrado.")
            return 1

        user.role = "super_admin"

        flags = user.feature_flags or {}
        flags["admin"] = True
        flags["resell"] = True
        user.feature_flags = flags

        db.commit()
        print(f"Usuário '{user.name}' promovido para super_admin com sucesso.")
        return 0
    except SQLAlchemyError as exc:
        db.rollback()
        print(f"Erro ao promover usuário: {exc}")
        return 1
    finally:
        db.close()


def main():
    if len(sys.argv) != 2:
        print("Uso: python promote_super_admin.py <email_do_usuario>")
        sys.exit(1)
    email = sys.argv[1].strip()
    sys.exit(promote(email))


if __name__ == "__main__":
    main()

