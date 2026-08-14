-- ============================================================================
--  009 — folhas de redacao respondidas no papel (MODO PAPEL)
--
--  Igual em espirito a 008 (provas), mas para redacoes: guarda a foto/scan da
--  redacao manuscrita e o texto transcrito pela IA. A correcao por competencias
--  do ENEM (redacao_ai_service) so roda apos o professor revisar o texto.
--  Pendura em redacoes_alunos. Enum de status pelos NOMES em maiusculo, como
--  todo enum do SQLAlchemy neste schema.
--
--  Risco: baixo. Tabela NOVA, idempotente. Em dev o create_all ja cria; em
--  producao rodar antes/junto do deploy.
--
--  Desfazer: DROP TABLE IF EXISTS redacoes_alunos_folhas;
-- ============================================================================

CREATE TABLE IF NOT EXISTS redacoes_alunos_folhas (
  id                     INT          NOT NULL AUTO_INCREMENT,
  redacao_id             INT          NOT NULL,
  imagem_path            VARCHAR(500)                              DEFAULT NULL,
  texto_transcrito       TEXT                                     DEFAULT NULL,
  codigo_folha_detectado VARCHAR(50)                              DEFAULT NULL,
  status                 ENUM('TRANSCRITA','CONFIRMADA','ERRO')   DEFAULT NULL,
  criado_por_id          INT                                      DEFAULT NULL,
  criado_em              DATETIME                                 DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_redacoes_alunos_folhas_id (id),
  KEY ix_redacoes_alunos_folhas_redacao (redacao_id),
  CONSTRAINT redacoes_alunos_folhas_ibfk_1
    FOREIGN KEY (redacao_id) REFERENCES redacoes_alunos (id) ON DELETE CASCADE,
  CONSTRAINT redacoes_alunos_folhas_ibfk_2
    FOREIGN KEY (criado_por_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
  FROM INFORMATION_SCHEMA.COLUMNS
 WHERE TABLE_NAME = 'redacoes_alunos_folhas'
 ORDER BY ORDINAL_POSITION;
