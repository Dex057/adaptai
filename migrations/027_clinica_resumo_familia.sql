-- ============================================================================
--  027 — resumo p/ familia na evolucao (tradutor clinico->familia por IA)
--  Adiciona `resumo_familia` em `evolucoes`: versao em linguagem simples da nota
--  clinica, gerada pela IA e aprovada pelo profissional, exibida no portal da
--  familia (o texto tecnico permanece so no prontuario).
--  Risco: baixo. ADD COLUMN idempotente. Desfazer: ALTER TABLE evolucoes DROP COLUMN resumo_familia;
-- ============================================================================
SET @c := (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='evolucoes' AND COLUMN_NAME='resumo_familia');
SET @s := IF(@c=0,'ALTER TABLE evolucoes ADD COLUMN resumo_familia TEXT DEFAULT NULL','SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
SELECT COLUMN_NAME FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='evolucoes' AND COLUMN_NAME='resumo_familia';
