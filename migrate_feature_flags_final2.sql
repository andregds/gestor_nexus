-- ============================================================
-- MIGRAÇÃO: Adicionar feature_flags e reseller_feature_flags
-- Execute este script no MySQL Workbench ou cliente MySQL
-- ============================================================

-- Passo 1: Adicionar colunas (se ainda não existirem)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS feature_flags JSON DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS reseller_feature_flags JSON DEFAULT NULL;

-- Passo 2: Desativar safe update mode temporariamente
SET SQL_SAFE_UPDATES = 0;

-- Passo 3: Popular feature_flags para super_admin (acesso total incluindo admin)
UPDATE users
SET feature_flags = JSON_OBJECT(
    'dashboard', TRUE,
    'clients',   TRUE,
    'products',  TRUE,
    'whatsapp',  TRUE,
    'telegram',  TRUE,
    'settings',  TRUE,
    'resell',    TRUE,
    'admin',     TRUE
)
WHERE role = 'super_admin';

-- Passo 4: Popular feature_flags para todos os demais usuários com NULL
UPDATE users
SET feature_flags = JSON_OBJECT(
    'dashboard', TRUE,
    'clients',   TRUE,
    'products',  TRUE,
    'whatsapp',  TRUE,
    'telegram',  TRUE,
    'settings',  TRUE,
    'resell',    TRUE,
    'admin',     FALSE
)
WHERE feature_flags IS NULL;

-- Passo 5: Popular reseller_feature_flags para todos com NULL
UPDATE users
SET reseller_feature_flags = JSON_OBJECT(
    'dashboard', TRUE,
    'clients',   TRUE,
    'products',  TRUE,
    'whatsapp',  TRUE,
    'telegram',  TRUE,
    'settings',  TRUE,
    'resell',    TRUE,
    'admin',     FALSE
)
WHERE reseller_feature_flags IS NULL;

-- Passo 6: Reativar safe update mode
SET SQL_SAFE_UPDATES = 1;

-- Passo 7: Verificar resultado
SELECT id, email, role,
    JSON_EXTRACT(feature_flags, '$.admin') AS flag_admin,
    (feature_flags IS NOT NULL) AS has_flags,
    (reseller_feature_flags IS NOT NULL) AS has_reseller_flags
FROM users;

