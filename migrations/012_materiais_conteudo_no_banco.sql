-- ============================================================================
--  012 - Biblioteca de Materiais: conteudo no banco, colunas de versao e
--        indices de listagem.
--
--  TRES problemas, todos com sintoma na mesma tela ("Materiais").
--
--  ---------------------------------------------------------------------------
--  (1) materiais.conteudo / materiais.conteudo_versoes - DISCO EFEMERO
--  ---------------------------------------------------------------------------
--  O HTML (ou o JSON do mapa mental) gerado pela IA era gravado so em
--  backend/storage/materiais/{id}.html e a linha guardava apenas o nome do
--  arquivo (arquivo_path). O servico web do Railway roda em disco EFEMERO,
--  sem volume: a cada redeploy o arquivo some e a linha continua com
--  status='disponivel'. Para o professor, o material "nao persistiu" - abre e
--  responde 404 "Conteudo do material nao encontrado no storage".
--
--  Mesma causa raiz da migration 011 (ilustracoes.imagem_bytes), mesma
--  correcao: o conteudo passa a morar NA LINHA.
--
--    conteudo          MEDIUMTEXT  conteudo da versao atual (ate 16MB; um
--                                  material tipico tem 20-60KB)
--    conteudo_versoes  JSON        {"1": "<html...>", "2": "..."} das versoes
--                                  arquivadas por POST /materiais/{id}/regenerar
--
--  arquivo_path FICA (expand/migrate/contract). Codigo novo continua
--  preenchendo o campo como marcador logico, mas ninguem le arquivo por ele:
--  a leitura passa por app/services/material_conteudo.ler(), que tenta o banco
--  e cai para o disco so por causa de linhas antigas.
--
--  Linhas antigas com arquivo_path preenchido e conteudo NULL apontam para um
--  arquivo que ja nao existe - irrecuperaveis. O professor pode regerar pelo
--  botao "Regenerar" (nao consome cota de plano).
--
--  ---------------------------------------------------------------------------
--  (2) materiais.versao / materiais.historico_versoes - COLUNAS SEM MIGRATION
--  ---------------------------------------------------------------------------
--  O versionamento de material entrou no codigo em 08/06/2026 (commit
--  71b18c6) com um script Python avulso (aplicar_migracao_materiais_versao.py)
--  que depois saiu do repositorio - nao ha registro de ter rodado em
--  producao. Se essas colunas NAO existem no MySQL, todo
--  "SELECT materiais.*" falha com
--
--      (1054, "Unknown column 'materiais.versao' in 'field list'")
--
--  e a Biblioteca abre direto em "Nao foi possivel carregar os materiais".
--  Os ADDs abaixo sao condicionais: se as colunas ja existirem, nada acontece.
--
--  ---------------------------------------------------------------------------
--  (3) Indices - "1038 Out of sort memory"
--  ---------------------------------------------------------------------------
--  GET /materiais-adaptados/historico/student/{id} caiu em producao com:
--
--    pymysql.err.OperationalError: (1038, 'Out of sort memory, consider
--    increasing server sort buffer size')
--
--  O SELECT trazia materiais_adaptados_gerados.* (inclusive resultado_json,
--  que com hq_tirinha/album_figurinhas chega a megabytes por causa das imagens
--  em base64) e ordenava por created_at sem indice: filesort de linhas
--  enormes. O codigo ja foi corrigido para nao selecionar o JSON; os indices
--  abaixo eliminam tambem o filesort, que e o que sobra do problema quando o
--  volume por aluno cresce.
--
--  ---------------------------------------------------------------------------
--  COMO RODAR
--  ---------------------------------------------------------------------------
--  Cole o arquivo inteiro no console MySQL do Railway. E IDEMPOTENTE: cada
--  passo checa o INFORMATION_SCHEMA antes de executar, entao rodar duas vezes
--  nao da erro (a segunda vez so imprime "ja existe"). Rodar ANTES do deploy
--  do codigo novo (padrao expand: schema pronto antes de alguem escrever nele).
--
--  Risco: baixo. Só ADD COLUMN nullable e CREATE INDEX; nenhum SELECT/INSERT
--  existente muda de forma.
--
--  Desfazer:
--    ALTER TABLE materiais DROP COLUMN conteudo, DROP COLUMN conteudo_versoes;
--    DROP INDEX ix_materiais_criado_por_criado_em ON materiais;
--    DROP INDEX ix_mag_student_created ON materiais_adaptados_gerados;
--  (versao/historico_versoes NAO devem ser removidas - o codigo usa.)
-- ============================================================================

-- ---------------------------------------------------------------------------
-- (1) conteudo
-- ---------------------------------------------------------------------------
SET @existe := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                 WHERE TABLE_SCHEMA = DATABASE()
                   AND TABLE_NAME = 'materiais'
                   AND COLUMN_NAME = 'conteudo');
SET @sql := IF(@existe = 0,
  'ALTER TABLE materiais ADD COLUMN conteudo MEDIUMTEXT NULL AFTER arquivo_path',
  'SELECT "materiais.conteudo ja existe - nada a fazer" AS resultado');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ---------------------------------------------------------------------------
-- (1) conteudo_versoes
-- ---------------------------------------------------------------------------
SET @existe := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                 WHERE TABLE_SCHEMA = DATABASE()
                   AND TABLE_NAME = 'materiais'
                   AND COLUMN_NAME = 'conteudo_versoes');
SET @sql := IF(@existe = 0,
  'ALTER TABLE materiais ADD COLUMN conteudo_versoes JSON NULL AFTER conteudo',
  'SELECT "materiais.conteudo_versoes ja existe - nada a fazer" AS resultado');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ---------------------------------------------------------------------------
-- (2) versao
-- ---------------------------------------------------------------------------
SET @existe := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                 WHERE TABLE_SCHEMA = DATABASE()
                   AND TABLE_NAME = 'materiais'
                   AND COLUMN_NAME = 'versao');
SET @sql := IF(@existe = 0,
  'ALTER TABLE materiais ADD COLUMN versao INT NULL DEFAULT 1',
  'SELECT "materiais.versao ja existe - nada a fazer" AS resultado');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ---------------------------------------------------------------------------
-- (2) historico_versoes
-- ---------------------------------------------------------------------------
SET @existe := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                 WHERE TABLE_SCHEMA = DATABASE()
                   AND TABLE_NAME = 'materiais'
                   AND COLUMN_NAME = 'historico_versoes');
SET @sql := IF(@existe = 0,
  'ALTER TABLE materiais ADD COLUMN historico_versoes JSON NULL',
  'SELECT "materiais.historico_versoes ja existe - nada a fazer" AS resultado');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ---------------------------------------------------------------------------
-- (3) indice da listagem da Biblioteca
-- ---------------------------------------------------------------------------
SET @existe := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
                 WHERE TABLE_SCHEMA = DATABASE()
                   AND TABLE_NAME = 'materiais'
                   AND INDEX_NAME = 'ix_materiais_criado_por_criado_em');
SET @sql := IF(@existe = 0,
  'CREATE INDEX ix_materiais_criado_por_criado_em ON materiais (criado_por_id, criado_em)',
  'SELECT "ix_materiais_criado_por_criado_em ja existe - nada a fazer" AS resultado');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ---------------------------------------------------------------------------
-- (3) indice do historico de materiais adaptados
-- ---------------------------------------------------------------------------
SET @existe := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
                 WHERE TABLE_SCHEMA = DATABASE()
                   AND TABLE_NAME = 'materiais_adaptados_gerados'
                   AND INDEX_NAME = 'ix_mag_student_created');
SET @sql := IF(@existe = 0,
  'CREATE INDEX ix_mag_student_created ON materiais_adaptados_gerados (student_id, created_at)',
  'SELECT "ix_mag_student_created ja existe - nada a fazer" AS resultado');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ============================================================================
-- CONFERENCIA
-- ============================================================================

-- esperado: arquivo_path, conteudo (mediumtext), conteudo_versoes (json),
--           versao (int), historico_versoes (json)
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
  FROM INFORMATION_SCHEMA.COLUMNS
 WHERE TABLE_SCHEMA = DATABASE()
   AND TABLE_NAME = 'materiais'
   AND COLUMN_NAME IN ('arquivo_path', 'conteudo', 'conteudo_versoes',
                       'versao', 'historico_versoes')
 ORDER BY ORDINAL_POSITION;

-- esperado: os dois indices, com as duas colunas cada
SELECT TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX, COLUMN_NAME
  FROM INFORMATION_SCHEMA.STATISTICS
 WHERE TABLE_SCHEMA = DATABASE()
   AND INDEX_NAME IN ('ix_materiais_criado_por_criado_em', 'ix_mag_student_created')
 ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;

-- quantos materiais ficaram sem conteudo recuperavel (o arquivo em disco ja
-- nao existe): sao os que o professor precisa regerar
SELECT COUNT(*) AS materiais_sem_conteudo
  FROM materiais
 WHERE conteudo IS NULL
   AND status = 'DISPONIVEL';
