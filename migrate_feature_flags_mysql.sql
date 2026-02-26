-- ============================================================
-- MIGRAÇÃO: Adicionar colunas feature_flags e reseller_feature_flags
-- à tabela users no MySQL
--
-- COMPATÍVEL com MySQL 5.7+ e MySQL 8.0+
-- Execute no MySQL Workbench, phpMyAdmin, HeidiSQL ou terminal mysql
-- ============================================================

-- Verificar se a coluna feature_flags já existe antes de adicionar
-- (MySQL 5.7 não suporta ADD COLUMN IF NOT EXISTS)
SET @dbname = DATABASE();

-- Adiciona feature_flags se não existir
SET @col1 = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @dbname
      AND TABLE_NAME   = 'users'
      AND COLUMN_NAME  = 'feature_flags'
);
SET @sql1 = IF(@col1 = 0,
    'ALTER TABLE users ADD COLUMN feature_flags JSON NULL',
    'SELECT "feature_flags já existe" AS info'
);
PREPARE stmt1 FROM @sql1;
EXECUTE stmt1;
DEALLOCATE PREPARE stmt1;

-- Adiciona reseller_feature_flags se não existir
SET @col2 = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @dbname
      AND TABLE_NAME   = 'users'
      AND COLUMN_NAME  = 'reseller_feature_flags'
);
SET @sql2 = IF(@col2 = 0,
    'ALTER TABLE users ADD COLUMN reseller_feature_flags JSON NULL',
    'SELECT "reseller_feature_flags já existe" AS info'
);
PREPARE stmt2 FROM @sql2;
EXECUTE stmt2;
DEALLOCATE PREPARE stmt2;

-- ============================================================
-- Preenche os valores padrão nos registros existentes que
-- ainda não possuem as flags configuradas
-- ============================================================

-- feature_flags: tudo habilitado, exceto admin (que só super_admin tem)
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

-- reseller_feature_flags: template padrão para revendedores
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

-- Para super_admin, habilita o flag admin = true
UPDATE users
SET feature_flags = JSON_SET(feature_flags, '$.admin', TRUE)
WHERE role = 'super_admin';

-- ============================================================
-- Verificação final
-- ============================================================
SELECT id, name, email, role,
       feature_flags,
       reseller_feature_flags
FROM users
ORDER BY id;

