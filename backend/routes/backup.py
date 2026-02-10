# backend/routes/backup.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime
import csv
import io
import json
import pandas as pd  # Importante para ler Excel e CSV de forma robusta

# --- IMPORTS LOCAIS ---
from core.dependencies import get_db, get_current_user
from models import User, Client

router = APIRouter(prefix="/backup", tags=["Backup e Importação"])


# --- FUNÇÕES AUXILIARES ---

def normalize_phone(phone) -> str:
    """Remove caracteres não numéricos e garante o formato 55 + DDD + Numero"""
    if not phone or pd.isna(phone):
        return ""

    # Converte para string e remove tudo que não é dígito
    nums = "".join(filter(str.isdigit, str(phone)))

    if not nums:
        return ""

    # Se tiver 10 ou 11 dígitos (ex: 11999998888), adiciona o 55
    if len(nums) in [10, 11]:
        return f"55{nums}"

    return nums


def normalize_date(date_val):
    """Tenta converter diversos formatos de data para objeto date"""
    if not date_val or pd.isna(date_val):
        return None

    # Se o Pandas já leu como Timestamp (comum em Excel)
    if isinstance(date_val, (pd.Timestamp, datetime)):
        return date_val.date()

    date_str = str(date_val).strip()

    # Lista de formatos aceitos (Brasileiro e Internacional)
    formats = [
        "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d",
        "%d/%m/%y", "%Y/%m/%d", "%d.%m.%Y"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def find_column(df, keywords):
    """
    Procura no DataFrame uma coluna que contenha uma das palavras-chave.
    Retorna o nome da coluna encontrada ou None.
    """
    # Cria um mapa: { "nome_coluna_lower_strip": "Nome Original" }
    columns_map = {str(c).lower().strip(): c for c in df.columns}
    columns_lower = list(columns_map.keys())

    for keyword in keywords:
        keyword = keyword.lower()

        # 1. Tentativa de correspondência exata
        if keyword in columns_lower:
            return columns_map[keyword]

        # 2. Tentativa de correspondência parcial (contém)
        # Ex: "Login do Cliente" contém "login"
        for col_name_lower in columns_lower:
            if keyword in col_name_lower:
                return columns_map[col_name_lower]

    return None


# --- ROTAS DE EXPORTAÇÃO (BACKUP) ---

@router.get("/clients/export")
def export_clients_csv(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Gera um CSV com todos os clientes do usuário"""
    clients = db.query(Client).filter(Client.owner_id == current_user.id).all()

    stream = io.StringIO()
    writer = csv.writer(stream)

    # Cabeçalho
    writer.writerow(["Nome", "Login", "WhatsApp", "Vencimento", "Servidor", "Notas", "M3U8"])

    for client in clients:
        writer.writerow([
            client.name,
            client.login,
            client.whatsapp,
            client.expiration_date.strftime("%d/%m/%Y") if client.expiration_date else "",
            client.server_name or "",
            client.notes or "",
            client.m3u8_url or ""
        ])

    stream.seek(0)

    response = StreamingResponse(iter([stream.getvalue()]), media_type="text/csv")
    response.headers[
        "Content-Disposition"] = f"attachment; filename=clientes_backup_{datetime.now().strftime('%Y%m%d')}.csv"
    return response


@router.get("/full/export")
def export_full_backup(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Gera um JSON completo com Configurações + Clientes"""
    clients = db.query(Client).filter(Client.owner_id == current_user.id).all()

    backup_data = {
        "user_settings": {
            "name": current_user.name,
            "email": current_user.email,
            "whatsapp_instance": current_user.whatsapp_instance,
            "notification_time": current_user.notification_time,
            "notifications_enabled": current_user.notifications_enabled
        },
        "clients": []
    }

    for c in clients:
        backup_data["clients"].append({
            "name": c.name,
            "login": c.login,
            "whatsapp": c.whatsapp,
            "expiration_date": c.expiration_date.strftime("%Y-%m-%d") if c.expiration_date else None,
            "server_name": c.server_name,
            "notes": c.notes,
            "m3u8_url": c.m3u8_url,
            "reminder_days_before": c.reminder_days_before
        })

    json_str = json.dumps(backup_data, indent=4, ensure_ascii=False)

    response = StreamingResponse(iter([json_str]), media_type="application/json")
    response.headers[
        "Content-Disposition"] = f"attachment; filename=backup_geral_{datetime.now().strftime('%Y%m%d')}.json"
    return response


# --- ROTA DE IMPORTAÇÃO (PADRONIZADOR) ---

@router.post("/clients/import")
async def import_clients_file(
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Lê CSV, XLS ou XLSX, identifica colunas automaticamente e importa clientes.
    """
    filename = file.filename.lower()
    contents = await file.read()

    df = None
    errors = []
    imported_count = 0

    # 1. Carregar o arquivo para um DataFrame Pandas
    try:
        if filename.endswith('.csv') or filename.endswith('.txt'):
            # Tenta ler CSV com múltiplas estratégias de codificação e separador
            try:
                # Estratégia 1: UTF-8 com detecção automática de separador
                df = pd.read_csv(io.BytesIO(contents), encoding='utf-8', sep=None, engine='python')
            except:
                try:
                    # Estratégia 2: Latin-1 (comum no Brasil/Excel) com detecção automática
                    df = pd.read_csv(io.BytesIO(contents), encoding='latin-1', sep=None, engine='python')
                except:
                    try:
                        # Estratégia 3: UTF-8-SIG (com BOM)
                        df = pd.read_csv(io.BytesIO(contents), encoding='utf-8-sig', sep=None, engine='python')
                    except:
                        # Estratégia 4: Forçar ponto e vírgula com latin-1
                        df = pd.read_csv(io.BytesIO(contents), encoding='latin-1', sep=';')

        elif filename.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            raise HTTPException(status_code=400, detail="Formato não suportado. Use CSV ou Excel.")

    except Exception as e:
        print(f"Erro ao ler CSV/Excel: {e}")  # Log no terminal do servidor
        raise HTTPException(status_code=400,
                            detail=f"Erro ao ler arquivo. Verifique se é um CSV válido. Detalhe: {str(e)}")

    if df is None or df.empty:
        raise HTTPException(status_code=400, detail="O arquivo está vazio ou ilegível.")

    # Debug: Imprime as colunas encontradas no terminal para ajudar a diagnosticar
    print(f"Colunas encontradas no arquivo: {list(df.columns)}")

    # 2. Identificar Colunas (Mapeamento Inteligente)
    col_name = find_column(df, ['nome', 'cliente', 'name', 'nome completo', 'usuario', 'titular'])
    col_login = find_column(df, ['login', 'usuario', 'user', 'username', 'email'])
    col_phone = find_column(df, ['whatsapp', 'celular', 'telefone', 'tel', 'cel', 'zap', 'contato', 'mobile'])
    col_date = find_column(df, ['vencimento', 'data', 'validade', 'vence', 'expiration', 'expire'])
    col_notes = find_column(df, ['obs', 'observacao', 'observação', 'notas', 'observações', 'info'])
    col_server = find_column(df, ['servidor', 'server', 'plano', 'pacote'])

    # --- LÓGICA DE FALLBACK (CORREÇÃO SOLICITADA) ---

    # Se achou Login mas NÃO achou Nome, usa o Login como Nome
    if not col_name and col_login:
        col_name = col_login

    # Se achou Nome mas NÃO achou Login, usa o Nome como Login
    if not col_login and col_name:
        col_login = col_name

    # Validação mínima
    if not col_name:
        return {"message": "Erro: Não foi possível identificar a coluna de NOME ou LOGIN no arquivo.",
                "errors": [f"Colunas identificadas: {list(df.columns)}. Coluna 'Nome' ou 'Login' não encontrada."]}

    if not col_date:
        return {"message": "Erro: Não foi possível identificar a coluna de VENCIMENTO.",
                "errors": [f"Colunas identificadas: {list(df.columns)}. Coluna 'Vencimento' não encontrada."]}

    # 3. Iterar e Salvar
    # Substitui NaN por None/String vazia para evitar erros
    df = df.fillna("")

    for index, row in df.iterrows():
        try:
            # Pega o valor da coluna mapeada
            name_val = str(row[col_name]).strip()

            # Se a coluna usada para nome for a mesma do login (fallback), o nome será o login
            name = name_val

            # Define o Login
            if col_login:
                login = str(row[col_login]).strip()
            else:
                # Se não tem coluna de login, gera um baseado no nome
                login = name.lower().replace(" ", "")

            phone_raw = row[col_phone] if col_phone else ""
            date_raw = row[col_date]
            notes = str(row[col_notes]) if col_notes else ""
            server = str(row[col_server]) if col_server else ""

            if not name or not date_raw:
                continue

            # Normalizações
            whatsapp = normalize_phone(phone_raw)
            expiration_date = normalize_date(date_raw)

            if not expiration_date:
                errors.append(f"Linha {index + 2}: Data inválida ({date_raw}) para o cliente {name}")
                continue

            # Verifica duplicidade (pelo Login)
            existing = db.query(Client).filter(
                Client.owner_id == current_user.id,
                Client.login == login
            ).first()

            if existing:
                # Atualiza dados existentes
                existing.name = name
                existing.whatsapp = whatsapp
                existing.expiration_date = expiration_date
                if notes: existing.notes = notes
                if server: existing.server_name = server
            else:
                # Cria novo cliente
                new_client = Client(
                    owner_id=current_user.id,
                    name=name,
                    login=login,
                    whatsapp=whatsapp,
                    expiration_date=expiration_date,
                    notes=notes,
                    server_name=server,
                    reminder_enabled=True,
                    reminder_days_before="3"
                )
                db.add(new_client)

            imported_count += 1

        except Exception as e:
            errors.append(f"Linha {index + 2}: Erro ao processar ({str(e)})")

    db.commit()

    msg_final = f"Processamento concluído! {imported_count} clientes importados/atualizados."
    if not imported_count and errors:
        msg_final = "Nenhum cliente foi importado. Verifique os erros."

    return {
        "message": msg_final,
        "errors": errors
    }