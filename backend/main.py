# backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from routes import users, urls, whatsapp, clients

# from core.config import settings  <-- REMOVA ESTA LINHA
from core.lifespan import lifespan_manager
from database import Base, engine

# Importa os routers
from routes import auth, users, urls, whatsapp

# Cria as tabelas no banco de dados (se não existirem)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Monitor DNS API",
    description="API para monitoramento de URLs com notificações WhatsApp.",
    version="2.0.0",
    lifespan=lifespan_manager,
)

# Configuração CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclui os routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(urls.router)
app.include_router(whatsapp.router)
app.include_router(clients.router)

@app.get("/", tags=["Geral"])
def root():
    return {
        "app": "Monitor DNS com Notificações WhatsApp",
        "status": "online",
        "version": "2.0.0",
        "docs": "/docs"
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
