# Correções de 2026-08-11 — backend + frontend

> Rodada de correção conjunta nos repositórios `adaptai` (Railway) e
> `adaptai-frontend` (Vercel). Cada item traz **sintoma → causa raiz → correção**,
> para que a próxima pessoa entenda o *porquê* e não só o *o quê*.
>
> Documento espelhado em `adaptai-frontend/docs/CORRECOES-2026-08-11.md`.

## Índice

1. [Homologação de tipos de material adaptado](#1-homologação-de-tipos-de-material-adaptado)
2. [Tela de Materiais: erro invisível + filtro que dava 500](#2-tela-de-materiais)
3. [Planejamento: `Request failed with status code 404`](#3-planejamento-404)
4. [JSON cru vazando na tela do aluno](#4-json-cru-na-tela)
5. [Nomes de variáveis expostos na UI](#5-nomes-de-variáveis-expostos)
6. [`alert()` nativo → toasts](#6-alert-nativo--toasts)
7. [Encoding UTF-8](#7-encoding-utf-8)
8. [Overflow de texto](#8-overflow-de-texto)
9. [Pendências conscientes](#9-pendências-conscientes)

---

## 1. Homologação de tipos de material adaptado

**Contexto.** Existem 37 tipos implementados. Nem todos entregam qualidade
aceitável, mas remover código perderia prompts, viewers e o histórico já gerado.

**Solução.** Uma allowlist. O que não está nela continua **visível** na UI (o
professor enxerga o roadmap), porém **inerte**, com selo *"Em breve"*. Prompt,
viewer e histórico permanecem intactos.

**Liberados (28):**

| Categoria | Tipos |
|---|---|
| 📚 Leitura | `texto_niveis`, `resumo_estruturado`, `ficha_leitura` |
| 🎨 Visual | `infografico`, `tabela_comparativa`, `linha_tempo`, `diagrama_venn`, `mapa_mental`¹ |
| 🧠 Memorização | `flashcards`, `jogo_memoria` |
| 🎮 Jogos | `caca_palavras`, `quiz_interativo`, `roleta_perguntas`, `cruzadinha`¹ |
| 💙 TEA/TDAH | `historia_social`, `termometro_emocoes`, `cartoes_comunicacao`, `checklist_tarefas` |
| ✍️ Completar | `verdadeiro_falso`, `complete_lacunas`, `ordenar_sequencia` |
| 📝 Avaliação | `avaliacao`² |
| 🔬 Práticos | `experimento`, `receita_procedimento`, `estudo_caso`, `diario_bordo`² |

¹ **Não constavam na lista de homologação enviada**, mas têm viewer dedicado em
`MaterialViewer.jsx` e estão em uso em produção (aparecem funcionando nas capturas
de tela). Bloqueá-los seria uma regressão visível, então foram mantidos.
**Para removê-los, apague a linha correspondente nos dois arquivos abaixo.**

² Liberados, mas a qualidade ainda precisa de validação pedagógica — ver §9.

**Em breve (9):** `hq_tirinha`, `arvore_decisao`, `album_figurinhas`, `bingo`,
`domino`, `trilha_aprendizagem`, `sequenciamento`³, `quadro_rotina`,
`contrato_comportamento`, `painel_primeiro_depois`, `ligue_colunas`.

³ `sequenciamento` também tem viewer dedicado, mas não estava na lista aprovada —
mantido bloqueado conforme pedido.

### Onde mexer

| Arquivo | Papel |
|---|---|
| `app/api/routes/materiais_adaptados.py` → `TIPOS_HABILITADOS` | **Fonte de verdade.** Rejeita a geração com `422` |
| `adaptai-frontend/src/pages/materiaisAdaptados/config.js` → `TIPOS_HABILITADOS` | Controla o que a UI deixa clicar |

> ⚠️ **As duas listas precisam ficar em sincronia.** Divergir não quebra nada, mas o
> professor clica e leva 422. O backend valida **antes** de gastar crédito de IA.

`GET /materiais-adaptados/tipos-disponiveis` agora devolve `disponivel: bool` por
tipo e `total_disponiveis` — clientes futuros podem ler a regra em vez de duplicá-la.

---

## 2. Tela de Materiais

### 2.1 O `ErrorBoundary` escondia a causa

**Sintoma.** *"Algo deu errado ao carregar esta tela"* — que é literalmente o
fallback de `ErrorBoundary.jsx`. O bug ficou aberto porque **ninguém conseguia ver
qual era o erro**.

**Correção.** O fallback agora mostra `error.message` + `componentStack`:
- sempre em desenvolvimento;
- em produção, adicionando **`?debug=1`** à URL.

Assim dá para diagnosticar direto no ambiente publicado, sem redeploy.

### 2.2 Filtro por tipo devolvia 500

**Causa raiz.**

```python
query = query.filter(Material.tipo == tipo.upper())   # ❌
```

`TipoMaterial` tem valores **minúsculos** (`"visual"`, `"mapa_mental"`). Passar
`"VISUAL"` fazia o SQLAlchemy tentar `TipoMaterial("VISUAL")` → `LookupError` → 500.
Na prática: clicar nas abas **"Visuais"** ou **"Mapas Mentais"** quebrava a listagem.

**Correção.** O parâmetro passou a ser tipado com o próprio Enum, então o FastAPI
valida e converte antes de chegar na query (e o Swagger ganha um dropdown):

```python
tipo: TipoMaterial | None = Query(None, description="...")
...
query = query.filter(Material.tipo == tipo)
```

---

## 3. Planejamento 404

**Sintoma.** Ao gerar planejamento: banner vermelho *"Request failed with status
code 404"*, quase imediato.

**Causa raiz — corrida entre dois sistemas de tracking.**

```
1. POST /planejamento/gerar-planejamento-completo/async
2.   task_manager.create_task()          → task em memória
     asyncio.create_task(...)            → agenda o worker
     return { task_id }                  → responde em ~20 ms
3. Frontend chama checkStatus() IMEDIATAMENTE:
     GET /planejamento/planejamento-completo/job/{task_id}   → consulta o BANCO
4.   SELECT ... FROM planejamento_jobs WHERE task_id = ...   → 0 linhas
     → 404 "Job não encontrado"
5. catch → reject(error)   ← sem tolerância a 404
```

A linha em `planejamento_jobs` só nascia dentro de `gerar_planejamento_completo()`,
na chamada a `_criar_job` (~linha 830), **depois** de carregar o perfil do aluno e
listar componentes. Centenas de ms a vários segundos de janela — o frontend sempre
chegava primeiro.

**Agravantes:**
- se `verificar_job_em_andamento()` encontrasse um job travado, a exceção era lançada
  **antes** do `_criar_job` → 404 permanente;
- a closure não repassava `user_id`, então o job era gravado com `user_id = 0`.

**Correção (backend):**

1. **O job é persistido dentro do request, antes de devolver o `task_id`.**
   Invariante a preservar: *se o cliente tem o id, o id é consultável.*
2. `create_task()` ganhou o parâmetro opcional `task_id` para as duas tabelas
   compartilharem o mesmo UUID (retrocompatível — omitido, gera como sempre).
3. `gerar_planejamento_completo()` passou a reaproveitar o job pré-criado
   (`obter_job(task_id)`) em vez de criar um segundo.
4. Job duplicado agora responde **`409`** com o `task_id` ativo, em vez de erro
   genérico — o frontend se reconecta ao job em andamento.
5. Toda falha no worker marca `status = failed`. Job preso em `pending` era polling
   infinito.
6. `user_id` correto, capturado do `current_user` antes da closure.
7. Resposta virou **`202 Accepted`** e inclui `poll_interval_ms` + `status_url`.

**Correção (frontend, `planejamentoService.js`):**

- tolera até 5 respostas 404 (janela de criação, réplica atrasada, restart no Railway);
- trata 409 reconectando ao job existente;
- `setTimeout` recursivo → laço com `await` (não cresce a pilha);
- timeout global de 20 min com mensagem útil;
- backoff exponencial até 15 s em falha de rede;
- intervalo ditado pelo servidor (3 s) em vez de 2 s fixos — numa geração de 10 min,
  ~200 requisições em vez de ~300.

### Checklist: 404 em endpoint de IA assíncrono

| # | Causa | Como confirmar |
|---|---|---|
| 1 | Job criado depois da resposta *(era este)* | Task em memória existe, linha no banco não |
| 2 | Job em memória com >1 worker | Falha só com Gunicorn multi-worker |
| 3 | Barra final + `redirect_slashes` | 307 seguido de falha de preflight CORS |
| 4 | Rota `/{id}` declarada antes de `/nome-fixo` | `/task/status` cai no handler de `/task/{id}` |
| 5 | Prefixo duplicado (`/api/v1/api/v1/...`) | Comparar `VITE_API_URL` com o `include_router` |
| 6 | TTL do job < duração da geração | 404 só em gerações longas |
| 7 | Router não registrado no `main.py` | 404 em **todos** os métodos do prefixo |
| 8 | 404 usado como "sem permissão" | Some quando o usuário é dono do recurso |

Diagnóstico em 3 comandos:

```bash
curl -s $API/openapi.json | jq -r '.paths | keys[]' | grep planejamento
# DevTools → Network → veja a Request URL completa
mysql -e "SELECT task_id,status,progress,created_at FROM planejamento_jobs ORDER BY created_at DESC LIMIT 5;"
```

---

## 4. JSON cru na tela

**Sintoma.** Em alguns materiais o aluno via JSON bruto em vez de UI.

**Causa raiz.** `GenericViewer` (TC-114) já cobria **objeto** sem viewer dedicado. O
que ainda vazava era a IA devolver uma **string** contendo JSON — às vezes embrulhada
em ` ```json `. Ninguém fazia `JSON.parse`, então a string caía no renderizador de
texto e era impressa inteira.

**Correção em duas camadas:**

| Camada | Arquivo | Papel |
|---|---|---|
| Backend (fonte de verdade) | `app/services/ai_output.py` → `normalizar_saida_ia()` | Se o dado sai limpo da API, nenhum cliente repete a defesa |
| Frontend (rede de segurança) | `src/utils/conteudoIA.js` → `parseConteudoIA()` | Necessária pelo conteúdo já gravado torto |

Ambas tratam 4 formatos: dict pronto · JSON puro · JSON em cerca · prosa livre. O
último caso vira `{ _raw, _formato: 'texto' }` e o `MaterialViewer` o renderiza como
parágrafo — nunca como string crua.

> ⏳ **Pendente:** aplicar `normalizar_saida_ia()` nos pontos de escrita
> (`ai_materiais_service.py`, `redacao_ai_service.py`, `diario_ai_service.py`,
> `planejamento_bncc_completo_service.py`). O módulo está pronto e testado, mas
> plugá-lo mexe em prompts de IA em produção — e o `CLAUDE.md` deste repo proíbe
> alterar comportamento de IA sem validação prévia. Ver §9.

**Regra de time:** nunca renderizar `{JSON.stringify(x)}` num caminho que o aluno
alcança. Um `grep -rn "JSON.stringify" src/pages src/components` no CI, falhando fora
de blocos de debug, encerra essa classe de bug.

---

## 5. Nomes de variáveis expostos

**Sintoma.** A UI mostrava `mapa mental` (minúsculo, sem acento) no rodapé do
material, `serie_nivel` em cabeçalhos, e até **`mapa_mentakl`** — typo que o próprio
LLM devolveu e o frontend exibiu como se fosse válido.

**Causa raiz.** `MaterialViewer.jsx` fazia `tipo.replace(/_/g,' ')` + `capitalize`,
ignorando o dicionário de rótulos que **já existia** em
`pages/materiaisAdaptados/config.js` (37 tipos com nome e acento corretos).

**Correção.** Novo `src/constants/labels.js`:

- `TIPO_LABELS` é **derivado** de `config.js` — nada duplicado;
- `ALIASES` corrige typos conhecidos da IA (`mapa_mentakl` → `mapa_mental`) e
  sinônimos legados;
- `CAMPO_LABELS` / `STATUS_LABELS` para campos e status;
- fallback `humanizar()` com Title Case pt-BR (preserva "de", "da", "e"…), então
  **nenhum slug desconhecido aparece cru**;
- em dev, loga aviso para o slug órfão virar issue.

**Por que não i18next:** o produto é monolíngue pt-BR; a lib traria ~40 kB e cerimônia
de namespace sem benefício hoje. Se um dia houver outro idioma, os dicionários viram
`pt-BR.json` sem tocar em nenhum componente — a assinatura de `rotulo()` já é
compatível com `t()`.

---

## 6. `alert()` nativo → toasts

**Sintoma.** Avisos como *"Registro salvo! A IA está analisando…"* e *"PEI gerado com
sucesso"* usavam `alert()`, que bloqueia a thread, exibe o domínio
(*"adaptai-frontend.vercel.app diz"*), não aceita estilo e é inacessível para leitor
de tela — inaceitável num produto de educação inclusiva.

**Correção.** `src/components/ui/Toast.jsx` — sem dependência externa (0 kB de bundle
novo). Montado em `App.jsx` acima de todas as rotas.

```jsx
const toast = useToast();

await toast.promise(salvarRegistro(dados), {
  loading: 'Salvando registro e analisando com IA…',
  success: 'Registro salvo! A análise da IA já está disponível.',
  error: (e) => e?.response?.data?.detail ?? 'Não foi possível salvar o registro.',
});
```

`toast.promise()` é o substituto direto do padrão *"alert() antes + alert() depois"*:
o professor continua usando a tela enquanto a IA processa.

`useToast()` fora do provider cai num no-op que loga no console — **um aviso nunca
deve ser a causa de um crash**.

### Quando toast, quando modal

| Situação | Componente |
|---|---|
| Sucesso, aviso passageiro | **Toast** |
| Erro recuperável | **Toast** (`error`, 6 s) |
| Confirmar exclusão / ação destrutiva | **Modal** (`components/ui/Modal.jsx`) |
| Geração de IA longa | **Modal com progresso**, não-dispensável |
| Erro que bloqueia a tela inteira | **Estado inline**, não toast |

`MateriaisList.jsx` já foi migrado: `alert()` → toast, `confirm()` → `<Modal>` que
mostra **qual** material será apagado e avisa que é irreversível.

---

## 7. Encoding UTF-8

**Sintoma.** `CiÃªncias`, `HistÃ³ria`, `LÃngua Portuguesa`, `MatemÃ¡tica`,
`EducaÃ§Ã£o FÃsica` na lista de componentes curriculares.

**Diagnóstico.** Na **mesma tela**, o texto estático do React aparece correto
("Como funciona?", "Distribui os objetivos pelos 4 trimestres"). Isso prova que o
problema **não é de renderização — é do dado gravado**. Os componentes vêm de
`CurriculoNacional.componente`; o fallback hardcoded no próprio endpoint tem acentos
corretos.

O padrão `Ã©`/`Ã£`/`Ãª` é **double-encoding**: bytes UTF-8 lidos como Latin-1 e
re-codificados em UTF-8 no **INSERT** (script de importação da BNCC lendo CSV com a
codificação padrão do SO — no Windows, cp1252).

```
"ê" correto     = C3AA
"ê" corrompido  = C383C2AA      ← 2 bytes viraram 4
```

**Correções aplicadas:**

1. `app/database.py` — `init_command: "SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci"`.
   O `charset` sozinho nem sempre fixa a collation da sessão; alguns proxies/DBaaS
   reabrem a conexão com o default do servidor.
2. `scripts/reparar_encoding.py` — diagnóstico + reparo dos dados já corrompidos.

```bash
python -m scripts.reparar_encoding --diagnosticar   # só relata
python -m scripts.reparar_encoding --dry-run        # mostra os UPDATEs
python -m scripts.reparar_encoding --aplicar        # executa (BACKUP ANTES)
```

> ⚠️ **A conversão NÃO é idempotente** — rodar duas vezes corrompe de novo. A proteção
> é o filtro `WHERE col REGEXP 'Ã|Â'`, que só pega linhas ainda corrompidas.
> **Não remova esse filtro. Rode em staging primeiro.**

**Ainda manual (§9):** `ALTER DATABASE`/`ALTER TABLE ... CONVERT TO CHARACTER SET
utf8mb4` e a correção do script de importação (`open(..., encoding="utf-8")` ou
`pd.read_csv(..., encoding="utf-8-sig")` para CSV de Excel brasileiro).

---

## 8. Overflow de texto

**Sintoma.** E-mails como `202407905455@aluno.ifpa.edu.br` estouram o container na
tela de PEI.

**Causa.** Sem espaços, nenhum algoritmo de quebra de linha padrão os divide. Somado
a isso, itens de flex/grid têm `min-width: auto` e se recusam a encolher abaixo da
largura do conteúdo — **é este o motivo real de o card estourar em vez de quebrar**.

**Correção** (`src/index.css`): `.texto-quebravel`, `.texto-tecnico`,
`.texto-truncado` e a regra global `.flex > *, .grid > * { min-width: 0 }`, que
sozinha resolve a maioria dos casos.

```jsx
<p className="font-medium texto-tecnico" title={aluno.email}>{aluno.email}</p>
```

**Checklist de QA de layout:** e-mail 40+ caracteres sem espaço · nome com 60
caracteres · viewport 320 px · zoom 200% (WCAG 1.4.4).

---

## 9. Pendências conscientes

Itens **não** feitos nesta rodada, com o motivo. Nenhum é esquecimento.

| # | Item | Por que ficou de fora | Esforço |
|---|---|---|---|
| 1 | Plugar `normalizar_saida_ia()` nos services | Mexe em comportamento de IA em produção; `CLAUDE.md` exige validação com poucos exemplos antes | 1 dia |
| 2 | Migration `MaterialAdaptadoAluno` | Muda schema em produção (Railway) — merece janela e backup dedicados. Plano completo em `ARQUITETURA-CONTEUDOS.md` §4 | 2 dias |
| 3 | Rotas `/aluno/redacoes/*` + router `/student/redacoes` | Telas novas, não correção. **É por isso que a redação nunca chega ao aluno** | 2 dias |
| 4 | `POST /materiais/{id}/atribuir` em lote | Endpoint novo + UI de reatribuição | 1 dia |
| 5 | `ALTER TABLE ... CONVERT TO utf8mb4` | Precisa de janela de manutenção e backup | 1 h |
| 6 | Corrigir encoding no script de importação BNCC | Precisa saber qual script/CSV originou os dados | 30 min |
| 7 | Markmap no lugar do mapa mental estático | Nova dependência (`markmap-lib`) — decisão de produto | 1 dia |
| 8 | `StudentLayout` + `BackButton` nas telas do aluno | `BackButton` **já foi criado** e está exportado; falta plugar tela a tela | 2 dias |
| 9 | Varredura de tokens do DS no painel do aluno | Ex.: `AlunoMateriais.jsx:232` usa `from-purple-600` (Tailwind puro, fora da paleta) | 2 dias |
| 10 | Regra ESLint contra cores fora do DS | Quebraria `npm run lint:strict` (`--max-warnings 0`) até a varredura #9 terminar | 15 min |
| 11 | `UniqueConstraint` em `MaterialAluno` e `RedacaoAluno` | Migration; em `RedacaoAluno` o comentário promete uma constraint que **não existe** no código | 30 min |
| 12 | Validar qualidade de `avaliacao` e dos Práticos | **Precisa de avaliação pedagógica humana**, não de código | — |

### Sobre o item 10 — regra ESLint sugerida

```js
// .eslintrc.cjs — adicionar só DEPOIS da varredura #9
'no-restricted-syntax': ['error', {
  selector: "Literal[value=/\\b(?:from|to|via|bg|text|border)-(?:purple|indigo|violet|fuchsia|pink|sky|slate|zinc|neutral|stone|gray)-\\d{2,3}\\b/]",
  message: 'Use tokens do design system (aliceblue-*, grey-*, green-*, brand-*).',
}],
```

---

## Arquivos alterados

### Backend (`adaptai`)

| Arquivo | Mudança |
|---|---|
| `app/api/routes/materiais_adaptados.py` | `TIPOS_HABILITADOS`, guarda 422, `disponivel` em `/tipos-disponiveis` |
| `app/api/routes/materiais.py` | Filtro `tipo` tipado com Enum (corrige 500) |
| `app/api/routes/planejamento_bncc.py` | Job pré-criado, 409 duplicado, 202, `user_id` correto, falha marca `failed` |
| `app/services/background_tasks.py` | `create_task(task_id=...)` opcional |
| `app/services/planejamento_bncc_completo_service.py` | Reaproveita job pré-criado |
| `app/services/ai_output.py` | **novo** — `normalizar_saida_ia()` |
| `app/database.py` | `init_command` utf8mb4 |
| `scripts/reparar_encoding.py` | **novo** — diagnóstico e reparo de mojibake |
| `docs/ARQUITETURA-CONTEUDOS.md` | **novo** — Materiais × Materiais Adaptados |
| `docs/CORRECOES-2026-08-11.md` | **novo** — este documento |

### Frontend (`adaptai-frontend`)

| Arquivo | Mudança |
|---|---|
| `src/pages/materiaisAdaptados/config.js` | `TIPOS_HABILITADOS` + helpers |
| `src/pages/MateriaisAdaptados.jsx` | Cards "Em breve", "selecionar todos" só dos liberados, filtro antes do POST |
| `src/components/ErrorBoundary.jsx` | Expõe o erro real (`?debug=1` em produção) |
| `src/services/planejamentoService.js` | Polling tolerante a 404/409, timeout, backoff |
| `src/constants/labels.js` | **novo** — dicionário de rótulos |
| `src/utils/conteudoIA.js` | **novo** — `parseConteudoIA()` |
| `src/components/MaterialViewer.jsx` | Usa `parseConteudoIA` + `rotulo`; fallback de texto |
| `src/components/ui/Toast.jsx` | **novo** — toasts |
| `src/components/ui/BackButton.jsx` | **novo** — voltar com fallback |
| `src/components/ui/index.js` | Exporta `ToastProvider`, `useToast`, `BackButton` |
| `src/App.jsx` | `<ToastProvider>` global |
| `src/pages/MateriaisList.jsx` | `alert()` → toast, `confirm()` → `<Modal>` |
| `src/index.css` | Utilitários de overflow + `min-width: 0` em flex/grid |
| `docs/CORRECOES-2026-08-11.md` | **novo** — cópia deste documento |

---

## Ordem de deploy sugerida

O backend é retrocompatível com o frontend antigo, e vice-versa — mas o **404 do
planejamento só some com os dois lados no ar**.

1. **Backend (Railway) primeiro.** Nada aqui quebra o frontend atual: `422` para tipo
   bloqueado já era um caminho de erro tratado, e o `202` é lido como sucesso pelo
   axios.
2. **Frontend (Vercel) em seguida.**
3. **Depois do deploy:** rodar `python -m scripts.reparar_encoding --diagnosticar` em
   produção e avaliar o `--aplicar` com backup.

### Verificação pós-deploy

| # | Teste | Esperado |
|---|---|---|
| 1 | Abrir Materiais e clicar em "Visuais" | Lista filtra, sem erro |
| 2 | Materiais Adaptados → expandir categorias | Tipos não homologados cinza, tracejados, com selo "Em breve" |
| 3 | Selecionar tipos liberados e gerar | Gera normalmente |
| 4 | `/students/{id}/planejamento` → Gerar | Barra de progresso, **sem banner 404** |
| 5 | Excluir um material | Modal com o nome do material, não `confirm()` |
| 6 | Abrir um material adaptado | Rodapé com "Mapa Mental", não `mapa_mental` |
| 7 | Qualquer tela quebrada + `?debug=1` | Stack visível no fallback |
