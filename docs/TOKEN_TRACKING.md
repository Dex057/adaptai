# 📊 Contador de Consumo de Tokens (Claude) - AdaptAI

## Resumo

Nenhuma das features que chamam a IA Claude (PEI, jornada terapêutica,
planejamento diário/anual, análise qualitativa, prova de reforço) registrava
quantos tokens cada requisição consumia - o `usage` devolvido pela própria
API era descartado. Este documento descreve o contador implementado: o que
foi criado/alterado, como consultar, o que falta rodar em produção, e como
validar tudo em ambiente local.

---

## 1. 🧮 Como funciona

A contagem **não é estimada** - vem direto de `response.usage`, o objeto que
a API da Anthropic devolve em toda chamada `messages.create(...)` (contém
`input_tokens`, `output_tokens` e, quando prompt caching está em uso,
`cache_creation_input_tokens`/`cache_read_input_tokens`). Depois de cada
chamada nas 5 features, o código passa esse objeto para um helper central que:

1. **Loga** em JSON estruturado (via `app/core/logging_config.py`, já usado
   no projeto - em produção vira log pesquisável no Datadog/Logtail).
2. **Persiste** uma linha na tabela `ai_usage_log`, em uma sessão de banco
   própria e isolada (não a mesma sessão da rota) - assim, se a geração da IA
   falhar depois (ex.: erro ao parsear o JSON de resposta), o registro de uso
   não é perdido junto: os tokens já foram consumidos e cobrados pela
   Anthropic independente do que acontece depois na aplicação.
3. **Estima o custo em USD** a partir de uma tabela de preço por modelo
   (`PRECOS_USD_POR_MTOK`). Se o modelo usado não estiver na tabela, o custo
   fica `NULL` em vez de mostrar um valor errado.

**Arquivos novos:**
- `app/models/ai_usage_log.py` - modelo SQLAlchemy da tabela `ai_usage_log`.
- `app/core/ai_usage.py` - `registrar_uso_ia()` (grava) e `calcular_custo_usd()`
  (tabela de preço + cálculo).
- `migrations/005_ai_usage_log.sql` - `CREATE TABLE` (mesmo padrão dos SQLs
  legados já existentes em `migrations/`).

**Arquivos alterados** (uma chamada a `registrar_uso_ia(...)` logo após o
`messages.create(...)` já existente, sem mudar o comportamento da feature):

| Feature | Arquivo | `feature` gravado |
|---|---|---|
| PEI - análise de laudo | `app/api/routes/pei.py` | `pei_analise_laudo` |
| PEI - geração a partir de relatórios | `app/api/routes/pei.py` | `pei_geracao` |
| Jornada terapêutica | `app/api/routes/relatorios_analise.py` | `jornada_terapeutica` |
| Planejamento anual | `app/services/planejamento_bncc_service.py` | `planejamento_anual` |
| Planejamento por trimestre | `app/services/planejamento_bncc_service.py` | `planejamento_trimestre` |
| Planejamento anual completo (lotes) | `app/services/planejamento_bncc_completo_service.py` | `planejamento_anual_completo` |
| Análise qualitativa | `app/services/analise_qualitativa_service.py` | `analise_qualitativa` |
| Prova de reforço | `app/services/prova_adaptativa_service.py` | `prova_reforco` |

---

## 2. 📋 Colunas de `ai_usage_log`

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | INT PK | - |
| `feature` | VARCHAR(50) | Qual funcionalidade originou a chamada (ver tabela acima) |
| `model` | VARCHAR(100) | Modelo Claude usado nessa chamada específica |
| `input_tokens` / `output_tokens` | INT | Contagem exata (`response.usage`) |
| `cache_creation_input_tokens` / `cache_read_input_tokens` | INT | Prompt caching (0 se não usado) |
| `cost_usd` | DECIMAL(12,6) | Estimativa em USD; `NULL` se o modelo não está na tabela de preço |
| `student_id`, `user_id`, `escola_id` | INT (nullable, sem FK) | Atribuição opcional - tabela de log/telemetria, não deve travar nem ser afetada por exclusão de registros de domínio |
| `created_at` | DATETIME | - |

Consulta de exemplo (consumo por feature no mês):

```sql
SELECT feature, model,
       SUM(input_tokens + output_tokens) AS tokens,
       SUM(cost_usd)                     AS custo_usd,
       COUNT(*)                          AS chamadas
FROM ai_usage_log
WHERE created_at >= '2026-07-01'
GROUP BY feature, model
ORDER BY custo_usd DESC;
```

---

## 3. 🚀 O que falta rodar em produção

Isto **não foi executado** - mexe no banco de produção.

1. **Aplicar a migração SQL.** O Alembic ainda não tem baseline adotado neste
   projeto (`alembic/versions/` vazio, ver `alembic/README_ADOCAO.md`), então
   o mecanismo atual para produção é o mesmo dos SQLs legados: rodar
   `migrations/005_ai_usage_log.sql` diretamente no MySQL de produção (mesmo
   fluxo usado para `004_analises_qualitativas.sql` etc.). É `CREATE TABLE IF
   NOT EXISTS` - idempotente, não afeta tabelas existentes.
2. **Nenhuma variável de ambiente nova é necessária.** O contador reusa
   `ANTHROPIC_API_KEY`/`DATABASE_URL` (ou `MYSQL_*`) que já precisam estar
   configuradas no Railway para o resto da aplicação funcionar.
3. **Deploy do código** (rotas/services alterados) normalmente.

Não há ordem estrita entre 1 e 3: se o código subir antes da tabela existir,
`registrar_uso_ia()` **não derruba a feature** - ele captura a exceção
internamente, loga `"Falha ao registrar uso de tokens da IA"` e a resposta da
IA para o usuário segue normalmente. Ainda assim, o ideal é aplicar o SQL
antes do deploy para não perder registros nesse intervalo.

---

## 4. 🧪 Simulação em ambiente local - já validada

Sim, é possível simular localmente, e a parte estrutural (tabela, gravação,
cálculo de custo, log) **já foi testada nesta sessão** contra o MySQL local
configurado no seu `.env` (`localhost:3306/adaptai`), sem gastar nenhum
token real:

```python
from app.database import engine, SessionLocal
from app.models.ai_usage_log import AIUsageLog
from app.core.ai_usage import registrar_uso_ia
from types import SimpleNamespace

# cria a tabela se ainda nao existir (idempotente)
AIUsageLog.__table__.create(bind=engine, checkfirst=True)

# usage "falso" - mesmo formato que a API da Anthropic devolveria
usage_fake = SimpleNamespace(
    input_tokens=1200, output_tokens=430,
    cache_creation_input_tokens=0, cache_read_input_tokens=0,
)
registrar_uso_ia(feature="teste_simulacao_local", model="claude-sonnet-4-6", usage=usage_fake)
```

Resultado real desse teste (linha gravada e depois removida, para não sujar
o banco):

```
id=1 feature=teste_simulacao_local model=claude-sonnet-4-6
input=1200 output=430 cost_usd=0.010050
```

Custo bate com a conta manual: `1200/1e6 * $3 + 430/1e6 * $15 = $0.01005`. ✅

**O que essa simulação PROVA:** o modelo, a gravação no banco, o log
estruturado e o cálculo de custo funcionam corretamente.

**O que essa simulação NÃO prova** (e você já havia antecipado): os números
de `input_tokens`/`output_tokens` de uma chamada real - esses só existem
depois de uma chamada de verdade à API oficial da Anthropic, com uma
`ANTHROPIC_API_KEY` real. Não tem como "simular" quantos tokens o Claude vai
efetivamente processar sem de fato mandar o prompt pra ele.

### Como validar ponta a ponta com uma chamada real (mais barata possível)

Para não gastar muito, use o modelo Haiku (mais barato) direto, sem passar
pelas rotas completas de PEI/jornada/planejamento:

```python
from app.core.anthropic_client import get_anthropic_client, get_fast_model
from app.core.ai_usage import registrar_uso_ia

client = get_anthropic_client()  # precisa de ANTHROPIC_API_KEY real no .env
message = client.messages.create(
    model=get_fast_model(),
    max_tokens=50,
    messages=[{"role": "user", "content": "Responda apenas: ok"}],
)
registrar_uso_ia(feature="teste_validacao_real", model=get_fast_model(), usage=message.usage)
print(message.usage)
```

Depois é só consultar `SELECT * FROM ai_usage_log WHERE feature =
'teste_validacao_real'` para ver a linha com os tokens reais. Isso custa
frações de centavo (poucas dezenas de tokens no Haiku).

Para validar de fato uma das 5 features (não só a chamada crua), o caminho é
rodar o backend local (`uvicorn app.main:app --reload`) e disparar uma
requisição real para, por exemplo, `POST /pei/gerar-pei-de-relatorios` - só
funciona com `ANTHROPIC_API_KEY` real configurada (seção 5).

---

## 5. 🔧 Configuração do `.env` - itens encontrados

Revisei seu `.env` e `.env.example` atuais. Três pontos precisam de atenção
antes de qualquer teste com chamada real:

### 5.1 `ANTHROPIC_API_KEY` ainda é o placeholder

Seu `.env` atual tem:
```
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```
Isso é o texto de exemplo, não uma chave real - qualquer chamada à IA vai
falhar com erro de autenticação. Troque pela sua chave real de
https://console.anthropic.com/ (Settings → API Keys). Ela começa com
`sk-ant-api03-` seguido de um token longo, não de `x`.

### 5.2 `CLAUDE_MODEL` está travando no modelo antigo/depreciado

Seu `.env` tem:
```
CLAUDE_MODEL=claude-sonnet-4-20250514
```
Esse é justamente o modelo que a correção da commit `f481e13` (trocar
modelos aposentados) tentou deixar de usar como *default* - mas
`get_default_model()` (`app/core/anthropic_client.py`) é:
```python
return settings.CLAUDE_MODEL or "claude-sonnet-4-6"
```
Ou seja: como `CLAUDE_MODEL` **está definido** no seu `.env`, ele **sobrescreve**
o fallback atualizado e todas as 5 features continuam usando o modelo
depreciado (deprecated, ainda sem data de retirement definida - mas não é
o comportamento que a correção pretendia). Duas opções:
- Apagar a linha `CLAUDE_MODEL=...` do `.env` → deixa o código usar o
  fallback `claude-sonnet-4-6` automaticamente; ou
- Trocar o valor para `CLAUDE_MODEL=claude-sonnet-4-6` explicitamente.

### 5.3 ⚠️ `.env.example` está com uma senha real de banco commitável

Isso é o mais importante: `.env.example` (arquivo que normalmente **é**
versionado no git, ao contrário do `.env`, que está no `.gitignore`) foi
editado e agora contém, em texto puro:
```
DB_USER=davi
DB_PASSWORD=Edmartins057@
```
em vez dos placeholders originais (`seu_usuario` / `sua_senha`). Isso ainda
não foi commitado (`git status` mostra `.env.example` como modificado, não
staged), mas se for commitado/pushado, a senha do seu MySQL fica pública no
histórico do repositório. Recomendo reverter para placeholders antes de
commitar - posso fazer essa edição se quiser, é só confirmar.

Aproveitando: `.env.example` também usa nomes de variável que o
`app/core/config.py` **não lê** (`DB_HOST`, `DB_USER`, `DB_PASSWORD`,
`DB_NAME`, `CORS_ORIGINS`) - o `Settings` real espera `MYSQL_HOST`,
`MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`, `BACKEND_CORS_ORIGINS`
(que é o que seu `.env` real já usa corretamente). Isso é um problema
separado do contador de tokens, mas vale corrigir no `.env.example` para não
confundir o próximo dev que copiar o template.

### 5.4 Checklist rápido para rodar a validação real da seção 4

- [ ] Confirmar que o MySQL local está acessível (já testei nesta sessão: ✅ está)
- [ ] Trocar `ANTHROPIC_API_KEY` pela chave real (5.1)
- [ ] Remover ou corrigir `CLAUDE_MODEL` (5.2)
- [ ] Rodar o snippet da seção 4 ("validar ponta a ponta")
- [ ] Conferir a linha em `ai_usage_log`

---

## 6. 🧭 Fora do escopo (identificado, não alterado)

- `app/services/material_service.py` já calcula `tokens_used`, mas só devolve
  no corpo da resposta HTTP (não persiste) e ainda usa modelo hardcoded
  `claude-3-5-sonnet-20241022` em vez de `get_default_model()`.
- `scripts/testar_tokens.py` é um script de diagnóstico solto, desconectado
  do contador novo.

Ambos podem ser alinhados ao mesmo padrão se fizer sentido depois.
