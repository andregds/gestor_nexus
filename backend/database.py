import os
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


def get_runtime_env(key: str, default=None):
    value = os.getenv(key)
    if value not in (None, ""):
        return value

    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as registry_key:
                registry_value, _ = winreg.QueryValueEx(registry_key, key)
                if registry_value not in (None, ""):
                    return registry_value
        except FileNotFoundError:
            pass
        except OSError:
            pass

    return default


def _build_database_url():
    database_url = get_runtime_env("DATABASE_URL")
    if database_url:
        return database_url

    driver = get_runtime_env("DB_DRIVER", "mysql+pymysql")
    host = get_runtime_env("DB_HOST")
    port = get_runtime_env("DB_PORT", "3306")
    name = get_runtime_env("DB_NAME")
    user = get_runtime_env("DB_USER")
    password = get_runtime_env("DB_PASSWORD")

    if host and name and user and password is not None:
        return (
            f"{driver}://{quote_plus(user)}:{quote_plus(password)}"
            f"@{host}:{port}/{name}"
        )

    raise RuntimeError(
        "DATABASE_URL nao configurada. Defina DATABASE_URL ou DB_DRIVER, DB_HOST, "
        "DB_PORT, DB_NAME, DB_USER e DB_PASSWORD nas variaveis de ambiente do sistema."
    )


DATABASE_URL = _build_database_url()

engine_kwargs = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
