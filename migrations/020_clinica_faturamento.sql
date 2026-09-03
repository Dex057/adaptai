-- ============================================================================
--  020 — faturamento e convenios (vertical CLINICA)
--
--  MVP de faturamento da clinica multidisciplinar:
--    - `convenios`     : cadastro de fontes pagadoras (particular/convenio/SUS).
--    - `faturamentos`  : item faturavel por competencia (mes), opcionalmente
--                        ligado a uma sessao e a um convenio, com valor e status.
--
--  Nao altera `sessoes` nem `pacientes` (sem ADD COLUMN): o vinculo e feito por
--  FK em `faturamentos`, mantendo o resto do vertical intacto.
--
--  Risco: baixo. Tabelas NOVAS. Idempotente. Pre-req: 011 (pacientes), 012 (sessoes).
--
--  Desfazer:
--    DROP TABLE IF EXISTS faturamentos;
--    DROP TABLE IF EXISTS convenios;
-- ============================================================================

CREATE TABLE IF NOT EXISTS convenios (
  id           INT           NOT NULL AUTO_INCREMENT,
  escola_id    INT           NOT NULL,
  nome         VARCHAR(200)  NOT NULL,
  tipo         ENUM('PARTICULAR','CONVENIO','SUS') NOT NULL DEFAULT 'CONVENIO',
  registro_ans VARCHAR(60)   DEFAULT NULL,          -- registro na ANS (quando convenio)
  ativo        TINYINT(1)    NOT NULL DEFAULT 1,
  criado_em    DATETIME      DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_convenios_escola (escola_id, ativo),
  CONSTRAINT convenios_ibfk_1 FOREIGN KEY (escola_id) REFERENCES escolas (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS faturamentos (
  id           INT            NOT NULL AUTO_INCREMENT,
  escola_id    INT            NOT NULL,
  paciente_id  INT            NOT NULL,
  sessao_id    INT            DEFAULT NULL,
  convenio_id  INT            DEFAULT NULL,
  competencia  VARCHAR(7)     NOT NULL,             -- 'YYYY-MM'
  valor        DECIMAL(10,2)  NOT NULL DEFAULT 0.00,
  status       ENUM('A_FATURAR','FATURADO','PAGO','GLOSADO') NOT NULL DEFAULT 'A_FATURAR',
  observacao   VARCHAR(255)   DEFAULT NULL,
  criado_por_id INT           DEFAULT NULL,
  criado_em    DATETIME       DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_fat_paciente (paciente_id, competencia),
  KEY ix_fat_escola_comp (escola_id, competencia, status),
  CONSTRAINT fat_ibfk_1 FOREIGN KEY (paciente_id) REFERENCES pacientes (id) ON DELETE CASCADE,
  CONSTRAINT fat_ibfk_2 FOREIGN KEY (sessao_id)  REFERENCES sessoes (id)   ON DELETE SET NULL,
  CONSTRAINT fat_ibfk_3 FOREIGN KEY (convenio_id) REFERENCES convenios (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- conferencia
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
 WHERE TABLE_NAME IN ('convenios','faturamentos');
