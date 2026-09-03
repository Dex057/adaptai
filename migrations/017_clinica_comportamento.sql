-- ============================================================================
--  017 — registro de comportamento (ABC) (vertical CLINICA)
--
--  Registro ABC (Antecedente-Comportamento-Consequencia) + metricas de
--  frequencia/duracao/intensidade de comportamentos-alvo. Complementa o
--  registro de tentativas (dado de habilidade) com o dado de comportamento.
--
--  Risco: baixo. Tabela NOVA. Idempotente. Pre-req: 011 (pacientes) e 012 (sessoes).
--
--  Desfazer:
--    DROP TABLE IF EXISTS registros_comportamento;
-- ============================================================================

CREATE TABLE IF NOT EXISTS registros_comportamento (
  id            INT                                  NOT NULL AUTO_INCREMENT,
  escola_id     INT                                  NOT NULL,
  paciente_id   INT                                  NOT NULL,
  sessao_id     INT                                  DEFAULT NULL,
  comportamento VARCHAR(255)                         NOT NULL,   -- comportamento-alvo
  antecedente   TEXT                                 DEFAULT NULL,
  consequencia  TEXT                                 DEFAULT NULL,
  frequencia    INT                                  DEFAULT NULL,  -- ocorrencias
  duracao_seg   INT                                  DEFAULT NULL,  -- duracao total (s)
  intensidade   ENUM('LEVE','MODERADA','INTENSA')    DEFAULT NULL,
  data_hora     DATETIME                             DEFAULT NULL,
  criado_por_id INT                                  DEFAULT NULL,
  criado_em     DATETIME                             DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_reg_comp_paciente (paciente_id, id),
  KEY ix_reg_comp_sessao (sessao_id),
  CONSTRAINT reg_comp_ibfk_1 FOREIGN KEY (paciente_id) REFERENCES pacientes (id) ON DELETE CASCADE,
  CONSTRAINT reg_comp_ibfk_2 FOREIGN KEY (sessao_id) REFERENCES sessoes (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'registros_comportamento';
