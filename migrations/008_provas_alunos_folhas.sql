-- ============================================================================
--  008 — folhas de prova respondidas no papel (MODO PAPEL)
--
--  Contexto: nova feature "modo papel". O professor imprime a folha da prova
--  (GET /provas/aluno/{id}/folha-impressao), o aluno responde a mao, o professor
--  fotografa e envia (POST /provas/aluno/{id}/folha). O Claude Vision transcreve
--  o que foi marcado/escrito; o professor revisa e confirma
--  (POST /provas/aluno/{id}/folha/{folha_id}/confirmar), e a correcao reusa o
--  mesmo motor das provas online (grava em respostas_alunos e nota em
--  provas_alunos).
--
--  Esta tabela guarda CADA folha enviada: a imagem e a transcricao da IA. Ela
--  pendura na tentativa do aluno (provas_alunos), seguindo o padrao conteudo x
--  ponte do projeto — nenhuma posse nova fora da tentativa ja existente.
--
--  Espelha app/models/prova.py::ProvaAlunoFolha. O enum de status usa os NOMES
--  em maiusculo, como todo enum gerado pelo SQLAlchemy neste schema (ex.:
--  provas_alunos.status = enum('PENDENTE','EM_ANDAMENTO','CONCLUIDA','CORRIGIDA')).
--
--  Risco de aplicar: baixo. Tabela NOVA; nenhum SELECT/INSERT existente muda.
--  Idempotente (CREATE TABLE IF NOT EXISTS) — em dev o create_all ja pode ter
--  criado a tabela; em producao, rode esta migration antes/junto do deploy.
--
--  Desfazer:
--    DROP TABLE IF EXISTS provas_alunos_folhas;
-- ============================================================================

CREATE TABLE IF NOT EXISTS provas_alunos_folhas (
  id                     INT          NOT NULL AUTO_INCREMENT,
  prova_aluno_id         INT          NOT NULL,
  imagem_path            VARCHAR(500)                              DEFAULT NULL,
  transcricao_json       JSON                                     DEFAULT NULL,
  codigo_folha_detectado VARCHAR(50)                              DEFAULT NULL,
  status                 ENUM('TRANSCRITA','CONFIRMADA','ERRO')   DEFAULT NULL,
  criado_por_id          INT                                      DEFAULT NULL,
  criado_em              DATETIME                                 DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_provas_alunos_folhas_id (id),
  KEY ix_provas_alunos_folhas_prova_aluno (prova_aluno_id),
  CONSTRAINT provas_alunos_folhas_ibfk_1
    FOREIGN KEY (prova_aluno_id) REFERENCES provas_alunos (id) ON DELETE CASCADE,
  CONSTRAINT provas_alunos_folhas_ibfk_2
    FOREIGN KEY (criado_por_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- conferencia — esperado: a tabela com as colunas acima
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
  FROM INFORMATION_SCHEMA.COLUMNS
 WHERE TABLE_NAME = 'provas_alunos_folhas'
 ORDER BY ORDINAL_POSITION;
