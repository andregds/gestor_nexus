-- ============================================================
-- Script de Migração MySQL - Nexus Monitor
-- Execute este script para corrigir a estrutura do banco de dados
-- ============================================================

-- Use o banco correto (ajuste o nome se necessário)
-- USE nome_do_banco;

-- ============================================================
-- TABELA: users — adicionar colunas ausentes
-- ============================================================

-- feature_flags: flags de menu/funcionalidade por usuário
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS feature_flags JSON DEFAULT NULL;

-- reseller_feature_flags: flags padrão para filhos de um revendedor
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS reseller_feature_flags JSON DEFAULT NULL;

-- block_reason: motivo do bloqueio (usado pelo super_admin)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS block_reason VARCHAR(255) DEFAULT NULL;

-- owner_id: hierarquia revendedor → usuário filho
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS owner_id INT DEFAULT NULL,
    ADD CONSTRAINT fk_users_owner FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE SET NULL;

-- client_limit: limite de clientes do usuário
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS client_limit INT NOT NULL DEFAULT 0;

-- Configurações de Telegram
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS telegram_token VARCHAR(255) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS telegram_chat_id VARCHAR(100) DEFAULT NULL;

-- notification_channel: canal padrão (whatsapp | telegram)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS notification_channel VARCHAR(50) DEFAULT 'whatsapp';

-- Flags de notificação individuais
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS notifications_enabled TINYINT(1) NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS notify_when_down TINYINT(1) NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS notify_when_up TINYINT(1) NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS notify_when_slow TINYINT(1) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS notification_time VARCHAR(10) DEFAULT '09:00';

-- WhatsApp campos extras
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS whatsapp_instance VARCHAR(100) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS whatsapp_apikey VARCHAR(255) DEFAULT NULL;

-- is_active (caso não exista)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS is_active TINYINT(1) NOT NULL DEFAULT 1;

-- permissions JSON
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS permissions JSON DEFAULT NULL;

-- ============================================================
-- POPULAR feature_flags e reseller_feature_flags com defaults
-- para usuários que já existem no banco (NULL → JSON padrão)
-- ============================================================

-- Desativa temporariamente o Safe Update Mode (MySQL Workbench)
SET SQL_SAFE_UPDATES = 0;

UPDATE users
SET feature_flags = JSON_OBJECT(
    'dashboard', TRUE,
    'clients', TRUE,
    'products', TRUE,
    'whatsapp', TRUE,
    'telegram', TRUE,
    'settings', TRUE,
    'resell', TRUE,
    'admin', FALSE
)
WHERE id > 0 AND (feature_flags IS NULL OR JSON_TYPE(feature_flags) IS NULL OR feature_flags = 'null' OR CAST(feature_flags AS CHAR) = '');

-- Super admin sempre tem 'admin' = TRUE
UPDATE users
SET feature_flags = JSON_SET(
    COALESCE(feature_flags, '{}'),
    '$.admin', CAST(TRUE AS JSON)
)
WHERE id > 0 AND role = 'super_admin';

UPDATE users
SET reseller_feature_flags = JSON_OBJECT(
    'dashboard', TRUE,
    'clients', TRUE,
    'products', TRUE,
    'whatsapp', TRUE,
    'telegram', TRUE,
    'settings', TRUE,
    'resell', TRUE,
    'admin', FALSE
)
WHERE id > 0 AND (reseller_feature_flags IS NULL OR JSON_TYPE(reseller_feature_flags) IS NULL OR reseller_feature_flags = 'null' OR CAST(reseller_feature_flags AS CHAR) = '');

UPDATE users
SET permissions = JSON_OBJECT(
    'can_view_dashboard', TRUE,
    'can_view_clients', TRUE,
    'can_view_integrations', TRUE,
    'can_view_settings', TRUE
)
WHERE id > 0 AND (permissions IS NULL OR JSON_TYPE(permissions) IS NULL OR permissions = 'null' OR CAST(permissions AS CHAR) = '');

-- Reativa o Safe Update Mode
SET SQL_SAFE_UPDATES = 1;

-- ============================================================
-- TABELA: plans — billing_cycle requer comprimento no MySQL
-- ============================================================

-- Altera a coluna billing_cycle para VARCHAR(50) se ainda não tiver tamanho
ALTER TABLE plans
    MODIFY COLUMN billing_cycle VARCHAR(50) NOT NULL;

-- ============================================================
-- TABELAS NOVAS (caso não existam)
-- ============================================================

CREATE TABLE IF NOT EXISTS categories (
    id          INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    description VARCHAR(500) DEFAULT NULL,
    user_id     INT NOT NULL,
    CONSTRAINT fk_categories_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS products (
    id          INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    description VARCHAR(1024) DEFAULT NULL,
    price       FLOAT NOT NULL,
    category_id INT DEFAULT NULL,
    user_id     INT NOT NULL,
    CONSTRAINT fk_products_category FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL,
    CONSTRAINT fk_products_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS plans (
    id            INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(100) NOT NULL UNIQUE,
    description   VARCHAR(500) DEFAULT NULL,
    price         FLOAT NOT NULL,
    billing_cycle VARCHAR(50) NOT NULL,
    user_id       INT NOT NULL,
    CONSTRAINT fk_plans_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS features (
    id          INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    description VARCHAR(500) DEFAULT NULL,
    user_id     INT NOT NULL,
    CONSTRAINT fk_features_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS plan_features (
    plan_id    INT NOT NULL,
    feature_id INT NOT NULL,
    PRIMARY KEY (plan_id, feature_id),
    CONSTRAINT fk_pf_plan    FOREIGN KEY (plan_id)    REFERENCES plans(id)    ON DELETE CASCADE,
    CONSTRAINT fk_pf_feature FOREIGN KEY (feature_id) REFERENCES features(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS messages (
    id           INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    message_type VARCHAR(50) NOT NULL UNIQUE,
    content      VARCHAR(1024) NOT NULL,
    image_path   VARCHAR(255) DEFAULT NULL,
    is_default   TINYINT(1) NOT NULL DEFAULT 0,
    user_id      INT DEFAULT NULL,
    CONSTRAINT fk_messages_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- ============================================================
-- FIM DO SCRIPT
-- ============================================================
SELECT 'Migração concluída com sucesso!' AS resultado;

