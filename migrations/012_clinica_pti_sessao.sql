-- ============================================================================
--  012 — PTI, sessao e evolucao (Fase 1: Modulo 1 do MVP clinico)
--
--  Contexto: o nucleo clinico (011) criou paciente/profissional/equipe. Esta
--  migration adiciona a espinha dorsal do atendimento: o Plano Terapeutico
--  Individual (PTI) com objetivos/metas por especialidade, a sessao, a coleta
--  de tentativas (dado de ABA/independencia) e a nota de evolucao.
--
--  REUSO DE PADRAO (nao de tabela): espelha o desenho ja provado do PEI
--  educacional (peis -> pei_objetivos -> status), mas em tabelas proprias que
--  penduram em `pacientes` — o vertical CLINICA nao pode depender das tabelas
--  do vertical ESCOLA (peis/students). Mesmo padrao, dominios isolados.
--
--  Regra "IA rascunha, humano assina": `evolucoes.rascunho_ia` marca texto
--  gerado por IA; so vale apos `assinado_por_id`/`assinado_em` (profissional
--  habilitado / RT). Mesma regra do Modo Papel.
--
--  Ciclo de vida do objetivo (status clinico):
--    BASELINE -> EM_AQUISICAO -> MASTERY -> MANUTENCAO -> GENERALIZACAO
--    (ou DESCONTINUADO).
--
--  Risco: baixo. Tabelas NOVAS; nada existente muda. Idempotente.
--  Pre-requisito: 011 aplicada (FK para pacientes/profissionais).
--
--  Desfazer:
--    DROP TABLE IF EXISTS registros_tentativa;
--    DROP TABLE IF EXISTS evolucoes;
--    DROP TABLE IF EXISTS sessoes;
--    DROP TABLE IF EXISTS objetivos_terapeuticos;
--    DROP TABLE IF EXISTS planos_terapeuticos;
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1) PLANO TERAPEUTICO INDIVIDUAL (PTI) — espelha `peis`.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS planos_terapeuticos (
  id             INT                                        NOT NULL AUTO_INCREMENT,
  escola_id      INT                                        NOT NULL,
  paciente_id    INT                                        NOT NULL,
  titulo         VARCHAR(255)                               NOT NULL,
  periodo_inicio DATE                                       DEFAULT NULL,
  periodo_fim    DATE                                       DEFAULT NULL,
  status         ENUM('RASCUNHO','ATIVO','EM_REVISAO','CONCLUIDO','ARQUIVADO')
                                                            NOT NULL DEFAULT 'RASCUNHO',
  criado_por_id  INT                                        DEFAULT NULL,
  criado_em      DATETIME                                   DEFAULT NULL,
  atualizado_em  DATETIME                                   DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_planos_ter_paciente (paciente_id),
  KEY ix_planos_ter_escola (escola_id),
  KEY ix_planos_ter_status (status),
  CONSTRAINT planos_ter_ibfk_1
    FOREIGN KEY (paciente_id) REFERENCES pacientes (id) ON DELETE CASCADE,
  CONSTRAINT planos_ter_ibfk_2
    FOREIGN KEY (criado_por_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 2) OBJETIVO / META (Programa) — espelha `pei_objetivos`, com ciclo clinico.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS objetivos_terapeuticos (
  id               INT                                      NOT NULL AUTO_INCREMENT,
  plano_id         INT                                      NOT NULL,
  especialidade    ENUM('PSICOLOGIA_ABA','FONOAUDIOLOGIA','TERAPIA_OCUPACIONAL',
                        'PSICOPEDAGOGIA','FISIOTERAPIA','MUSICOTERAPIA','NUTRICAO',
                        'NEUROPEDIATRIA','OUTRO')           NOT NULL,
  descricao        TEXT                                     NOT NULL,
  criterio_mastery VARCHAR(500)                             DEFAULT NULL,
  linha_base       DECIMAL(5,2)                             DEFAULT NULL,  -- % inicial
  status           ENUM('BASELINE','EM_AQUISICAO','MASTERY','MANUTENCAO',
                        'GENERALIZACAO','DESCONTINUADO')    NOT NULL DEFAULT 'BASELINE',
  ordem            INT                                      DEFAULT 0,
  criado_em        DATETIME                                 DEFAULT NULL,
  atualizado_em    DATETIME                                 DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_objetivos_ter_plano (plano_id),
  KEY ix_objetivos_ter_status (status),
  CONSTRAINT objetivos_ter_ibfk_1
    FOREIGN KEY (plano_id) REFERENCES planos_terapeuticos (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 3) SESSAO — o atendimento (encontro terapeutico).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessoes (
  id              INT                                       NOT NULL AUTO_INCREMENT,
  escola_id       INT                                       NOT NULL,
  paciente_id     INT                                       NOT NULL,
  profissional_id INT                                       NOT NULL,
  especialidade   ENUM('PSICOLOGIA_ABA','FONOAUDIOLOGIA','TERAPIA_OCUPACIONAL',
                       'PSICOPEDAGOGIA','FISIOTERAPIA','MUSICOTERAPIA','NUTRICAO',
                       'NEUROPEDIATRIA','OUTRO')            NOT NULL,
  data_sessao     DATETIME                                  DEFAULT NULL,
  duracao_min     INT                                       DEFAULT NULL,
  presenca        ENUM('PRESENTE','FALTA','REMARCADA')      NOT NULL DEFAULT 'PRESENTE',
  observacao      TEXT                                      DEFAULT NULL,
  criado_em       DATETIME                                  DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_sessoes_paciente (paciente_id),
  KEY ix_sessoes_profissional (profissional_id),
  KEY ix_sessoes_escola_data (escola_id, data_sessao),
  CONSTRAINT sessoes_ibfk_1
    FOREIGN KEY (paciente_id) REFERENCES pacientes (id) ON DELETE CASCADE,
  CONSTRAINT sessoes_ibfk_2
    FOREIGN KEY (profissional_id) REFERENCES profissionais (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 4) REGISTRO DE TENTATIVA — dado por meta por sessao (ABA/independencia).
--    Alimenta a curva de evolucao e o criterio de mastery.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS registros_tentativa (
  id             INT                                        NOT NULL AUTO_INCREMENT,
  sessao_id      INT                                        NOT NULL,
  objetivo_id    INT                                        NOT NULL,
  tentativas     INT                                        NOT NULL DEFAULT 0,
  acertos        INT                                        NOT NULL DEFAULT 0,
  nivel_ajuda    ENUM('INDEPENDENTE','AJUDA_VERBAL','AJUDA_GESTUAL',
                      'AJUDA_FISICA_PARCIAL','AJUDA_FISICA_TOTAL')  DEFAULT NULL,
  percentual_independencia DECIMAL(5,2)                     DEFAULT NULL,
  criado_em      DATETIME                                   DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_reg_tent_sessao (sessao_id),
  KEY ix_reg_tent_objetivo (objetivo_id),
  CONSTRAINT reg_tent_ibfk_1
    FOREIGN KEY (sessao_id) REFERENCES sessoes (id) ON DELETE CASCADE,
  CONSTRAINT reg_tent_ibfk_2
    FOREIGN KEY (objetivo_id) REFERENCES objetivos_terapeuticos (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 5) EVOLUCAO — nota clinica da sessao. IA rascunha; profissional assina.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evolucoes (
  id              INT                                       NOT NULL AUTO_INCREMENT,
  escola_id       INT                                       NOT NULL,
  paciente_id     INT                                       NOT NULL,
  sessao_id       INT                                       DEFAULT NULL,
  profissional_id INT                                       DEFAULT NULL,
  especialidade   ENUM('PSICOLOGIA_ABA','FONOAUDIOLOGIA','TERAPIA_OCUPACIONAL',
                       'PSICOPEDAGOGIA','FISIOTERAPIA','MUSICOTERAPIA','NUTRICAO',
                       'NEUROPEDIATRIA','OUTRO')            DEFAULT NULL,
  texto           TEXT                                      NOT NULL,
  rascunho_ia     TINYINT(1)                                NOT NULL DEFAULT 0,
  assinado_por_id INT                                       DEFAULT NULL,  -- users.id (RT/prof.)
  assinado_em     DATETIME                                  DEFAULT NULL,  -- NULL = nao assinada
  criado_em       DATETIME                                  DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_evolucoes_paciente (paciente_id),
  KEY ix_evolucoes_sessao (sessao_id),
  CONSTRAINT evolucoes_ibfk_1
    FOREIGN KEY (paciente_id) REFERENCES pacientes (id) ON DELETE CASCADE,
  CONSTRAINT evolucoes_ibfk_2
    FOREIGN KEY (sessao_id) REFERENCES sessoes (id) ON DELETE SET NULL,
  CONSTRAINT evolucoes_ibfk_3
    FOREIGN KEY (assinado_por_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- conferencia — esperado: as 5 tabelas novas
SELECT TABLE_NAME
  FROM INFORMATION_SCHEMA.TABLES
 WHERE TABLE_NAME IN ('planos_terapeuticos','objetivos_terapeuticos','sessoes',
                      'registros_tentativa','evolucoes')
 ORDER BY TABLE_NAME;

-- ============================================================================
-- Fim da 012. Proximo: models SQLAlchemy (clinica_terapia.py) + API do
-- Modulo 1 (CRUD PTI/sessao + evolucao com rascunho de IA e assinatura).
-- ============================================================================
