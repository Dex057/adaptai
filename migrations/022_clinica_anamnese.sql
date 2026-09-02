-- ============================================================================
--  022 — anamnese / admissao do paciente (vertical CLINICA)
--
--  Ficha de avaliacao inicial: uma por paciente (a porta de entrada do
--  prontuario). Campos em blocos (queixa, gestacao, desenvolvimento, medico,
--  familiar, rotina, comunicacao, comportamento, escolaridade, terapias
--  anteriores, medicacoes, observacoes).
--
--  Risco: baixo. Tabela NOVA. Idempotente. Pre-req: 011 (pacientes).
--
--  Desfazer: DROP TABLE IF EXISTS anamneses;
-- ============================================================================

CREATE TABLE IF NOT EXISTS anamneses (
  id                       INT       NOT NULL AUTO_INCREMENT,
  escola_id                INT       NOT NULL,
  paciente_id              INT       NOT NULL,
  queixa_principal         TEXT      DEFAULT NULL,
  historico_gestacional    TEXT      DEFAULT NULL,
  historico_desenvolvimento TEXT     DEFAULT NULL,
  historico_medico         TEXT      DEFAULT NULL,
  historico_familiar       TEXT      DEFAULT NULL,
  rotina                   TEXT      DEFAULT NULL,
  comunicacao              TEXT      DEFAULT NULL,
  comportamento            TEXT      DEFAULT NULL,
  escolaridade             TEXT      DEFAULT NULL,
  terapias_anteriores      TEXT      DEFAULT NULL,
  medicacoes               TEXT      DEFAULT NULL,
  observacoes              TEXT      DEFAULT NULL,
  preenchido_por_id        INT       DEFAULT NULL,
  criado_em                DATETIME  DEFAULT NULL,
  atualizado_em            DATETIME  DEFAULT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_anamnese_paciente (paciente_id),
  CONSTRAINT anamnese_ibfk_1 FOREIGN KEY (paciente_id) REFERENCES pacientes (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'anamneses';
