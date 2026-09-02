-- ============================================================================
--  024 — repasse ao profissional (vertical CLINICA)
--
--  1) percentual_repasse em `profissionais` (contrato: quanto o prof recebe).
--  2) tabela `repasses`: fecha por competencia (mes) o quanto cada profissional
--     recebe, com base no faturado das sessoes dele. status PENDENTE/PAGO.
--
--  Risco: baixo. ADD COLUMN idempotente (checa information_schema) + tabela NOVA.
--  Pre-req: 020 (faturamentos), 011 (profissionais).
--
--  Desfazer:
--    DROP TABLE IF EXISTS repasses;
--    ALTER TABLE profissionais DROP COLUMN percentual_repasse;
-- ============================================================================

SET @exist := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = DATABASE()
     AND TABLE_NAME = 'profissionais'
     AND COLUMN_NAME = 'percentual_repasse'
);
SET @sql := IF(@exist = 0,
  'ALTER TABLE profissionais ADD COLUMN percentual_repasse DECIMAL(5,2) DEFAULT NULL',
  'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS repasses (
  id              INT           NOT NULL AUTO_INCREMENT,
  escola_id       INT           NOT NULL,
  profissional_id INT           NOT NULL,
  competencia     VARCHAR(7)    NOT NULL,
  valor_base      DECIMAL(10,2) NOT NULL DEFAULT 0,
  percentual      DECIMAL(5,2)  NOT NULL DEFAULT 0,
  valor_repasse   DECIMAL(10,2) NOT NULL DEFAULT 0,
  status          VARCHAR(20)   NOT NULL DEFAULT 'PENDENTE',
  observacao      VARCHAR(255)  DEFAULT NULL,
  pago_em         DATETIME      DEFAULT NULL,
  criado_em       DATETIME      DEFAULT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_repasse_prof_comp (profissional_id, competencia),
  KEY ix_repasse_comp (escola_id, competencia),
  CONSTRAINT repasse_ibfk_1 FOREIGN KEY (profissional_id) REFERENCES profissionais (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'repasses';
