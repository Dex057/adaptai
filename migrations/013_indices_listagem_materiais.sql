-- ============================================================================
--  013 - Indices de listagem + colunas de versionamento que podem estar
--        faltando em producao
--
--  Complementa a 012 (materiais.conteudo_gerado + tipo 'geometria'), que
--  resolveu ONDE o conteudo mora. Esta trata do PESO de ler esse conteudo sem
--  querer, e de um buraco de schema anterior.
--
--  ---------------------------------------------------------------------------
--  (1) Indices - "1038 Out of sort memory"
--  ---------------------------------------------------------------------------
--  GET /materiais-adaptados/historico/student/{id} caiu em producao com:
--
--    pymysql.err.OperationalError: (1038, 'Out of sort memory, consider
--    increasing server sort buffer size')
--
--  Nao e volume de linhas, e TAMANHO de linha. O SELECT trazia
--  materiais_adaptados_gerados.* - inclusive resultado_json, que com
--  hq_tirinha/album_figurinhas carrega imagens embutidas - e ordenava por
--  created_at sem indice: filesort de linhas de megabytes. A mesma armadilha
--  passou a existir em `materiais` depois da 012, que colocou um LONGTEXT com
--  o material inteiro na linha.
--
--  O codigo ja foi corrigido nas duas pontas (colunas grandes viraram
--  `deferred` no model e as listagens selecionam colunas explicitas). Os
--  indices abaixo eliminam o filesort que sobra quando o volume por
--  aluno/professor cresce.
--
--  ---------------------------------------------------------------------------
--  (2) materiais.versao / materiais.historico_versoes - COLUNAS SEM MIGRATION
--  ---------------------------------------------------------------------------
--  O versionamento de material entrou no codigo em 08/06/2026 (commit
--  71b18c6) por um script Python avulso (aplicar_migracao_materiais_versao.py)
--  que depois saiu do repositorio - nao ha registro de ter rodado em
--  producao. Se essas colunas NAO existirem no MySQL, todo `SELECT
--  materiais.*` falha com
--
--      (1054, "Unknown column 'materiais.versao' in 'field list'")
--
--  e a Biblioteca abre direto em "Nao foi possivel carregar os materiais" -
--  um dos sintomas relatados em 18/08. Os ADDs sao condicionais: se as colunas
--  ja existem (o caso esperado), nada acontece.
--
--  ---------------------------------------------------------------------------
--  COMO RODAR
--  ---------------------------------------------------------------------------
--  Cole o arquivo inteiro no console MySQL do Railway, DEPOIS da 012.
--  E IDEMPOTENTE: cada passo consulta o INFORMATION_SCHEMA antes de executar,
--  entao rodar duas vezes nao da erro (a segunda so imprime "ja existe").
--
--  Risco: baixo. ADD COLUMN nullable + CREATE INDEX; nenhum SELECT/INSERT
--  existente muda de forma. Diferente da 012, esta pode rodar depois do deploy
--  sem quebrar nada - o codigo novo nao depende dos indices para funcionar,
--  so para ser rapido.
--
--  Desfazer:
--    DROP INDEX ix_materiais_criado_por_criado_em ON materiais;
--    DROP INDEX ix_mag_student_created ON materiais_adaptados_gerados;
--  (versao/historico_versoes NAO devem ser removidas - o codigo usa.)
-- ============================================================================

-- ---------------------------------------------------------------------------
-- (1) indice da listagem da Biblioteca
--     WHERE criado_por_id = ? ORDER BY criado_em DESC
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
-- (1) indice do historico de materiais adaptados
--     WHERE student_id = ? ORDER BY created_at DESC
-- ---------------------------------------------------------------------------
SET @existe := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
                 WHERE TABLE_SCHEMA = DATABASE()
                   AND TABLE_NAME = 'materiais_adaptados_gerados'
                   AND INDEX_NAME = 'ix_mag_student_created');
SET @sql := IF(@existe = 0,
  'CREATE INDEX ix_mag_student_created ON materiais_adaptados_gerados (student_id, created_at)',
  'SELECT "ix_mag_student_created ja existe - nada a fazer" AS resultado');
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

-- ============================================================================
-- CONFERENCIA
-- ============================================================================

-- esperado: os dois indices, com as duas colunas cada
SELECT TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX, COLUMN_NAME
  FROM INFORMATION_SCHEMA.STATISTICS
 WHERE TABLE_SCHEMA = DATABASE()
   AND INDEX_NAME IN ('ix_materiais_criado_por_criado_em', 'ix_mag_student_created')
 ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;

-- esperado: conteudo_gerado (longtext, da 012), versao (int), historico_versoes (json)
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
  FROM INFORMATION_SCHEMA.COLUMNS
 WHERE TABLE_SCHEMA = DATABASE()
   AND TABLE_NAME = 'materiais'
   AND COLUMN_NAME IN ('arquivo_path', 'conteudo_gerado', 'versao', 'historico_versoes')
 ORDER BY ORDINAL_POSITION;

-- quantos materiais ficaram sem conteudo recuperavel (o arquivo em disco ja
-- nao existe): sao os que o professor precisa regerar
SELECT COUNT(*) AS materiais_sem_conteudo
  FROM materiais
 WHERE conteudo_gerado IS NULL
   AND status = 'DISPONIVEL';
