-- ============================================================================
--  013 — CAA: pranchas de comunicacao e rotinas visuais (vertical CLINICA)
--
--  Comunicacao Alternativa e Ampliada (CAA): pranchas de comunicacao, rotinas
--  visuais e historias sociais montadas com pictogramas ARASAAC (reusa o
--  pictograma_service ja existente). Uma prancha pode ser de um paciente
--  especifico (paciente_id) ou um modelo da clinica (paciente_id NULL).
--
--  Cada item guarda apenas arasaac_id + URL do CDN + rotulo (nao copiamos a
--  imagem para o storage), no mesmo padrao de `ilustracoes`.
--
--  Risco: baixo. Tabelas NOVAS. Idempotente. Pre-req: 011 (pacientes).
--
--  Desfazer:
--    DROP TABLE IF EXISTS prancha_itens;
--    DROP TABLE IF EXISTS pranchas;
-- ============================================================================

CREATE TABLE IF NOT EXISTS pranchas (
  id            INT                                        NOT NULL AUTO_INCREMENT,
  escola_id     INT                                        NOT NULL,
  paciente_id   INT                                        DEFAULT NULL,  -- NULL = modelo da clinica
  titulo        VARCHAR(255)                               NOT NULL,
  tipo          ENUM('COMUNICACAO','ROTINA','HISTORIA_SOCIAL')  NOT NULL DEFAULT 'COMUNICACAO',
  criado_por_id INT                                        DEFAULT NULL,
  criado_em     DATETIME                                   DEFAULT NULL,
  atualizado_em DATETIME                                   DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_pranchas_escola (escola_id),
  KEY ix_pranchas_paciente (paciente_id),
  CONSTRAINT pranchas_ibfk_1
    FOREIGN KEY (escola_id) REFERENCES escolas (id) ON DELETE CASCADE,
  CONSTRAINT pranchas_ibfk_2
    FOREIGN KEY (paciente_id) REFERENCES pacientes (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prancha_itens (
  id          INT                                          NOT NULL AUTO_INCREMENT,
  prancha_id  INT                                          NOT NULL,
  ordem       INT                                          NOT NULL DEFAULT 0,
  arasaac_id  INT                                          DEFAULT NULL,
  imagem_url  VARCHAR(1000)                                DEFAULT NULL,
  rotulo      VARCHAR(255)                                 NOT NULL,
  criado_em   DATETIME                                     DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_prancha_itens_prancha (prancha_id),
  CONSTRAINT prancha_itens_ibfk_1
    FOREIGN KEY (prancha_id) REFERENCES pranchas (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- conferencia — esperado: as 2 tabelas novas
SELECT TABLE_NAME
  FROM INFORMATION_SCHEMA.TABLES
 WHERE TABLE_NAME IN ('pranchas','prancha_itens')
 ORDER BY TABLE_NAME;

-- ============================================================================
-- Fim da 013. (Portal da familia pode exibir estas pranchas no futuro.)
-- ============================================================================
