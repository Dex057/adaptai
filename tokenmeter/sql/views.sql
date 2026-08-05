-- Views de leitura para BI (Metabase/Power BI/Tableau) sobre o banco central do tokenmeter.
--
-- Regra que estas views preservam do tokenmeter/query.py: tokens de modelos diferentes
-- usam tokenizadores diferentes (o mesmo texto conta tokens distintos). Somar tokens sem
-- quebrar por `model` produz um número sem sentido -- é um degrau de tokenizador disfarçado
-- de consumo. Por isso as views de token SEMPRE trazem `model` no agrupamento; só as views
-- de custo (cost_usd, que é USD e é comparável entre modelos) podem agregar cruzando modelo.
--
-- Rodar contra o banco central, com o mesmo table_prefix usado em tm.configure(table_prefix=...).
-- Se você usa prefixo, ajuste "usage_event"/"usage_event_tag" abaixo para "<prefix>usage_event" etc.

-- ---------------------------------------------------------------------------
-- v_usage_daily_by_model
-- Grão: dia x service x environment x feature x provider x model x status.
-- Uso: qualquer pergunta que envolva soma de tokens (input/output/cache/total).
-- Cobre "consumo de tokens do projeto Y na feature X".
CREATE OR REPLACE VIEW v_usage_daily_by_model AS
SELECT
    occurred_date,
    service,
    environment,
    feature,
    provider,
    model,
    model_family,
    status,
    COUNT(*)                    AS calls,
    SUM(input_tokens)           AS input_tokens,
    SUM(output_tokens)          AS output_tokens,
    SUM(cache_write_tokens)     AS cache_write_tokens,
    SUM(cache_read_tokens)      AS cache_read_tokens,
    SUM(total_tokens)           AS total_tokens,
    SUM(cost_usd)               AS cost_usd,
    SUM(priced)                 AS priced_calls
FROM usage_event
GROUP BY occurred_date, service, environment, feature, provider, model, model_family, status;

-- ---------------------------------------------------------------------------
-- v_usage_daily_cost
-- Grão: dia x service x environment x feature x provider x status (SEM model).
-- Uso: comparar custo em USD cruzando modelos/projetos livremente -- é a métrica que
-- atravessa troca de modelo sem perder sentido. Cobre "custo do projeto Y" agregado.
CREATE OR REPLACE VIEW v_usage_daily_cost AS
SELECT
    occurred_date,
    service,
    environment,
    feature,
    provider,
    status,
    COUNT(*)          AS calls,
    SUM(cost_usd)     AS cost_usd,
    SUM(priced)       AS priced_calls
FROM usage_event
GROUP BY occurred_date, service, environment, feature, provider, status;

-- ---------------------------------------------------------------------------
-- v_usage_tag_values
-- Grão: 1 linha por (evento, tag). Formato longo (EAV), não agregado.
-- Uso: filtrar/agrupar por qualquer dimensão livre (student_id, turma_id, entity_id, ...)
-- sem precisar prever a coluna com antecedência. No Metabase, filtre por tag_key = 'x'
-- e agrupe por tag_value.
CREATE OR REPLACE VIEW v_usage_tag_values AS
SELECT
    e.event_id,
    e.occurred_date,
    e.service,
    e.environment,
    e.feature,
    e.provider,
    e.model,
    e.status,
    e.cost_usd,
    e.total_tokens,
    t.tag_key,
    t.tag_value
FROM usage_event e
JOIN usage_event_tag t ON t.event_id = e.event_id;

-- ---------------------------------------------------------------------------
-- v_usage_coverage
-- Termômetro de qualidade de atribuição (espelha tokenmeter.coverage()).
-- Uso: acompanhar % de chamadas com feature explícita por projeto -- sinaliza quando um
-- projeto novo ainda não instrumentou feature/tags corretamente.
CREATE OR REPLACE VIEW v_usage_coverage AS
SELECT
    service,
    feature_source,
    COUNT(*) AS calls
FROM usage_event
GROUP BY service, feature_source;
