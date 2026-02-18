#!/bin/bash
# Script de deploy automatizado para VPS Contabo
# Uso: bash deploy_vps_contabo.sh

set -e

# === CONFIGURAÇÕES ===
REPO_URL="https://github.com/andregds/gestor_nexus.git"
PROJ_DIR="gestor_nexus"
DOCKER_COMPOSE_FILE="docker-compose.yml"
DOMAIN="painel.gestornexus.com.br" # Altere para seu domínio, se desejar
EMAIL_LETSENCRYPT="andregds@msn.com" # Altere para seu e-mail

# === 1. Atualiza o sistema e instala dependências ===
echo "[1/7] Atualizando sistema e instalando Docker, Docker Compose, Git, Nginx, Certbot..."
apt update && apt install -y docker.io docker-compose git nginx certbot python3-certbot-nginx
systemctl enable --now docker
systemctl enable --now nginx

# === 2. Clona ou atualiza o repositório ===
echo "[2/7] Clonando ou atualizando o repositório..."
if [ -d "$PROJ_DIR/.git" ]; then
  cd "$PROJ_DIR"
  git pull
  cd ..
else
  git clone "$REPO_URL"
fi
cd "$PROJ_DIR"

# === 3. Ajusta variáveis de ambiente (opcional) ===
echo "[3/7] Ajuste variáveis de ambiente se necessário (edite .env manualmente se precisar)"

# === 4. Sobe os containers ===
echo "[4/7] Subindo containers Docker..."
docker-compose down || true
docker-compose up -d --build

# === 5. Configura Nginx para proxy reverso ===
echo "[5/7] Configurando Nginx para proxy reverso..."
cat > /etc/nginx/sites-available/gestor_nexus <<EOF
server {
    listen 80;
    server_name $DOMAIN;
    location / {
        proxy_pass http://localhost:8000; # Ajuste a porta se necessário
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
ln -sf /etc/nginx/sites-available/gestor_nexus /etc/nginx/sites-enabled/gestor_nexus
nginx -t && systemctl reload nginx

# === 6. (Opcional) HTTPS com Let's Encrypt ===
echo "[6/7] (Opcional) Instalando HTTPS com Let's Encrypt..."
if [ "$DOMAIN" != "seusite.com" ]; then
  certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m $EMAIL_LETSENCRYPT || true
fi

# === 7. Fim ===
echo "[7/7] Deploy finalizado! Acesse: http://$DOMAIN ou http://$(curl -s ifconfig.me):8000"

