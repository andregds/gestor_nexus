-- ============================================================
-- CORREÇÃO: Garantir que feature_flags e reseller_feature_flags
-- tenham TODAS as chaves necessárias (incluindo 'admin')
-- Execute este script no MySQL Workbench ou cliente MySQL
-- ============================================================

SET SQL_SAFE_UPDATES = 0;

-- -------------------------------------------------------
-- PASSO 1: Garantir que as colunas existem
-- -------------------------------------------------------
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS feature_flags JSON DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS reseller_feature_flags JSON DEFAULT NULL;

-- -------------------------------------------------------
-- PASSO 2: FORÇAR atualização do super_admin
-- Garante acesso TOTAL (admin=true) para super_admin
-- -------------------------------------------------------
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

-- -------------------------------------------------------
-- PASSO 3: FORÇAR atualização dos demais usuários
-- (não é super_admin) - admin=false para todos os outros
-- -------------------------------------------------------
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
WHERE role != 'super_admin';

-- -------------------------------------------------------
-- PASSO 4: FORÇAR atualização do reseller_feature_flags
-- para super_admin (acesso total)
-- -------------------------------------------------------
UPDATE users
SET reseller_feature_flags = JSON_OBJECT(
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

-- -------------------------------------------------------
-- PASSO 5: FORÇAR atualização do reseller_feature_flags
-- para demais usuários
-- -------------------------------------------------------
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
WHERE role != 'super_admin';

SET SQL_SAFE_UPDATES = 1;

-- -------------------------------------------------------
-- VERIFICAÇÃO FINAL: Confira os resultados
-- -------------------------------------------------------
SELECT
    id,
    email,
    role,
    JSON_EXTRACT(feature_flags, '$.admin')    AS flag_admin,
    JSON_EXTRACT(feature_flags, '$.dashboard') AS flag_dashboard,
    JSON_EXTRACT(feature_flags, '$.clients')  AS flag_clients,
    feature_flags,
    reseller_feature_flags
FROM users;

