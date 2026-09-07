-- ============================================================================
--  030 — Biblioteca de Estrategias de Adaptacao (base curada por transtorno)
--
--  Base editavel que mapeia transtorno/CID -> diretrizes de adaptacao, injetada
--  nos geradores de tarefa. escola_id NULL = estrategia base (global); preenchido
--  = customizacao da escola. Espelha app/models/estrategia_adaptacao.py.
--
--  Tabela NOVA; nada existente muda. O seed das estrategias-base e feito pelo
--  endpoint POST /estrategias-adaptacao/seed (idempotente) ou pelo create_all+seed.
--
--  Desfazer: DROP TABLE IF EXISTS estrategias_adaptacao;
-- ============================================================================

CREATE TABLE IF NOT EXISTS estrategias_adaptacao (
  id            INT          NOT NULL AUTO_INCREMENT,
  escola_id     INT                           DEFAULT NULL,
  transtorno    VARCHAR(60)  NOT NULL,
  cid           VARCHAR(100)                  DEFAULT NULL,
  titulo        VARCHAR(200)                  DEFAULT NULL,
  diretrizes    TEXT         NOT NULL,
  fonte         VARCHAR(500)                  DEFAULT NULL,
  ativo         TINYINT(1)                    DEFAULT 1,
  ordem         INT                           DEFAULT 100,
  criado_por_id INT                           DEFAULT NULL,
  criado_em     DATETIME                      DEFAULT NULL,
  atualizado_em DATETIME                      DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_estrategias_transtorno (transtorno),
  KEY ix_estrategias_escola (escola_id),
  KEY ix_estrategias_ativo (ativo),
  CONSTRAINT estrategias_ibfk_1 FOREIGN KEY (escola_id) REFERENCES escolas (id) ON DELETE CASCADE,
  CONSTRAINT estrategias_ibfk_2 FOREIGN KEY (criado_por_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
  FROM INFORMATION_SCHEMA.COLUMNS
 WHERE TABLE_NAME = 'estrategias_adaptacao'
 ORDER BY ORDINAL_POSITION;
