-- ============================================================================
--  011 — nucleo clinico (Fase 0: fundacao da arquitetura modular)
--
--  Contexto: o ADAPT AI passa a ter um vertical CLINICA (gestao clinica
--  multidisciplinar para TEA) ao lado do vertical ESCOLA ja existente. Esta
--  migration crava a FUNDACAO que permite vender "so Clinica", "so Escola" ou
--  as duas juntas, e cria as entidades-ancora do prontuario.
--
--  O tenant continua sendo `escolas` (tabela multi-tenant existente). Uma
--  clinica e um tenant de `escolas.tipo = 'CLINICA'`. Nao criamos tabela de
--  tenant nova — reaproveitamos a que ja existe.
--
--  Entitlement (vender separado/junto): `escola_modulos` diz quais modulos o
--  tenant tem ativos. E a camada acima do plano/assinatura e do features.py
--  (que sao toggles finos DENTRO de um modulo). Espelha app/core/entitlements.py.
--
--  Ponte "equipe do caso x paciente" (`equipe_caso`): evolucao do padrao
--  posse x atribuicao (professor dono x aluno atribuido) para o mundo
--  multidisciplinar — varios profissionais acessam o mesmo prontuario.
--
--  LGPD: `consentimentos` guarda o aceite do responsavel (dado sensivel de
--  saude, art. 11). `vinculo_aluno_paciente` e OPCIONAL — so faz sentido quando
--  ESCOLA e CLINICA coexistem no mesmo tenant; a clinica standalone nao a usa.
--
--  NAO entra aqui (vai na 012 — Modulo 1 do MVP): plano_terapeutico, objetivo/
--  meta, sessao, evolucao, registro de tentativa.
--
--  Risco de aplicar: baixo. Todas as tabelas sao NOVAS; nenhum SELECT/INSERT
--  existente muda. Idempotente (CREATE TABLE IF NOT EXISTS).
--
--  Desfazer:
--    DROP TABLE IF EXISTS auditoria_acesso;
--    DROP TABLE IF EXISTS vinculo_aluno_paciente;
--    DROP TABLE IF EXISTS consentimentos;
--    DROP TABLE IF EXISTS equipe_caso;
--    DROP TABLE IF EXISTS pacientes;
--    DROP TABLE IF EXISTS profissionais;
--    DROP TABLE IF EXISTS escola_modulos;
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1) ENTITLEMENTS — quais modulos cada tenant (escola) tem ativos.
--    E o que permite vender "so Clinica", "so Escola" ou junto.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS escola_modulos (
  id             INT                                        NOT NULL AUTO_INCREMENT,
  escola_id      INT                                        NOT NULL,
  modulo         ENUM('ESCOLA','CLINICA','INTELIGENCIA')    NOT NULL,
  ativo          TINYINT(1)                                 NOT NULL DEFAULT 1,
  ativado_em     DATETIME                                   DEFAULT NULL,
  desativado_em  DATETIME                                   DEFAULT NULL,
  observacao     VARCHAR(500)                               DEFAULT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY ux_escola_modulo (escola_id, modulo),
  KEY ix_escola_modulos_escola (escola_id),
  CONSTRAINT escola_modulos_ibfk_1
    FOREIGN KEY (escola_id) REFERENCES escolas (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Seed: todo tenant existente ja opera o vertical ESCOLA (nao quebra nada).
INSERT INTO escola_modulos (escola_id, modulo, ativo, ativado_em)
SELECT e.id, 'ESCOLA', 1, NOW()
  FROM escolas e
  LEFT JOIN escola_modulos em
    ON em.escola_id = e.id AND em.modulo = 'ESCOLA'
 WHERE em.id IS NULL;

-- ----------------------------------------------------------------------------
-- 2) PROFISSIONAL — o terapeuta: liga um usuario ao tenant + especialidade.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS profissionais (
  id              INT                                       NOT NULL AUTO_INCREMENT,
  escola_id       INT                                       NOT NULL,
  usuario_id      INT                                       NOT NULL,
  nome            VARCHAR(255)                              NOT NULL,
  especialidade   ENUM('PSICOLOGIA_ABA','FONOAUDIOLOGIA','TERAPIA_OCUPACIONAL',
                       'PSICOPEDAGOGIA','FISIOTERAPIA','MUSICOTERAPIA','NUTRICAO',
                       'NEUROPEDIATRIA','OUTRO')            NOT NULL,
  conselho_tipo   ENUM('CRP','CFFA','CREFITO','CRM','CRN','CREF','OUTRO')
                                                            DEFAULT NULL,
  conselho_numero VARCHAR(50)                               DEFAULT NULL,
  papel           ENUM('ADMIN_CLINICA','RESPONSAVEL_TECNICO','COORDENADOR',
                       'SUPERVISOR','APLICADOR','TERAPEUTA')
                                                            NOT NULL DEFAULT 'TERAPEUTA',
  ativo           TINYINT(1)                                NOT NULL DEFAULT 1,
  criado_em       DATETIME                                  DEFAULT NULL,
  atualizado_em   DATETIME                                  DEFAULT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY ux_prof_escola_usuario (escola_id, usuario_id),
  KEY ix_profissionais_escola (escola_id),
  CONSTRAINT profissionais_ibfk_1
    FOREIGN KEY (escola_id) REFERENCES escolas (id) ON DELETE CASCADE,
  CONSTRAINT profissionais_ibfk_2
    FOREIGN KEY (usuario_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 3) PACIENTE — titular do prontuario. DADO SENSIVEL DE SAUDE (LGPD art. 11).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pacientes (
  id                  INT                                   NOT NULL AUTO_INCREMENT,
  escola_id           INT                                   NOT NULL,
  nome                VARCHAR(255)                          NOT NULL,
  data_nascimento     DATE                                  DEFAULT NULL,
  responsavel_nome    VARCHAR(255)                          DEFAULT NULL,
  responsavel_contato VARCHAR(100)                          DEFAULT NULL,
  status              ENUM('EM_AVALIACAO','ATIVO','INATIVO','ALTA')
                                                            NOT NULL DEFAULT 'EM_AVALIACAO',
  -- Token read-only para o Portal da Familia (espelha o studentToken).
  token_familia       VARCHAR(64)                           DEFAULT NULL,
  criado_em           DATETIME                              DEFAULT NULL,
  atualizado_em       DATETIME                              DEFAULT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY ux_pacientes_token_familia (token_familia),
  KEY ix_pacientes_escola (escola_id),
  CONSTRAINT pacientes_ibfk_1
    FOREIGN KEY (escola_id) REFERENCES escolas (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 4) EQUIPE DO CASO — a ponte "equipe do caso x paciente".
--    O guard de acesso clinico valida pertencimento AQUI (nao posse).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS equipe_caso (
  id              INT                                       NOT NULL AUTO_INCREMENT,
  escola_id       INT                                       NOT NULL,
  paciente_id     INT                                       NOT NULL,
  profissional_id INT                                       NOT NULL,
  papel_no_caso   ENUM('RESPONSAVEL','COTERAPEUTA','SUPERVISOR','OBSERVADOR')
                                                            NOT NULL DEFAULT 'COTERAPEUTA',
  ativo           TINYINT(1)                                NOT NULL DEFAULT 1,
  criado_em       DATETIME                                  DEFAULT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY ux_equipe_caso (paciente_id, profissional_id),
  KEY ix_equipe_caso_profissional (profissional_id),
  KEY ix_equipe_caso_paciente (paciente_id),
  CONSTRAINT equipe_caso_ibfk_1
    FOREIGN KEY (paciente_id) REFERENCES pacientes (id) ON DELETE CASCADE,
  CONSTRAINT equipe_caso_ibfk_2
    FOREIGN KEY (profissional_id) REFERENCES profissionais (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 5) CONSENTIMENTO — LGPD na fundacao (dado sensivel de saude, art. 11).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS consentimentos (
  id             INT                                        NOT NULL AUTO_INCREMENT,
  escola_id      INT                                        NOT NULL,
  paciente_id    INT                                        NOT NULL,
  tipo           ENUM('TRATAMENTO_DADOS','USO_IMAGEM',
                      'COMPARTILHA_ESCOLA','COMPARTILHA_CONVENIO')  NOT NULL,
  versao_texto   VARCHAR(100)                               NOT NULL,
  concedido_por  VARCHAR(255)                               NOT NULL,
  concedido_em   DATETIME                                   DEFAULT NULL,
  revogado_em    DATETIME                                   DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_consentimentos_paciente (paciente_id),
  CONSTRAINT consentimentos_ibfk_1
    FOREIGN KEY (paciente_id) REFERENCES pacientes (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 6) VINCULO OPCIONAL Aluno x Paciente.
--    So faz sentido quando ESCOLA e CLINICA coexistem no mesmo tenant.
--    Vinculo LEVE (nao fusao): a clinica standalone nunca usa esta tabela.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vinculo_aluno_paciente (
  id           INT                                          NOT NULL AUTO_INCREMENT,
  escola_id    INT                                          NOT NULL,
  aluno_id     INT                                          NOT NULL,
  paciente_id  INT                                          NOT NULL,
  criado_em    DATETIME                                     DEFAULT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY ux_vinculo_aluno_paciente (aluno_id, paciente_id),
  KEY ix_vinculo_ap_escola (escola_id),
  KEY ix_vinculo_ap_paciente (paciente_id),
  CONSTRAINT vinculo_ap_ibfk_1
    FOREIGN KEY (aluno_id) REFERENCES students (id) ON DELETE CASCADE,
  CONSTRAINT vinculo_ap_ibfk_2
    FOREIGN KEY (paciente_id) REFERENCES pacientes (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 7) AUDITORIA DE ACESSO — trilha de quem acessou qual prontuario e quando.
--    Exigencia pratica de prontuario (dado sensivel de saude). Sem FK em
--    usuario_id de proposito: a trilha deve sobreviver a remocao do usuario.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS auditoria_acesso (
  id           INT                                          NOT NULL AUTO_INCREMENT,
  escola_id    INT                                          NOT NULL,
  usuario_id   INT                                          DEFAULT NULL,
  paciente_id  INT                                          NOT NULL,
  acao         ENUM('VISUALIZAR','CRIAR','EDITAR','EXPORTAR','IMPRIMIR')  NOT NULL,
  recurso      VARCHAR(100)                                 DEFAULT NULL,
  recurso_id   INT                                          DEFAULT NULL,
  ip           VARCHAR(45)                                  DEFAULT NULL,
  criado_em    DATETIME                                     DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_auditoria_paciente (paciente_id),
  KEY ix_auditoria_escola_data (escola_id, criado_em),
  CONSTRAINT auditoria_acesso_ibfk_1
    FOREIGN KEY (paciente_id) REFERENCES pacientes (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- conferencia — esperado: as 7 tabelas novas
SELECT TABLE_NAME
  FROM INFORMATION_SCHEMA.TABLES
 WHERE TABLE_NAME IN ('escola_modulos','profissionais','pacientes',
                      'equipe_caso','consentimentos','vinculo_aluno_paciente',
                      'auditoria_acesso')
 ORDER BY TABLE_NAME;

-- ============================================================================
-- Fim da 011. Proxima: 012_clinica_pti_sessao.sql (PTI, objetivo/meta, sessao,
-- evolucao) — Modulo 1 do MVP.
-- ============================================================================
