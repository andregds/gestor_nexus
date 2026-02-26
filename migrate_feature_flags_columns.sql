-- ============================================================
-- Migração: Adiciona colunas feature_flags e reseller_feature_flags
-- na tabela users (caso ainda não existam)
-- Execute este script diretamente no MySQL
-- ============================================================

-- 1. Adiciona feature_flags (visibilidade de menus para cada usuário)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS feature_flags JSON DEFAULT NULL COMMENT 'Flags de visibilidade de menus por usuário';

-- 2. Adiciona reseller_feature_flags (padrão herdado pelos filhos de um revendedor)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS reseller_feature_flags JSON DEFAULT NULL COMMENT 'Flags padrão aplicadas aos filhos de revendedor';

-- 3. Preenche com valor padrão (tudo habilitado) para registros existentes que estejam NULL
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

-- 4. Para o super_admin, habilita também a flag 'admin'
UPDATE users
SET feature_flags = JSON_SET(feature_flags, '$.admin', TRUE)
WHERE role = 'super_admin';

-- 5. Confirma o resultado
SELECT id, name, email, role,
       feature_flags,
       reseller_feature_flags
FROM users;

