-- ============================================================
-- MIGRAÇÃO COMPLETA: feature_flags + reseller_feature_flags
-- Execute este script no MySQL Workbench ou similar
-- ============================================================

-- 1. Desativa o safe update mode temporariamente
SET SQL_SAFE_UPDATES = 0;

-- 2. Adiciona coluna feature_flags (se ainda não existir)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS feature_flags JSON DEFAULT NULL;

-- 3. Adiciona coluna reseller_feature_flags (se ainda não existir)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS reseller_feature_flags JSON DEFAULT NULL;

-- 4. Popula feature_flags para usuários comuns (role != 'super_admin') onde ainda está NULL
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
WHERE feature_flags IS NULL
  AND role != 'super_admin';

-- 5. Popula feature_flags para super_admin (admin = TRUE)
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

-- 6. Popula reseller_feature_flags para todos onde ainda está NULL
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

-- 7. Restaura o safe update mode
SET SQL_SAFE_UPDATES = 1;

-- 8. Verifica o resultado
SELECT id, email, role,
       feature_flags,
       reseller_feature_flags
FROM users;

