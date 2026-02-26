-- ============================================================
-- MIGRAÇÃO: Adiciona colunas feature_flags e reseller_feature_flags
-- na tabela users (MySQL)
-- Execute este script no seu banco de dados MySQL.
-- ============================================================

-- 1. Adiciona coluna feature_flags (JSON) se não existir
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS feature_flags JSON DEFAULT NULL COMMENT 'Flags de funcionalidade por usuário';

-- 2. Adiciona coluna reseller_feature_flags (JSON) se não existir
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS reseller_feature_flags JSON DEFAULT NULL COMMENT 'Flags de funcionalidade padrão para filhos do revendedor';

-- 3. Preenche os registros que estão com NULL com o valor padrão
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
WHERE feature_flags IS NULL;

-- 4. Garante que super_admin sempre tenha admin = TRUE
UPDATE users
SET feature_flags = JSON_SET(
    COALESCE(feature_flags, '{}'),
    '$.admin', CAST(TRUE AS JSON)
)
WHERE role = 'super_admin';

-- 5. Preenche reseller_feature_flags onde estiver NULL
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
WHERE reseller_feature_flags IS NULL;

-- ============================================================
-- VERIFICAÇÃO: execute para confirmar que as colunas existem
-- e os dados foram preenchidos corretamente.
-- ============================================================
-- SELECT id, email, role, feature_flags, reseller_feature_flags FROM users;


