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
    writer.writerow(["Nome", "Login", "WhatsApp", "Vencimento", "Produto", "Valor", "Status Pagamento", "Notas"])

    for client in clients:
        writer.writerow([
            client.name,
            client.login,
            client.whatsapp,
            client.expiration_date.strftime("%d/%m/%Y") if client.expiration_date else "",
            client.server_name or "",
            client.m3u8_url or "",
            client.payment_status or "",
            client.notes or "",
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
            "product_id": c.product_id,
            "payment_status": c.payment_status,
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

    # Remove colunas "Unnamed" (colunas vazias geradas pelo Excel/Pandas)
    df = df.loc[:, ~df.columns.astype(str).str.contains('^Unnamed', case=False, na=False)]
    print(f"Colunas após limpeza: {list(df.columns)}")

    # Remove linhas completamente vazias
    df = df.dropna(how='all')

    # 2. Identificar Colunas (Mapeamento Inteligente)
    col_name   = find_column(df, ['nome', 'cliente', 'name', 'nome completo', 'titular', 'nome do cliente'])
    col_login  = find_column(df, ['login', 'usuario', 'user', 'username', 'email', 'usuario/login'])
    col_phone  = find_column(df, ['whatsapp', 'celular', 'telefone', 'tel', 'cel', 'zap', 'contato', 'mobile', 'fone', 'numero', 'número'])
    col_date   = find_column(df, ['vencimento', 'data', 'validade', 'vence', 'expiration', 'expire', 'data vencimento', 'data de vencimento', 'dt_vencimento', 'dt vencimento'])
    col_notes  = find_column(df, ['obs', 'observacao', 'observação', 'notas', 'observações', 'info', 'nota'])
    col_server = find_column(df, ['servidor', 'server', 'plano', 'pacote', 'servico', 'serviço'])

    print(f"Colunas mapeadas -> nome={col_name}, login={col_login}, phone={col_phone}, date={col_date}")

    # --- LÓGICA DE FALLBACK CRUZADO ---
    # Se achou Login mas NÃO achou Nome, usa o Login como Nome
    if not col_name and col_login:
        col_name = col_login
        print(f"Fallback: usando coluna '{col_login}' como Nome.")

    # Se achou Nome mas NÃO achou Login, usa o Nome como Login
    if not col_login and col_name:
        col_login = col_name
        print(f"Fallback: usando coluna '{col_name}' como Login.")

    # Se ainda não encontrou nome/login, tenta usar a primeira coluna string disponível
    if not col_name:
        for c in df.columns:
            if df[c].dtype == object:
                col_name = c
                col_login = c
                print(f"Fallback: usando primeira coluna string '{c}' como Nome/Login.")
                break

    # Se ainda não encontrou data, tenta coluna que tenha padrão de data
    if not col_date:
        for c in df.columns:
            sample = df[c].dropna().head(5).astype(str)
            if sample.str.contains(r'\d{2}[/\-\.]\d{2}[/\-\.]\d{2,4}', regex=True).any():
                col_date = c
                print(f"Fallback de data por padrão: usando coluna '{c}'.")

    # Validação mínima
    if not col_name:
        cols_found = list(df.columns)
        return {
            "message": "Erro: Não foi possível identificar a coluna de NOME ou LOGIN no arquivo.",
            "errors": [f"Colunas encontradas: {cols_found}. Use cabeçalhos como: Nome, Login, WhatsApp, Vencimento."]
        }

    if not col_date:
        cols_found = list(df.columns)
        return {
            "message": "Erro: Não foi possível identificar a coluna de VENCIMENTO.",
            "errors": [f"Colunas encontradas: {cols_found}. Use um cabeçalho como: Vencimento, Data, Validade."]
        }

    # 3. Iterar e Salvar
    # Substitui NaN por string vazia para evitar erros de comparação
    df = df.fillna("")

    for index, row in df.iterrows():
        try:
            # --- Extrai valores brutos ---
            name_val  = str(row[col_name]).strip()  if col_name  else ""
            login_val = str(row[col_login]).strip() if col_login else ""
            date_raw  = row[col_date] if col_date else ""
            phone_raw = row[col_phone] if col_phone else ""
            notes     = str(row[col_notes]).strip()  if col_notes  else ""
            server    = str(row[col_server]).strip() if col_server else ""

            # Remove valores que Pandas converte para "nan" como string
            _nan_vals = ("nan", "none", "nat", "<na>", "")
            if name_val.lower()  in _nan_vals: name_val  = ""
            if login_val.lower() in _nan_vals: login_val = ""
            if notes.lower()     in _nan_vals: notes     = ""
            if server.lower()    in _nan_vals: server    = ""

            # Define nome e login com fallback cruzado
            name  = name_val  or login_val
            login = login_val or name_val

            # Se ambos estão vazios, pula a linha
            if not name:
                errors.append(f"Linha {index + 2}: Nome/Login vazio — linha ignorada.")
                continue

            # Gera um login derivado do nome se ainda assim não tiver
            if not login:
                login = name.lower().replace(" ", "_")

            # Verifica se a data está presente
            if not date_raw or str(date_raw).strip() in ("", "nan", "None"):
                errors.append(f"Linha {index + 2}: Data de vencimento vazia para '{name}' — linha ignorada.")
                continue

            # Normalizações
            whatsapp        = normalize_phone(phone_raw)
            expiration_date = normalize_date(date_raw)

            if not expiration_date:
                errors.append(f"Linha {index + 2}: Data inválida '{date_raw}' para '{name}' — linha ignorada.")
                continue

            # Verifica duplicidade (pelo Login)
            existing = db.query(Client).filter(
                Client.owner_id == current_user.id,
                Client.login == login
            ).first()

            if existing:
                # Atualiza dados existentes
                existing.name            = name
                existing.whatsapp        = whatsapp
                existing.expiration_date = expiration_date
                if notes:  existing.notes       = notes
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
            errors.append(f"Linha {index + 2}: Erro inesperado ao processar ({str(e)})")
            print(f"  Exceção na linha {index + 2}: {e}")

    db.commit()

    msg_final = f"Processamento concluído! {imported_count} clientes importados/atualizados."
    if not imported_count and errors:
        msg_final = "Nenhum cliente foi importado. Verifique os erros."

    return {
        "message": msg_final,
        "errors": errors
    }