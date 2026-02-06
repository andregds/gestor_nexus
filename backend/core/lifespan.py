# backend/core/lifespan.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from monitor import start_monitoring
import asyncio

@asynccontextmanager
async def lifespan_manager(app: FastAPI):
    print("🚀 Iniciando aplicação...")
    # Não precisamos criar a sessão aqui, o monitor cria a dele
    app.state.monitoring_task = asyncio.create_task(start_monitoring(None))
    try:
        yield
    finally:
        print("🛑 Desligando aplicação...")
        if hasattr(app.state, 'monitoring_task') and app.state.monitoring_task:
            app.state.monitoring_task.cancel()
            try:
                await app.state.monitoring_task
            except asyncio.CancelledError:
                print("Monitoramento de URLs cancelado.")