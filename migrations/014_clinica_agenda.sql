-- ============================================================================
--  014 — agenda de sessoes (vertical CLINICA)
--
--  Agenda propria da clinica: agendamentos de atendimento ligados a paciente +
--  profissional + especialidade. NAO reusa `agenda_professor` (vertical ESCOLA,
--  preso a students) para manter o isolamento entre verticais.
--
--  Ponte com o que ja existe: ao marcar um agendamento como REALIZADO, o app
--  cria uma `sessoes` (migration 012) e guarda o vinculo em `sessao_id` — assim
--  a agenda alimenta o fluxo sessao -> registro de tentativa -> evolucao.
--
--  Risco: baixo. Tabela NOVA. Idempotente. Pre-req: 011 (paciente/profissional)
--  e 012 (sessoes).
--
--  Desfazer:
--    DROP TABLE IF EXISTS agendamentos;
-- ============================================================================

CREATE TABLE IF NOT EXISTS agendamentos (
  id              INT                                       NOT NULL AUTO_INCREMENT,
  escola_id       INT                                       NOT NULL,
  paciente_id     INT                                       NOT NULL,
  profissional_id INT                                       NOT NULL,
  especialidade   ENUM('PSICOLOGIA_ABA','FONOAUDIOLOGIA','TERAPIA_OCUPACIONAL',
                       'PSICOPEDAGOGIA','FISIOTERAPIA','MUSICOTERAPIA','NUTRICAO',
                       'NEUROPEDIATRIA','OUTRO')            NOT NULL,
  inicio          DATETIME                                  NOT NULL,
  duracao_min     INT                                       DEFAULT 50,
  status          ENUM('AGENDADO','CONFIRMADO','REALIZADO','FALTA',
                       'CANCELADO','REMARCADO')             NOT NULL DEFAULT 'AGENDADO',
  local           VARCHAR(255)                              DEFAULT NULL,
  observacao      TEXT                                      DEFAULT NULL,
  sessao_id       INT                                       DEFAULT NULL,  -- criado ao REALIZAR
  criado_por_id   INT                                       DEFAULT NULL,
  criado_em       DATETIME                                  DEFAULT NULL,
  atualizado_em   DATETIME                                  DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_agend_escola_inicio (escola_id, inicio),
  KEY ix_agend_profissional (profissional_id, inicio),
  KEY ix_agend_paciente (paciente_id),
  CONSTRAINT agend_ibfk_1 FOREIGN KEY (paciente_id) REFERENCES pacientes (id) ON DELETE CASCADE,
  CONSTRAINT agend_ibfk_2 FOREIGN KEY (profissional_id) REFERENCES profissionais (id),
  CONSTRAINT agend_ibfk_3 FOREIGN KEY (sessao_id) REFERENCES sessoes (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- conferencia
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'agendamentos';

-- ============================================================================
-- Fim da 014.
-- ============================================================================
