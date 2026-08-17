-- ============================================================================
--  011 — ilustracoes.imagem_bytes: para de depender de disco efemero
--
--  Contexto: a ilustracao gerada por IA era salva em
--  backend/storage/ilustracoes/{id}.png e servida via FileResponse. O servico
--  web do Railway roda em disco EFEMERO, sem volume persistente montado
--  (mesmo problema documentado para o dead-letter do tokenmeter em
--  docs/dashcentral.md). A cada redeploy o arquivo sumia enquanto a linha em
--  `ilustracoes` continuava com status='PRONTA' e imagem_path preenchido -
--  GET /ilustracoes/{id}/imagem devolvia 404 pra ilustracoes que o sistema
--  jurava estarem prontas.
--
--  Correcao: os bytes passam a morar NA PROPRIA LINHA (imagem_bytes,
--  MEDIUMBLOB - ate 16MB, um PNG de ~150-400KB sobra folgado). A coluna
--  imagem_path FICA (nao dropamos - expand/migrate/contract, ver
--  docs/ARQUITETURA-CONTEUDOS.md secao 4), so deixa de ser escrita por
--  codigo novo. Linhas antigas com imagem_path preenchido e imagem_bytes
--  NULL apontam pra um arquivo que ja nao existe mais - irrecuperavel, o
--  proprio 404 que ja acontecia hoje continua acontecendo pra elas.
--
--  Risco de aplicar: baixo. So ADD COLUMN, nenhum SELECT/INSERT existente
--  muda de forma. A partir deste deploy, imagem_path PARA de ser escrito -
--  codigo novo grava so em imagem_bytes (ver app/api/routes/ilustracoes.py).
--  Rodar esta migration ANTES do deploy do codigo novo (padrao expand: o
--  schema fica pronto antes de alguem tentar escrever nele).
--
--  Desfazer:
--    ALTER TABLE ilustracoes DROP COLUMN imagem_bytes;
-- ============================================================================

-- Sem "IF NOT EXISTS": o clausulado so existe a partir do MySQL 8.0.29 e deu
-- erro de sintaxe testando local (8.0.46) - nao vale a pena depender disso.
-- Rodar 1x; rodar de novo por engano da erro de coluna duplicada (seguro,
-- so nao reaplica).
ALTER TABLE ilustracoes
  ADD COLUMN imagem_bytes MEDIUMBLOB NULL AFTER imagem_path;

-- conferencia — esperado: imagem_bytes listada, tipo mediumblob, nullable
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
  FROM INFORMATION_SCHEMA.COLUMNS
 WHERE TABLE_NAME = 'ilustracoes'
 ORDER BY ORDINAL_POSITION;
