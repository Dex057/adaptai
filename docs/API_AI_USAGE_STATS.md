# 📡 API - Estatísticas de Consumo de Tokens da IA

Referência de uso do endpoint que devolve o consumo de tokens/custo do Claude,
agregado por feature e por modelo. Implementação: `app/api/routes/admin_monitoring.py`.
Fonte dos dados: tabela `ai_usage_log`, gravada por `app/core/ai_usage.registrar_uso_ia()`
após cada chamada real a Claude em PEI, jornada terapêutica, planejamento, análise
qualitativa e prova de reforço.

---

## 1. Endpoint

```
GET /api/v1/admin/ai-usage/stats
```

| | |
|---|---|
| **Auth** | Bearer token (JWT), obrigatório |
| **Permissão** | `ADMIN` ou `SUPER_ADMIN` (via `require_admin`) — qualquer outra role recebe `403` |

### Query params (todos opcionais, combináveis)

| Param | Tipo | Efeito |
|---|---|---|
| `dias` | int | Filtra chamadas dos últimos N dias (default `30`) |
| `feature` | string | Filtra só uma funcionalidade — valores possíveis: `pei_analise_laudo`, `pei_geracao`, `jornada_terapeutica`, `planejamento_anual`, `planejamento_trimestre`, `planejamento_anual_completo`, `analise_qualitativa`, `prova_reforco` |
| `user_id` | int | Filtra só chamadas atribuídas a esse usuário (professor/admin logado que disparou a ação) |
| `student_id` | int | Filtra só chamadas relacionadas a esse aluno |

**Nem toda chamada grava `user_id`/`student_id`** — depende de cada feature ter informado isso ao chamar `registrar_uso_ia(...)`:

| Feature | Grava `user_id` | Grava `student_id` |
|---|---|---|
| `pei_analise_laudo`, `pei_geracao` | ✅ | ✅ (só `pei_geracao`) |
| `jornada_terapeutica` | ✅ | ✅ |
| `planejamento_anual` | ✅ | ✅ |
| `planejamento_trimestre` | ❌ | ✅ |
| `planejamento_anual_completo` | ❌ | ❌ |
| `analise_qualitativa`, `prova_reforco` | ❌ | ❌ |

Filtrar por `user_id`/`student_id` numa feature que não grava esse campo simplesmente devolve zero resultados — não é erro, é ausência de dado.

---

## 2. Como chamar

### Opção A — pelo Swagger (`/docs`), sem escrever código

O projeto usa `OAuth2PasswordBearer` (`app/api/dependencies.py`), então o botão "Authorize"
já faz o login por você — não precisa chamar `/login` manualmente nem copiar token.

1. Abra `https://<seu-backend>/docs` (local: `http://localhost:8000/docs`).
2. Clique em **"Authorize"** (cadeado, topo da página).
3. No formulário que abre, preencha `username` com o e-mail de uma conta `ADMIN`/`SUPER_ADMIN`
   e `password` com a senha (deixe `client_id`/`client_secret` em branco) → **"Authorize"**.
   O Swagger chama `POST /api/v1/auth/login` por baixo dos panos e já anexa o token em toda
   chamada seguinte.
4. Feche o popup, ache `GET /api/v1/admin/ai-usage/stats` na lista, clique em **"Try it out"**
   → preencha `dias` (opcional) → **"Execute"**.

**Se precisar do token fora do Swagger** (ex. pra usar em `curl`): chame
`POST /api/v1/auth/login/json` (aceita JSON — mais fácil de preencher à mão que o `/login`,
que espera form) com `{"email": "...", "password": "..."}`, e copie o campo `access_token`
da resposta (`{"access_token": "eyJ...", "token_type": "bearer", "refresh_token": "eyJ..."}`).

### Opção B — `curl`

```bash
curl -H "Authorization: Bearer SEU_TOKEN_AQUI" \
  "https://<seu-backend>/api/v1/admin/ai-usage/stats?dias=30"
```

### Opção C — JavaScript (ex. dentro do próprio frontend, se quiser expor numa tela admin)

```javascript
const resp = await fetch("/api/v1/admin/ai-usage/stats?dias=30", {
  headers: { Authorization: `Bearer ${token}` },
});
const dados = await resp.json();
```

---

## 3. Exemplos de uso com filtros

Casos de uso reais, combinando os query params. Todos testados localmente (dados simulados).

**"Quanto a jornada terapêutica custou pro usuário 42 nos últimos 90 dias?"**
```
GET /api/v1/admin/ai-usage/stats?feature=jornada_terapeutica&user_id=42&dias=90
```

**"Quanto qualquer feature de IA custou pro usuário 42 no total?"** (sem filtrar feature)
```
GET /api/v1/admin/ai-usage/stats?user_id=42&dias=90
```

**"Quanto custou o PEI (geração) desse aluno específico, desde sempre?"** (`dias` bem alto cobre "desde sempre")
```
GET /api/v1/admin/ai-usage/stats?feature=pei_geracao&student_id=7&dias=3650
```

**"Quanto a análise qualitativa custou no total essa semana?"** (`analise_qualitativa` não grava `user_id`/`student_id` — só dá pra ver o agregado geral, ver tabela acima)
```
GET /api/v1/admin/ai-usage/stats?feature=analise_qualitativa&dias=7
```

Exemplo de `curl` para o primeiro caso:
```bash
curl -H "Authorization: Bearer SEU_TOKEN_AQUI" \
  "https://<seu-backend>/api/v1/admin/ai-usage/stats?feature=jornada_terapeutica&user_id=42&dias=90"
```

Resposta real desse caso (validada localmente — 2 chamadas de jornada terapêutica do usuário 42, isoladas de uma 3ª chamada de PEI do mesmo usuário e de uma chamada de outro usuário):
```json
{
  "periodo_dias": 90,
  "filtros": { "feature": "jornada_terapeutica", "user_id": 42, "student_id": null },
  "total": {
    "chamadas": 2,
    "input_tokens": 3500,
    "output_tokens": 1400,
    "custo_usd": 0.0315
  },
  "por_feature": [
    { "chamadas": 2, "input_tokens": 3500, "output_tokens": 1400, "custo_usd": 0.0315, "feature": "jornada_terapeutica" }
  ],
  "por_modelo": [
    { "chamadas": 2, "input_tokens": 3500, "output_tokens": 1400, "custo_usd": 0.0315, "model": "claude-sonnet-4-6" }
  ],
  "chamadas_recentes": [
    { "id": 7, "feature": "jornada_terapeutica", "model": "claude-sonnet-4-6", "input_tokens": 1500, "output_tokens": 600, "custo_usd": 0.0135, "student_id": 7, "user_id": 42, "escola_id": null, "created_at": "2026-07-30T16:31:34" },
    { "id": 6, "feature": "jornada_terapeutica", "model": "claude-sonnet-4-6", "input_tokens": 2000, "output_tokens": 800, "custo_usd": 0.018, "student_id": 7, "user_id": 42, "escola_id": null, "created_at": "2026-07-30T16:31:34" }
  ]
}
```
Com esse retorno já dá pra responder a pergunta direto: **2 chamadas, $0.0315 no total**, e ainda dá pra ver o custo de cada chamada individual em `chamadas_recentes` (a mais recente custou $0.0135).

---

## 4. Exemplo de retorno (sem filtros)

Resposta real (validada localmente com dados simulados — números só de exemplo):

```json
{
  "periodo_dias": 30,
  "filtros": { "feature": null, "user_id": null, "student_id": null },
  "total": {
    "chamadas": 4,
    "input_tokens": 7600,
    "output_tokens": 3000,
    "custo_usd": 0.0586
  },
  "por_feature": [
    {
      "chamadas": 2,
      "input_tokens": 6000,
      "output_tokens": 2400,
      "custo_usd": 0.054,
      "feature": "pei_geracao"
    },
    {
      "chamadas": 2,
      "input_tokens": 1600,
      "output_tokens": 600,
      "custo_usd": 0.0046,
      "feature": "analise_qualitativa"
    }
  ],
  "por_modelo": [
    {
      "chamadas": 2,
      "input_tokens": 6000,
      "output_tokens": 2400,
      "custo_usd": 0.054,
      "model": "claude-sonnet-4-6"
    },
    {
      "chamadas": 2,
      "input_tokens": 1600,
      "output_tokens": 600,
      "custo_usd": 0.0046,
      "model": "claude-haiku-4-5-20251001"
    }
  ],
  "chamadas_recentes": [
    {
      "id": 5,
      "feature": "analise_qualitativa",
      "model": "claude-haiku-4-5-20251001",
      "input_tokens": 800,
      "output_tokens": 300,
      "custo_usd": 0.0023,
      "student_id": null,
      "user_id": null,
      "escola_id": null,
      "created_at": "2026-07-29T21:15:57"
    }
  ]
}
```

## 5. O que cada campo significa

| Campo | Tipo | Descrição |
|---|---|---|
| `periodo_dias` | int | O valor de `dias` usado no filtro (eco do parâmetro enviado) |
| `filtros` | object | Eco de `feature`/`user_id`/`student_id` recebidos (`null` para os não enviados) — útil pra conferir que a URL que você montou foi interpretada como esperado |
| `total.chamadas` | int | Quantas chamadas à IA (linhas em `ai_usage_log`) no período, somando todas as features |
| `total.input_tokens` / `total.output_tokens` | int | Soma exata de tokens de entrada/saída no período (vem de `response.usage`, não é estimativa) |
| `total.custo_usd` | float \| null | Soma do custo estimado em USD; `null` só se **nenhuma** chamada do período teve modelo com preço cadastrado |
| `por_feature[]` | array | Mesmas métricas (`chamadas`, `input_tokens`, `output_tokens`, `custo_usd`), uma linha por `feature` (`pei_geracao`, `pei_analise_laudo`, `jornada_terapeutica`, `planejamento_anual`, `planejamento_trimestre`, `planejamento_anual_completo`, `analise_qualitativa`, `prova_reforco`), ordenado por custo decrescente |
| `por_modelo[]` | array | Mesmas métricas, agrupadas por `model` (ex. `claude-sonnet-4-6`, `claude-haiku-4-5-20251001`), ordenado por custo decrescente |
| `chamadas_recentes[]` | array | As últimas 20 chamadas individuais do período, não agregadas — útil pra debugar uma chamada específica (inclui `student_id`/`user_id`/`escola_id` quando a feature os informou, e `created_at` em ISO 8601) |

**Por que `custo_usd` pode vir `null` numa linha:** o cálculo de custo depende de uma tabela de preço fixa por modelo (`PRECOS_USD_POR_MTOK` em `app/core/ai_usage.py`). Se um modelo novo for usado antes de alguém atualizar essa tabela, a linha correspondente some com `custo_usd: null` em vez de mostrar um valor errado.

---

## 6. Erros possíveis

| Status | Causa |
|---|---|
| `401 Unauthorized` | Token ausente, inválido ou expirado |
| `403 Forbidden` | Usuário autenticado, mas sem role `ADMIN`/`SUPER_ADMIN` |
| `200` com listas vazias | Nenhuma chamada à IA registrada no período pedido (não é erro — aumente `dias` ou gere alguma chamada real primeiro) |
