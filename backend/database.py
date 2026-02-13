# backend/database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

# Carrega a URL do banco de dados do arquivo .env
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./monitor_dns.db")

# Cria um dicionário de argumentos de conexão vazio.
engine_args = {}

# Lógica para definir argumentos baseados no tipo de banco
if DATABASE_URL.startswith("sqlite"):
    # Configurações específicas para SQLite (Desenvolvimento local)
    engine_args["connect_args"] = {"check_same_thread": False}
else:
    # --- CONFIGURAÇÕES CRUCIAIS PARA MYSQL (Produção) ---
    # pool_recycle: Recria a conexão a cada 1 hora (3600s) para evitar o timeout padrão do MySQL (8h)
    engine_args["pool_recycle"] = 3600
    # pool_pre_ping: Testa a conexão com um "SELECT 1" antes de usar. 
    # Se a conexão caiu, ele reconecta automaticamente sem dar erro na aplicação.
    engine_args["pool_pre_ping"] = True
    # pool_size: Define o número de conexões mantidas abertas (opcional, padrão é 5)
    engine_args["pool_size"] = 10
    # max_overflow: Quantas conexões extras podem ser criadas se o pool estiver cheio
    engine_args["max_overflow"] = 20

# Passa os argumentos para o create_engine usando o operador **
engine = create_engine(DATABASE_URL, **engine_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()