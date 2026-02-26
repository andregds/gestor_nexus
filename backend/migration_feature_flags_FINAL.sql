-- =====================================================
-- MIGRAÇÃO FINAL: feature_flags e reseller_feature_flags
-- Execute este arquivo no MySQL Workbench ou via mysql CLI
-- =====================================================

-- Desabilitar safe update mode para permitir UPDATE sem KEY no WHERE
SET SQL_SAFE_UPDATES = 0;

-- 1. Adicionar colunas (IF NOT EXISTS evita erros se já existirem)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS feature_flags JSON DEFAULT NULL;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS reseller_feature_flags JSON DEFAULT NULL;

-- 2. Atualizar super_admin com acesso total (admin=true)
UPDATE users
SET
    feature_flags = JSON_OBJECT(
        'dashboard', TRUE,
        'clients', TRUE,
        'products', TRUE,
        'whatsapp', TRUE,
        'telegram', TRUE,
        'settings', TRUE,
        'resell', TRUE,
        'admin', TRUE
    ),
    reseller_feature_flags = JSON_OBJECT(
        'dashboard', TRUE,
        'clients', TRUE,
        'products', TRUE,
        'whatsapp', TRUE,
        'telegram', TRUE,
        'settings', TRUE,
        'resell', TRUE,
        'admin', FALSE
    )
WHERE role = 'super_admin';

-- 3. Atualizar demais usuários (admin=false)
UPDATE users
SET
    feature_flags = JSON_OBJECT(
        'dashboard', TRUE,
        'clients', TRUE,
        'products', TRUE,
        'whatsapp', TRUE,
        'telegram', TRUE,
        'settings', TRUE,
        'resell', TRUE,
        'admin', FALSE
    ),
    reseller_feature_flags = JSON_OBJECT(
        'dashboard', TRUE,
        'clients', TRUE,
        'products', TRUE,
        'whatsapp', TRUE,
        'telegram', TRUE,
        'settings', TRUE,
        'resell', TRUE,
        'admin', FALSE
    )
WHERE (role != 'super_admin' OR role IS NULL)
  AND (feature_flags IS NULL OR reseller_feature_flags IS NULL);

-- 4. Reativar safe update mode
SET SQL_SAFE_UPDATES = 1;

-- 5. Verificar resultado
SELECT id, email, role,
       JSON_EXTRACT(feature_flags, '$.admin') AS flag_admin,
       JSON_EXTRACT(feature_flags, '$.dashboard') AS flag_dashboard
FROM users
LIMIT 20;

