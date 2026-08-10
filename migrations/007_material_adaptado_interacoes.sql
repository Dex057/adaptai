-- ============================================================================
--  007 — interacoes do aluno no material adaptado gerado (TC-033/123/124)
--
--  Contexto: a rodada anterior criou a ponte de LEITURA
--  (GET /student/materiais-adaptados/), e o TC-027 passou a funcionar: o aluno
--  ve e abre o que o professor gerou. Favoritar, marcar como lido e anotar,
--  porem, continuaram sem efeito — essas colunas existem em `materiais_alunos`
--  (outro pipeline, alimentado por POST /materiais/), e o material gerado pela
--  tela "Criar com IA" nunca passa por la. Nao havia onde gravar.
--
--  Esta migration adiciona as quatro colunas na propria tabela do material
--  gerado, com os MESMOS nomes usados em `materiais_alunos` para o frontend
--  reaproveitar o componente:
--    - favorito         INT 0/1  (igual materiais_alunos.favorito)
--    - lido             INT 0/1
--    - lido_em          DATETIME
--    - anotacoes_aluno  TEXT     (igual materiais_alunos.anotacoes_aluno)
--
--  Risco de aplicar: baixo. Sao colunas NOVAS, todas nullable/com default 0.
--  Nenhum SELECT existente quebra, nenhum INSERT existente precisa mudar, e as
--  linhas ja gravadas assumem "nao favoritado / nao lido / sem anotacao", que e
--  exatamente o estado real delas hoje.
--
--  Aplicar JUNTO com o deploy que muda app/models/material_adaptado_gerado.py.
--  Se o codigo subir sem a migration, os endpoints novos respondem 500
--  (coluna inexistente) e a LISTAGEM/DETALHE tambem quebram, porque passam a
--  ler os campos. Ordem correta: migration primeiro, deploy depois.
--
--  Desfazer:
--    ALTER TABLE materiais_adaptados_gerados
--      DROP COLUMN favorito,
--      DROP COLUMN lido,
--      DROP COLUMN lido_em,
--      DROP COLUMN anotacoes_aluno;
-- ============================================================================

ALTER TABLE materiais_adaptados_gerados
  ADD COLUMN favorito        INT      NOT NULL DEFAULT 0,
  ADD COLUMN lido            INT      NOT NULL DEFAULT 0,
  ADD COLUMN lido_em         DATETIME NULL,
  ADD COLUMN anotacoes_aluno TEXT     NULL;

-- Consulta "meus favoritos" filtra por aluno + favorito. Sem o indice composto
-- vira full scan da tabela do aluno a cada abertura do Portal.
CREATE INDEX ix_mag_student_favorito
  ON materiais_adaptados_gerados (student_id, favorito);

-- conferencia — esperado: as 4 colunas listadas
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
  FROM INFORMATION_SCHEMA.COLUMNS
 WHERE TABLE_NAME = 'materiais_adaptados_gerados'
   AND COLUMN_NAME IN ('favorito', 'lido', 'lido_em', 'anotacoes_aluno');
