-- ============================================================================
--  016 — mensagens equipe <-> familia (vertical CLINICA)
--
--  Canal simples de recados por paciente. A equipe posta (autenticada) e a
--  familia posta/le pelo portal (token). Origem marca de que lado veio.
--
--  Risco: baixo. Tabela NOVA. Idempotente. Pre-req: 011 (pacientes).
--
--  Desfazer:
--    DROP TABLE IF EXISTS mensagens_familia;
-- ============================================================================

CREATE TABLE IF NOT EXISTS mensagens_familia (
  id          INT                        NOT NULL AUTO_INCREMENT,
  escola_id   INT                        NOT NULL,
  paciente_id INT                        NOT NULL,
  origem      ENUM('EQUIPE','FAMILIA')   NOT NULL,
  autor_id    INT                        DEFAULT NULL,  -- users.id quando origem=EQUIPE
  texto       TEXT                       NOT NULL,
  criado_em   DATETIME                   DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_msg_familia_paciente (paciente_id, id),
  CONSTRAINT msg_familia_ibfk_1 FOREIGN KEY (paciente_id) REFERENCES pacientes (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'mensagens_familia';
