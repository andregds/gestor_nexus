from fastapi import APIRouter, HTTPException, UploadFile, Form, Depends
from typing import Optional
import os

from core.dependencies import get_current_user

router = APIRouter()

# Novo diretório para imagens anexas
BASE_UPLOAD_DIR = "imagens_anexas"

# Lista simulada para armazenar mensagens
messages = []

# Mensagens padrão para vencimentos
DEFAULT_MESSAGES = [
    {"id": 1001, "type": "vencido", "content": "Prezado cliente, sua fatura está vencida. Regularize o pagamento para evitar interrupções.", "image": None, "is_default": True, "user_id": None, "selected_for_send": True},
    {"id": 1002, "type": "vence_1", "content": "Prezado cliente, sua fatura vence em 1 dia. Regularize o pagamento para evitar interrupções.", "image": None, "is_default": True, "user_id": None, "selected_for_send": True},
    {"id": 1003, "type": "vence_2", "content": "Prezado cliente, sua fatura vence em 2 dias. Regularize o pagamento para evitar interrupções.", "image": None, "is_default": True, "user_id": None, "selected_for_send": True},
    {"id": 1004, "type": "vence_3", "content": "Prezado cliente, sua fatura vence em 3 dias. Regularize o pagamento para evitar interrupções.", "image": None, "is_default": True, "user_id": None, "selected_for_send": True},
    {"id": 1005, "type": "vence_4", "content": "Prezado cliente, sua fatura vence em 4 dias. Regularize o pagamento para evitar interrupções.", "image": None, "is_default": True, "user_id": None, "selected_for_send": True},
]

def ensure_default_messages():
    existing_types = {msg["type"] for msg in messages}
    for default_msg in DEFAULT_MESSAGES:
        if default_msg["type"] not in existing_types:
            messages.append(default_msg.copy())

# Garante que as mensagens padrão estejam sempre presentes
ensure_default_messages()

def normalize_filename(filename):
    import re
    name, ext = os.path.splitext(filename)
    name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    return name + ext

@router.post("/api/messages")
async def create_message(
    type: str = Form(...),
    content: str = Form(...),
    image: Optional[UploadFile] = None,
    selected_for_send: bool = Form(False),
    current_user: dict = Depends(get_current_user)
):
    print(f"Recebido POST /api/messages com type={type}, content={content}, image={image}")
    try:
        user_id = current_user["id"] if isinstance(current_user, dict) else getattr(current_user, "id", "anon")
        user_upload_dir = os.path.join(BASE_UPLOAD_DIR, str(user_id))
        os.makedirs(user_upload_dir, exist_ok=True)
        user_images = [f for f in os.listdir(user_upload_dir) if os.path.isfile(os.path.join(user_upload_dir, f))]
        if image and len(user_images) >= 10:
            raise HTTPException(status_code=400, detail="Limite de 10 imagens anexas atingido para este usuário.")
        image_path = None
        if image:
            if image.content_type not in ["image/jpeg", "image/png"]:
                raise HTTPException(status_code=400, detail="Formato de imagem não suportado.")
            normalized_filename = normalize_filename(image.filename)
            image_path = os.path.join(user_upload_dir, normalized_filename)
            with open(image_path, "wb") as f:
                f.write(await image.read())
        # Se já existe mensagem do mesmo tipo para este usuário, sobrescreve
        for msg in messages:
            if msg["type"] == type and msg.get("user_id") == user_id:
                msg["content"] = content
                msg["selected_for_send"] = selected_for_send
                if image_path:
                    msg["image"] = f"/{user_upload_dir.replace(os.sep, '/')}/{os.path.basename(image_path)}"
                return msg
        # Se não existe, cria nova
        if image_path:
            image_url = f"/{user_upload_dir.replace(os.sep, '/')}/{os.path.basename(image_path)}"
        else:
            image_url = None
        new_message = {
            "id": len(messages) + 1,
            "type": type,
            "content": content,
            "image": image_url,
            "user_id": user_id,
            "is_default": False,
            "selected_for_send": selected_for_send,
        }
        messages.append(new_message)
        print(f"Mensagem criada com sucesso: {new_message}")
        return new_message
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao criar mensagem: {str(e)}")

@router.get("/api/messages")
async def list_messages(current_user: dict = Depends(get_current_user)):
    """Retorna apenas as mensagens padrão e as do usuário autenticado."""
    ensure_default_messages()
    user_id = current_user["id"] if isinstance(current_user, dict) else getattr(current_user, "id", "anon")
    return [msg for msg in messages if msg.get("is_default") or msg.get("user_id") == user_id]

@router.put("/api/messages/{message_id}")
async def update_message(message_id: int, type: str = Form(...), content: str = Form(...), image: Optional[UploadFile] = None, selected_for_send: Optional[bool] = Form(None), current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"] if isinstance(current_user, dict) else getattr(current_user, "id", "anon")
    user_upload_dir = os.path.join(BASE_UPLOAD_DIR, str(user_id))
    os.makedirs(user_upload_dir, exist_ok=True)
    user_images = [f for f in os.listdir(user_upload_dir) if os.path.isfile(os.path.join(user_upload_dir, f))]
    if image and len(user_images) >= 10:
        raise HTTPException(status_code=400, detail="Limite de 10 imagens anexas atingido para este usuário.")
    for msg in messages:
        if msg["id"] == message_id and (msg.get("user_id") == user_id or msg.get("is_default")):
            msg["type"] = type
            msg["content"] = content
            if selected_for_send is not None:
                msg["selected_for_send"] = selected_for_send
            if image:
                if image.content_type not in ["image/jpeg", "image/png"]:
                    raise HTTPException(status_code=400, detail="Formato de imagem não suportado.")
                normalized_filename = normalize_filename(image.filename)
                image_path = os.path.join(user_upload_dir, normalized_filename)
                with open(image_path, "wb") as f:
                    f.write(await image.read())
                msg["image"] = f"/{user_upload_dir.replace(os.sep, '/')}/{os.path.basename(image_path)}"
            return msg
    raise HTTPException(status_code=404, detail="Mensagem não encontrada.")

@router.delete("/api/messages/{message_id}")
async def delete_message(message_id: int, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"] if isinstance(current_user, dict) else getattr(current_user, "id", "anon")
    for i, msg in enumerate(messages):
        if msg["id"] == message_id and (msg.get("user_id") == user_id or msg.get("is_default")):
            del messages[i]
            return {"detail": "Mensagem deletada com sucesso."}
    raise HTTPException(status_code=404, detail="Mensagem não encontrada.")

@router.patch("/api/messages/{message_id}/select")
async def toggle_message_selection(message_id: int, selected_for_send: bool = Form(...), current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"] if isinstance(current_user, dict) else getattr(current_user, "id", "anon")
    for msg in messages:
        if msg["id"] == message_id and (msg.get("user_id") == user_id or msg.get("is_default")):
            msg["selected_for_send"] = selected_for_send
            return msg
    raise HTTPException(status_code=404, detail="Mensagem não encontrada.")
