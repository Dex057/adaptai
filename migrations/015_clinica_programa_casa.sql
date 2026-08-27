-- ============================================================================
--  015 — programa de casa (vertical CLINICA)
--
--  Tarefas de generalizacao que o terapeuta define para o paciente fazer em
--  casa; a familia marca "fez/nao fez" pelo portal (token). Fecha o laco
--  clinica <-> casa.
--
--  Risco: baixo. Tabelas NOVAS. Idempotente. Pre-req: 011 (pacientes).
--
--  Desfazer:
--    DROP TABLE IF EXISTS tarefa_casa_check;
--    DROP TABLE IF EXISTS tarefas_casa;
-- ============================================================================

CREATE TABLE IF NOT EXISTS tarefas_casa (
  id            INT           NOT NULL AUTO_INCREMENT,
  escola_id     INT           NOT NULL,
  paciente_id   INT           NOT NULL,
  titulo        VARCHAR(255)  NOT NULL,
  descricao     TEXT          DEFAULT NULL,
  ativo         TINYINT(1)    NOT NULL DEFAULT 1,
  criado_por_id INT           DEFAULT NULL,
  criado_em     DATETIME      DEFAULT NULL,
  atualizado_em DATETIME      DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_tarefas_casa_paciente (paciente_id),
  CONSTRAINT tarefas_casa_ibfk_1 FOREIGN KEY (paciente_id) REFERENCES pacientes (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS tarefa_casa_check (
  id         INT           NOT NULL AUTO_INCREMENT,
  tarefa_id  INT           NOT NULL,
  data       DATE          NOT NULL,
  feito      TINYINT(1)    NOT NULL DEFAULT 0,
  observacao VARCHAR(500)  DEFAULT NULL,
  criado_em  DATETIME      DEFAULT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY ux_tarefa_data (tarefa_id, data),
  CONSTRAINT tarefa_casa_check_ibfk_1 FOREIGN KEY (tarefa_id) REFERENCES tarefas_casa (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- conferencia
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
 WHERE TABLE_NAME IN ('tarefas_casa','tarefa_casa_check') ORDER BY TABLE_NAME;
