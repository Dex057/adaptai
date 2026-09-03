-- ============================================================================
--  023 — anexos do prontuario (vertical CLINICA)
--
--  Documentos anexados ao prontuario do paciente (laudos, exames, fotos). Os
--  BYTES ficam no volume (ANEXOS_DIR); aqui guardamos so os metadados + o
--  caminho relativo. Servido por endpoint autenticado (dado de saude, LGPD).
--
--  Risco: baixo. Tabela NOVA. Idempotente. Pre-req: 011 (pacientes).
--
--  Desfazer: DROP TABLE IF EXISTS anexos_prontuario;
-- ============================================================================

CREATE TABLE IF NOT EXISTS anexos_prontuario (
  id             INT          NOT NULL AUTO_INCREMENT,
  escola_id      INT          NOT NULL,
  paciente_id    INT          NOT NULL,
  nome_original  VARCHAR(255) NOT NULL,
  mime           VARCHAR(120) DEFAULT NULL,
  tamanho_bytes  INT          DEFAULT NULL,
  caminho        VARCHAR(500) NOT NULL,       -- relativo a ANEXOS_DIR: <escola_id>/<uuid>.<ext>
  categoria      VARCHAR(60)  DEFAULT NULL,   -- LAUDO / EXAME / FOTO / OUTRO
  descricao      VARCHAR(500) DEFAULT NULL,
  enviado_por_id INT          DEFAULT NULL,
  criado_em      DATETIME     DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_anexos_paciente (paciente_id),
  CONSTRAINT anexo_ibfk_1 FOREIGN KEY (paciente_id) REFERENCES pacientes (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'anexos_prontuario';
