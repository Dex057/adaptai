-- ============================================================================
--  021 — tabela de precos por especialidade (faturamento por sessao)
--
--  Preco padrao por especialidade, por tenant. Quando uma folha de sessao e
--  confirmada, o sistema gera um item de faturamento usando este valor.
--
--  Risco: baixo. Tabela NOVA. Idempotente. Pre-req: 011 (escolas), 020 (faturamentos).
--
--  Desfazer: DROP TABLE IF EXISTS precos_especialidade;
-- ============================================================================

CREATE TABLE IF NOT EXISTS precos_especialidade (
  id            INT           NOT NULL AUTO_INCREMENT,
  escola_id     INT           NOT NULL,
  especialidade ENUM('PSICOLOGIA_ABA','FONOAUDIOLOGIA','TERAPIA_OCUPACIONAL','PSICOPEDAGOGIA','FISIOTERAPIA','MUSICOTERAPIA','NUTRICAO','NEUROPEDIATRIA','OUTRO') NOT NULL,
  valor         DECIMAL(10,2) NOT NULL DEFAULT 0.00,
  criado_em     DATETIME      DEFAULT NULL,
  atualizado_em DATETIME      DEFAULT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_preco_esp (escola_id, especialidade),
  CONSTRAINT preco_esp_ibfk_1 FOREIGN KEY (escola_id) REFERENCES escolas (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'precos_especialidade';
