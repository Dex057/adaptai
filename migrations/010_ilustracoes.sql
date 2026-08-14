-- ============================================================================
--  010 — ilustracoes de conteudo (apoio visual)
--
--  Contexto: nova feature "ilustrar conteudo". Materiais, questoes de prova e
--  temas de redacao passam a poder receber apoio visual de duas fontes:
--    - ARASAAC: pictogramas padronizados (gratuitos, licenca CC), ideais para
--      compreensao de alunos com TEA/TDAH. Guardamos apenas arasaac_id + a URL
--      estatica no CDN (a imagem NAO e copiada para o nosso storage).
--    - IA: ilustracao gerada por modelo de imagem (Flux via provedor). O arquivo
--      e salvo em backend/storage/ilustracoes/ e servido por rota protegida
--      (GET /ilustracoes/{id}/imagem). O prompt usado fica em prompt_ia (auditoria).
--
--  Propriedade (conteudo x ponte): a ilustracao pertence ao CONTEUDO
--  (contexto_tipo + contexto_id), nunca ao aluno — gerada uma vez, reaproveitada
--  por toda a turma. Referencia polimorfica leve (sem FK para o alvo) porque um
--  mesmo registro serve tres tabelas distintas; a validacao do vinculo (conteudo
--  existe e e do professor) acontece na camada de servico.
--
--  Espelha app/models/ilustracao.py::Ilustracao. Os enums usam os NOMES em
--  maiusculo, como todo enum gerado pelo SQLAlchemy neste schema.
--
--  Risco de aplicar: baixo. Tabela NOVA; nenhum SELECT/INSERT existente muda.
--  Idempotente (CREATE TABLE IF NOT EXISTS).
--
--  Desfazer:
--    DROP TABLE IF EXISTS ilustracoes;
-- ============================================================================

CREATE TABLE IF NOT EXISTS ilustracoes (
  id             INT                                       NOT NULL AUTO_INCREMENT,
  contexto_tipo  ENUM('MATERIAL','QUESTAO','REDACAO_TEMA') NOT NULL,
  contexto_id    INT                                       NOT NULL,
  fonte          ENUM('ARASAAC','IA')                      NOT NULL,
  status         ENUM('PENDENTE','PRONTA','ERRO')          NOT NULL DEFAULT 'PRONTA',
  descricao      VARCHAR(500)                              DEFAULT NULL,
  arasaac_id     INT                                       DEFAULT NULL,
  imagem_url     VARCHAR(1000)                             DEFAULT NULL,
  imagem_path    VARCHAR(500)                              DEFAULT NULL,
  prompt_ia      TEXT                                      DEFAULT NULL,
  criado_por_id  INT                                       DEFAULT NULL,
  criado_em      DATETIME                                  DEFAULT NULL,
  PRIMARY KEY (id),
  KEY ix_ilustracoes_id (id),
  KEY ix_ilustracoes_contexto (contexto_tipo, contexto_id),
  CONSTRAINT ilustracoes_ibfk_1
    FOREIGN KEY (criado_por_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- conferencia — esperado: a tabela com as colunas acima
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
  FROM INFORMATION_SCHEMA.COLUMNS
 WHERE TABLE_NAME = 'ilustracoes'
 ORDER BY ORDINAL_POSITION;
