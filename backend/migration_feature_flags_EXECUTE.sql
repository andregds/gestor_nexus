-- =====================================================
-- MIGRAÇÃO: Adicionar feature_flags e reseller_feature_flags
-- Execute este arquivo no MySQL Workbench ou via mysql CLI
-- =====================================================

-- 1. Adicionar colunas (IF NOT EXISTS evita erros se já existirem)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS feature_flags JSON DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS reseller_feature_flags JSON DEFAULT NULL;

-- 2. Atualizar super_admin com acesso total (incluindo admin=true)
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
WHERE id IN (SELECT id FROM (SELECT id FROM users WHERE role = 'super_admin') AS tmp);

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
WHERE id IN (SELECT id FROM (SELECT id FROM users WHERE role != 'super_admin' OR role IS NULL) AS tmp);

-- 4. Verificar resultado
SELECT id, email, role, feature_flags FROM users LIMIT 20;

