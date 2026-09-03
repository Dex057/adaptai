-- ============================================================================
--  025 — supervisao & qualidade ABA (vertical CLINICA)
--
--  1) aprovacao/assinatura do PTI: colunas em `planos_terapeuticos`.
--  2) `fidelidade_aplicacao`: checklist de fidelidade por sessao (% aplicado).
--  3) `ioa_registros`: concordancia entre observadores (IOA) por sessao.
--
--  Risco: baixo. ADD COLUMN idempotente (checa information_schema) + 2 tabelas NOVAS.
--  Pre-req: 012 (planos/sessoes).
--
--  Desfazer:
--    DROP TABLE IF EXISTS ioa_registros;
--    DROP TABLE IF EXISTS fidelidade_aplicacao;
--    ALTER TABLE planos_terapeuticos
--      DROP COLUMN aprovado_por_id, DROP COLUMN aprovado_em,
--      DROP COLUMN assinatura_hash, DROP COLUMN revisao_nota;
-- ============================================================================

SET @c := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='planos_terapeuticos' AND COLUMN_NAME='aprovado_por_id');
SET @s := IF(@c=0,'ALTER TABLE planos_terapeuticos ADD COLUMN aprovado_por_id INT DEFAULT NULL','SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @c := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='planos_terapeuticos' AND COLUMN_NAME='aprovado_em');
SET @s := IF(@c=0,'ALTER TABLE planos_terapeuticos ADD COLUMN aprovado_em DATETIME DEFAULT NULL','SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @c := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='planos_terapeuticos' AND COLUMN_NAME='assinatura_hash');
SET @s := IF(@c=0,'ALTER TABLE planos_terapeuticos ADD COLUMN assinatura_hash VARCHAR(64) DEFAULT NULL','SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @c := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='planos_terapeuticos' AND COLUMN_NAME='revisao_nota');
SET @s := IF(@c=0,'ALTER TABLE planos_terapeuticos ADD COLUMN revisao_nota VARCHAR(500) DEFAULT NULL','SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

CREATE TABLE IF NOT EXISTS fidelidade_aplicacao (
  id            INT           NOT NULL AUTO_INCREMENT,
  escola_id     INT           NOT NULL,
  sessao_id     INT           NOT NULL,
  observador_id INT           DEFAULT NULL,
  itens         TEXT          DEFAULT NULL,
  total_itens   INT           NOT NULL DEFAULT 0,
  itens_ok      INT           NOT NULL DEFAULT 0,
  percentual    DECIMAL(5,2)  NOT NULL DEFAULT 0,
  observacao    VARCHAR(500)  DEFAULT NULL,
  criado_em     DATETIME      DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_fidelidade_sessao (sessao_id),
  CONSTRAINT fidelidade_ibfk_1 FOREIGN KEY (sessao_id) REFERENCES sessoes (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ioa_registros (
  id                INT           NOT NULL AUTO_INCREMENT,
  escola_id         INT           NOT NULL,
  sessao_id         INT           NOT NULL,
  objetivo_id       INT           DEFAULT NULL,
  metodo            VARCHAR(30)   DEFAULT NULL,
  observador2_nome  VARCHAR(255)  DEFAULT NULL,
  concordancias     INT           NOT NULL DEFAULT 0,
  total             INT           NOT NULL DEFAULT 0,
  percentual        DECIMAL(5,2)  NOT NULL DEFAULT 0,
  observacao        VARCHAR(500)  DEFAULT NULL,
  registrado_por_id INT           DEFAULT NULL,
  criado_em         DATETIME      DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_ioa_sessao (sessao_id),
  CONSTRAINT ioa_ibfk_1 FOREIGN KEY (sessao_id) REFERENCES sessoes (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME IN ('fidelidade_aplicacao','ioa_registros');
