-- ============================================================================
--  026 — fase/condicao no registro de tentativa (grafico ABA padrao-ouro)
--
--  Adiciona `fase` em `registros_tentativa` (Linha de base / Intervencao /
--  Generalizacao / Manutencao). Permite quebrar a curva e desenhar as linhas
--  de mudanca de fase no grafico, convencao ABA.
--
--  Risco: baixo. ADD COLUMN idempotente (checa information_schema).
--  Desfazer: ALTER TABLE registros_tentativa DROP COLUMN fase;
-- ============================================================================

SET @c := (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='registros_tentativa' AND COLUMN_NAME='fase');
SET @s := IF(@c=0,'ALTER TABLE registros_tentativa ADD COLUMN fase VARCHAR(40) DEFAULT NULL','SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SELECT COLUMN_NAME FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='registros_tentativa' AND COLUMN_NAME='fase';
