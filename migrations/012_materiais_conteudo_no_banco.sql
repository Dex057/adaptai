-- ============================================================================
--  012 — materiais.conteudo_gerado + tipo 'geometria'
--
--  PARTE 1 (bug): o conteudo do material da Biblioteca era gravado SO em
--  storage/materiais/{id}.html|json, com o banco guardando apenas o nome do
--  arquivo (arquivo_path). O servico web do Railway roda em disco EFEMERO —
--  nao ha volume montado (ver railway.json). A cada redeploy o arquivo some
--  enquanto a linha continua com status='disponivel', e
--  GET /materiais/{id}/conteudo passa a devolver 404 para material que a
--  Biblioteca mostra como pronto.
--
--  E o MESMO defeito que a migration 011 corrigiu para `ilustracoes`
--  (imagem_bytes) em 2026-08-17; a correcao nunca tinha chegado em `materiais`.
--
--  Correcao: o conteudo passa a morar na propria linha, em conteudo_gerado
--  (LONGTEXT). arquivo_path FICA (expand/migrate/contract, ver
--  docs/ARQUITETURA-CONTEUDOS.md secao 4) e continua sendo escrito como cache
--  local; a leitura so cai nele quando conteudo_gerado esta vazio, que e o
--  caso das linhas antigas.
--
--  LONGTEXT e nao TEXT: a atividade de geometria (parte 2) carrega um SVG
--  inline por exercicio; os 64KB de TEXT ficariam apertados.
--
--  PARTE 2 (feature): novo tipo 'geometria' no ENUM materiais.tipo —
--  atividade de matematica com as figuras desenhadas pela IA em SVG
--  (app/services/material_service.gerar_atividade_geometria).
--
--  ATENCAO A ORDEM: rodar esta migration ANTES do deploy do codigo novo. Sem
--  a coluna, todo INSERT/UPDATE de material quebra; sem o valor no ENUM, a
--  criacao de material de geometria falha com "Data truncated for column
--  'tipo'".
--
--  Risco de aplicar: baixo. ADD COLUMN nullable + MODIFY de ENUM apenas
--  ACRESCENTANDO um valor (nenhum valor existente e removido ou renomeado,
--  entao nenhuma linha gravada muda de significado).
--
--  Desfazer:
--    ALTER TABLE materiais DROP COLUMN conteudo_gerado;
--    ALTER TABLE materiais MODIFY COLUMN tipo
--      ENUM('VISUAL','MAPA_MENTAL','RESUMO','TEXTO_SIMPLIFICADO',
--           'ROTEIRO_ESTUDO','ATIVIDADES') NOT NULL;
-- ============================================================================

ALTER TABLE materiais
  ADD COLUMN conteudo_gerado LONGTEXT NULL AFTER arquivo_path;

-- ATENCAO AO CASE. O SQLAlchemy declara `SQLEnum(TipoMaterial)` usando os NOMES
-- dos membros do Enum Python (VISUAL, MAPA_MENTAL, ...), nao os valores
-- minusculos — por isso o ENUM do MySQL deve estar em maiusculas. Errar o case
-- aqui NAO da erro: reescreve o ENUM com valores diferentes dos gravados e as
-- linhas existentes viram string vazia.
--
-- PREFIRA `python scripts/aplicar_migration_012.py --aplicar`: ele le o ENUM
-- real em INFORMATION_SCHEMA e so ACRESCENTA o valor novo, preservando ordem e
-- case do que ja existe (e e idempotente). Use o SQL abaixo apenas se ja tiver
-- confirmado o case com a consulta de conferencia no fim do arquivo.
ALTER TABLE materiais
  MODIFY COLUMN tipo ENUM(
    'VISUAL','MAPA_MENTAL','RESUMO','TEXTO_SIMPLIFICADO',
    'ROTEIRO_ESTUDO','ATIVIDADES','GEOMETRIA'
  ) NOT NULL;

-- conferencia — esperado: conteudo_gerado longtext YES, e 'GEOMETRIA' dentro
-- do COLUMN_TYPE de `tipo`.
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
  FROM INFORMATION_SCHEMA.COLUMNS
 WHERE TABLE_NAME = 'materiais'
   AND COLUMN_NAME IN ('conteudo_gerado', 'tipo');
