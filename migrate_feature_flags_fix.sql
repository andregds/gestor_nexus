-- =============================================================================
-- MIGRAÇÃO: Corrige colunas NULL em feature_flags e reseller_feature_flags
-- Banco de dados: MySQL
-- Execute no banco: monitor_dns (ou o nome do seu banco)
-- =============================================================================

-- 1. Garante que a coluna feature_flags existe com tipo JSON
ALTER TABLE `users`
  MODIFY COLUMN `feature_flags` JSON NULL;

-- 2. Garante que a coluna reseller_feature_flags existe com tipo JSON
ALTER TABLE `users`
  MODIFY COLUMN `reseller_feature_flags` JSON NULL;

-- 3. Atualiza TODOS os usuários com feature_flags NULL para o valor padrão
UPDATE `users`
SET `feature_flags` = JSON_OBJECT(
    'dashboard', TRUE,
    'clients',   TRUE,
    'products',  TRUE,
    'whatsapp',  TRUE,
    'telegram',  TRUE,
    'settings',  TRUE,
    'resell',    TRUE,
    'admin',     FALSE
)
WHERE `feature_flags` IS NULL;

-- 4. Para o super_admin, habilita também o 'admin'
UPDATE `users`
SET `feature_flags` = JSON_OBJECT(
    'dashboard', TRUE,
    'clients',   TRUE,
    'products',  TRUE,
    'whatsapp',  TRUE,
    'telegram',  TRUE,
    'settings',  TRUE,
    'resell',    TRUE,
    'admin',     TRUE
)
WHERE `role` = 'super_admin';

-- 5. Atualiza reseller_feature_flags NULL para o valor padrão
UPDATE `users`
SET `reseller_feature_flags` = JSON_OBJECT(
    'dashboard', TRUE,
    'clients',   TRUE,
    'products',  TRUE,
    'whatsapp',  TRUE,
    'telegram',  TRUE,
    'settings',  TRUE,
    'resell',    TRUE,
    'admin',     FALSE
)
WHERE `reseller_feature_flags` IS NULL;

-- 6. Garante que a coluna permissions existe e não está NULL
ALTER TABLE `users`
  MODIFY COLUMN `permissions` JSON NULL;

UPDATE `users`
SET `permissions` = JSON_OBJECT(
    'can_view_dashboard',   TRUE,
    'can_view_clients',     TRUE,
    'can_view_integrations',TRUE,
    'can_view_settings',    TRUE
)
WHERE `permissions` IS NULL;

-- 7. Verifica o resultado
SELECT id, name, email, role,
       feature_flags,
       reseller_feature_flags
FROM `users`;

