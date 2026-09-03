-- ============================================================================
--  018 — aplicacao de instrumentos padronizados (vertical CLINICA)
--
--  Registro de aplicacao de instrumentos/escalas (VB-MAPP, ABLLS, Vineland,
--  PEP-3, M-CHAT, CARS...) com pontuacao, para acompanhar evolucao no tempo.
--  MVP generico (nome + pontuacao + data); bancos de itens por instrumento
--  ficam para uma fase futura.
--
--  Risco: baixo. Tabela NOVA. Idempotente. Pre-req: 011 (pacientes).
--
--  Desfazer:
--    DROP TABLE IF EXISTS aplicacoes_instrumento;
-- ============================================================================

CREATE TABLE IF NOT EXISTS aplicacoes_instrumento (
  id            INT            NOT NULL AUTO_INCREMENT,
  escola_id     INT            NOT NULL,
  paciente_id   INT            NOT NULL,
  instrumento   VARCHAR(120)   NOT NULL,             -- ex.: VB-MAPP, Vineland-3
  data          DATE           DEFAULT NULL,
  pontuacao     DECIMAL(7,2)   DEFAULT NULL,
  pontuacao_max DECIMAL(7,2)   DEFAULT NULL,
  observacao    TEXT           DEFAULT NULL,
  criado_por_id INT            DEFAULT NULL,
  criado_em     DATETIME       DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_aplic_instr_paciente (paciente_id, instrumento, data),
  CONSTRAINT aplic_instr_ibfk_1 FOREIGN KEY (paciente_id) REFERENCES pacientes (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'aplicacoes_instrumento';
