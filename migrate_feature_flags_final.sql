-- ============================================================
-- MIGRAÇÃO: Adicionar colunas feature_flags e reseller_feature_flags
-- à tabela users no MySQL
-- Execute este script no seu banco de dados MySQL
-- ============================================================

-- 1. Adicionar coluna feature_flags (JSON) com valor padrão
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS feature_flags JSON NULL;

-- 2. Adicionar coluna reseller_feature_flags (JSON) com valor padrão
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS reseller_feature_flags JSON NULL;

-- 3. Preencher os registros existentes com os valores padrão
--    (todos habilitados para não quebrar nenhum usuário existente)
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

-- 4. Para o super_admin, habilitar também o admin no feature_flags
UPDATE users
SET feature_flags = JSON_SET(feature_flags, '$.admin', TRUE)
WHERE role = 'super_admin';

-- 5. Verificar resultado
SELECT id, name, email, role, feature_flags, reseller_feature_flags
FROM users;

