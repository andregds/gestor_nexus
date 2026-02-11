# Usa uma imagem leve do Python
FROM python:3.10-slim

# Define o diretório de trabalho
WORKDIR /app

# Instala dependências do sistema necessárias (para compilar algumas libs se necessário)
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# Copia o arquivo de requisitos
COPY requirements.txt .

# Instala as dependências do Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o código do backend
COPY . .

# Expõe a porta 8000
EXPOSE 8000

# Comando para rodar a aplicação
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]