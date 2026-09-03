-- ============================================================================
--  019 — assinatura digital de evolucoes (vertical CLINICA)
--
--  Adiciona `assinatura_hash` em `evolucoes`: um SHA-256 de
--  (id | texto | assinado_por_id | assinado_em) calculado no ato da assinatura.
--  Permite verificar depois se o conteudo assinado foi alterado (integridade).
--
--  Risco: baixo (ADD COLUMN). Idempotente (checa information_schema). Pre-req: 012.
--
--  Desfazer:
--    ALTER TABLE evolucoes DROP COLUMN assinatura_hash;
-- ============================================================================

SET @exist := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = DATABASE()
     AND TABLE_NAME = 'evolucoes'
     AND COLUMN_NAME = 'assinatura_hash'
);
SET @sql := IF(@exist = 0,
  'ALTER TABLE evolucoes ADD COLUMN assinatura_hash VARCHAR(64) DEFAULT NULL',
  'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- conferencia
SELECT COLUMN_NAME FROM information_schema.COLUMNS
 WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'evolucoes'
   AND COLUMN_NAME = 'assinatura_hash';
