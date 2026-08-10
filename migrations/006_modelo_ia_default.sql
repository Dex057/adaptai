-- ============================================================================
--  006 — remove o ID de modelo aposentado do default de configuracoes_escola
--
--  Contexto: a coluna nasceu (migrations/multitenant_migration.sql:127) com
--
--      modelo_ia_preferido VARCHAR(100) DEFAULT 'claude-3-haiku-20240307'
--
--  Esse modelo foi aposentado pela Anthropic em 20/04/2026. Como planos.py e
--  seed_demo.py criam ConfiguracaoEscola SEM passar o campo, toda escola nova
--  continuava recebendo o ID aposentado — no default do Python (models/escola.py),
--  no default do Pydantic (schemas/escola.py) e no DEFAULT do proprio banco.
--
--  Risco de aplicar: baixo. A coluna e escrita mas NUNCA lida — conferido nos
--  103 arquivos .py do repositorio, nenhum caminho seleciona modelo a partir
--  dela. NULL passa a significar "usa o modelo padrao da aplicacao"
--  (settings.CLAUDE_MODEL), resolvido em runtime.
--
--  Aplicar JUNTO com o deploy que muda models/escola.py e schemas/escola.py —
--  os tres defaults tem que contar a mesma historia.
--
--  Desfazer:
--    ALTER TABLE configuracoes_escola
--      ALTER COLUMN modelo_ia_preferido SET DEFAULT 'claude-3-haiku-20240307';
-- ============================================================================

-- 1. o banco para de gravar o ID aposentado em toda linha nova
ALTER TABLE configuracoes_escola
  ALTER COLUMN modelo_ia_preferido DROP DEFAULT;

-- 2. limpa o que ja foi gravado (so os IDs aposentados; preferencia real de
--    alguma escola, se existir, fica intacta)
UPDATE configuracoes_escola
   SET modelo_ia_preferido = NULL
 WHERE modelo_ia_preferido IN ('claude-3-haiku-20240307',
                               'claude-3-5-sonnet-20241022');

-- 3. conferencia — esperado: 0 linhas
SELECT COUNT(*) AS ainda_com_modelo_aposentado
  FROM configuracoes_escola
 WHERE modelo_ia_preferido IN ('claude-3-haiku-20240307',
                               'claude-3-5-sonnet-20241022');
