# Correções — 18/08/2026 · Geração de materiais (Biblioteca + Adaptados)

> Relato de origem: *"ao gerar um material na biblioteca, não está persistindo…
> ele encaminha a tela para materiais adaptados… ao abrir a página de materiais
> já retorna 'Não foi possível carregar os materiais'… no log do Railway
> aparecem vários comandos SQL."*
>
> Cada item abaixo segue o formato **sintoma → causa raiz → correção**, como em
> `docs/CORRECOES-2026-08-11.md`.

---

## Nota sobre a rodada de 17/08 (já no `main`)

Enquanto esta rodada era feita, o `main` recebeu a
`docs/CORRECOES-2026-08-17.md`, que atacou **o mesmo bug de disco efêmero** por
outro caminho: `materiais.conteudo_gerado` (LONGTEXT) + migration 012 +
`services/material_conteudo.ler_conteudo()`. Essa é a implementação que ficou —
a coluna `Material.conteudo` que este trabalho havia criado foi descartada no
merge.

O que sobrou daqui, e que continua valendo, é **o peso dessa decisão nas
listagens**: uma coluna LONGTEXT com o material inteiro dentro de
`SELECT materiais.*` é exatamente a receita do `1038 Out of sort memory` que
derrubou o histórico de adaptados. Os itens abaixo refletem o estado **depois**
do merge.

## ⚠️ Antes do deploy: rodar as migrations

1. `migrations/012_materiais_conteudo_no_banco.sql` — a do `main`. Prefira
   `python scripts/aplicar_migration_012.py --aplicar` (lê o ENUM real antes de
   alterá-lo). **Obrigatória antes do deploy**: sem a coluna, todo
   INSERT/UPDATE de material falha.
2. `migrations/013_indices_listagem_materiais.sql` — desta rodada. Dois índices
   e, condicionalmente, `materiais.versao` / `materiais.historico_versoes` (ver
   item 1 abaixo). É idempotente e pode rodar depois do deploy sem quebrar
   nada — o código não depende dos índices para funcionar, só para ser rápido.

---

## 1. "Não foi possível carregar os materiais" ao abrir a tela

### Sintoma
A Biblioteca abre e o toast de erro aparece na hora. O histórico de materiais
adaptados devolve 500. No Railway:

```
pymysql.err.OperationalError: (1038, 'Out of sort memory, consider increasing
server sort buffer size')
[SQL: SELECT materiais_adaptados_gerados.id, …, resultado_json, …
      WHERE student_id = %s ORDER BY created_at DESC LIMIT %s, %s]
```

### Causa raiz
Não é volume de linhas: é **tamanho de linha**. A listagem fazia
`db.query(MaterialAdaptadoGerado)` — todas as colunas, inclusive
`resultado_json` — e ordenava por `created_at`.

Desde 15/08, `hq_tirinha` e `album_figurinhas` embutem **cada imagem como data
URI base64 dentro do `resultado_json`** (até ~6,6 MB por registro — ver
`ai_materiais_service._ilustrar_itens`). O `ORDER BY` obriga o MySQL a levar
essas linhas inteiras para o *sort buffer*, que estoura. **Um campo que a
listagem nem usa derrubava a listagem inteira.**

É por isso que "funcionava antes": funcionou até os primeiros materiais
ilustrados entrarem na tabela.

### Correção
- `MaterialAdaptadoGerado.resultado_json` virou **`deferred`**: não entra mais
  em nenhum `SELECT` genérico da entidade. Só é carregado quando alguém lê o
  campo (rotas de detalhe, um registro por vez).
- As três listagens passaram a selecionar **colunas explícitas**:
  `GET /materiais-adaptados/historico/student/{id}`,
  `GET /student/materiais-adaptados/` e `GET /materiais/`.
- **`Material.conteudo_gerado` (LONGTEXT, vindo da migration 012) também virou
  `deferred`.** Sem isso, a correção de 17/08 teria trocado um bug por outro:
  cada listagem de 100 materiais passaria a trazer 100 materiais completos.
- Índices `(student_id, created_at)` e `(criado_por_id, criado_em)` para
  eliminar também o *filesort* — migration 013.
- A contagem parou de usar `query.count()` do SQLAlchemy (que embrulha o SELECT
  inteiro numa subquery) e passou a ser um `func.count()` direto.

Travado por `tests/test_materiais_adaptados_historico.py`, que inspeciona o SQL
emitido e falha se `resultado_json` voltar para o SELECT da listagem.

### Segunda causa possível, coberta na mesma migration
O versionamento de material entrou em 08/06/2026 (commit `71b18c6`) com um
script Python avulso que depois saiu do repositório — não há registro de que
`materiais.versao` / `materiais.historico_versoes` tenham sido criadas em
produção. Se não existirem, **todo** `SELECT materiais.*` falha com
`(1054, "Unknown column 'materiais.versao' in 'field list'")`, o que produz
exatamente o mesmo toast. A migration 013 cria as duas se faltarem.

---

## 2. Material da Biblioteca "não persiste"

### Sintoma
O professor gera um material da Biblioteca, recebe "Material sendo gerado" e
depois o material aparece sem conteúdo — ou a tela de detalhe abre com o
material marcado como **Disponível** e nada embaixo.

### Causa raiz
O HTML (ou o JSON do mapa mental) era gravado **apenas em
`backend/storage/materiais/{id}.html`**; a linha guardava só `arquivo_path`.
O serviço web do Railway roda em **disco efêmero**: a cada redeploy os arquivos
somem enquanto a linha continua com `status='disponivel'`.

Esta rodada e a de 17/08 chegaram à mesma conclusão de forma independente. **A
correção que ficou é a do `main`** (`Material.conteudo_gerado` + migration
012 + `material_conteudo.ler_conteudo()`); ver `docs/CORRECOES-2026-08-17.md`.

### O que esta rodada acrescenta
- **A coluna nova é `deferred`** (item 1). Um LONGTEXT com o material inteiro
  entrando em todo `SELECT materiais.*` transformaria a correção num problema
  de performance imediato.
- **A tela de detalhe deixou de mentir.** Quando
  `GET /materiais/{id}/conteudo` falha, o front só fazia `console.error` e
  deixava `conteudo` em `null`: o material aparecia como **Disponível** com uma
  área em branco embaixo, sem explicação e sem saída. Era exatamente assim que
  o conteúdo perdido no disco efêmero se manifestava para o professor. Agora
  mostra o aviso com *Tentar novamente* e *Regenerar*.
- **`materiais.versao` / `historico_versoes`** podem nunca ter sido criadas em
  produção (migration 013) — ver o fim do item 1.

A query no fim da migration 013 conta quantos materiais ficaram sem conteúdo
recuperável (arquivo já perdido, coluna vazia): esses precisam de "Regenerar".

---

## 3. Gerar material da Biblioteca levava para "Materiais Adaptados"

### Sintoma
O professor escolhe um tipo em `/materiais/criar`, conclui o wizard e cai em
`/materiais/adaptados`. Na Biblioteca, nada.

### Causa raiz
Não é bug de navegação: **7 dos 12 tipos daquela tela nunca foram para a
Biblioteca.** `MateriaisCreate` decide o destino pelo campo `isAdaptado` do
tipo escolhido:

| `isAdaptado` | endpoint | tabela | onde aparece |
|---|---|---|---|
| `true` | `POST /materiais-adaptados/gerar` | `materiais_adaptados_gerados` | histórico do aluno |
| `false` | `POST /materiais/` | `materiais` | Biblioteca |

Os 12 tipos eram exibidos num grid único e idêntico; a única pista do destino
era uma linha de 10px no rodapé do card. Escolher "Texto em 3 Níveis" (o tipo
do log enviado) é escolher o caminho adaptado — o material foi gerado e salvo,
só que no outro lugar.

### Correção (UI; a duplicidade estrutural continua sendo uma decisão pendente)
- Os tipos agora aparecem em **duas seções com título e explicação**:
  "Biblioteca de Materiais" e "Material adaptado (por aluno)".
- O resumo da seleção e a etapa de alunos dizem o destino por extenso.
- O botão final é "**Criar na Biblioteca**" ou "**Gerar Material Adaptado**".

A unificação de verdade (uma porta só de criação, materiais adaptados
reatribuíveis) continua em `docs/DECISOES-2026-08-11.md`, Escolha 1 — ainda
aguardando decisão.

---

## 4. "Vários comandos SQL" no log do Railway

Duas fontes, ambas na mesma abertura de tela:

1. **`GET /materiais/` tinha N+1.** O código chamava
   `len(material.materiais_alunos)` por item — uma query por material. Com
   `size=100`, 100 queries extras por abertura. (O comentário no código
   prometia *eager-load*; não havia nenhum.) Agora é **um** `GROUP BY`.

2. **A aba "Histórico" fazia uma requisição por aluno.** `carregarHistoricoGeral`
   percorria a lista de alunos e disparava
   `GET /historico/student/{id}?size=100` para **todos**, em paralelo, só para
   descobrir quem tinha material — cada uma com COUNT + SELECT paginado.
   Novo endpoint `GET /materiais-adaptados/historico/resumo` faz isso em um
   `GROUP BY`; os materiais só são buscados do aluno que o professor abrir.

---

## 5. Qualidade da geração — o que foi encontrado

### 5.1 Truncamento silencioso na Biblioteca
`material_service` pegava `response.content[0].text` e devolvia
`success=True` **sem olhar `stop_reason`**. Com `max_tokens=4000` para um
prompt que pede HTML rico com CSS inline, o material era salvo com o HTML
**cortado no meio** — e com status "disponível", então nada indicava problema.

`ai_materiais_service` já fazia essa checagem desde 11/08; a Biblioteca tinha
ficado de fora. Agora há `_extrair_texto()`: detecta truncamento e resposta
vazia, e o teto subiu para 8192 (visual e textos) / 4096 (mapa mental).

### 5.2 Teto de tokens baixo em 18 tipos adaptados
Tipos como linha do tempo (8 eventos), dominó (16 peças) e sequenciamento
(8 etapas × 6 campos) ainda pediam 2048/3072 tokens. Ao estourar, o JSON vinha
cortado e **o material inteiro falhava**. Piso padronizado em **4096**.

`max_tokens` é teto, não meta: o prompt não mudou (continua pedindo "5-8
eventos"), a IA não escreve mais por causa disso, e o custo só sobe nas
respostas que antes eram perdidas por inteiro.

Todas as chamadas ganharam `cache_type` explícito — antes 18 delas caíam no
default `"material"`, o que apagava a distinção por tipo no tokenmeter e nos
logs.

### 5.3 Portal do aluno abria só 2 dos 6 tipos da Biblioteca
`GET /student/materiais/{id}/visualizar` respondia **501** para `resumo`,
`texto_simplificado`, `roteiro_estudo` e `atividades` — tipos que o professor
gera na mesma Biblioteca e atribui ao aluno.

Esta rodada e a de 17/08 corrigiram isso em paralelo (a do `main` ficou, via
`material_conteudo.ler_conteudo()`); o que veio daqui foi **o teste que trava o
comportamento** — não havia nenhum.

### 5.4 Material ilustrado que não cabe no banco
O commit `22d4ba2` (no `main`) atacou o peso na origem: as imagens embutidas
passaram a ser **JPEG compacto** em vez de PNG 1024², o que tira um álbum de
12 figurinhas de ~6 MB para menos de 1 MB.

Esta rodada acrescenta a rede embaixo, para o que ainda passar do limite —
inclusive os materiais **já gravados** antes daquela mudança. Quando o `INSERT`
do material completo falha por tamanho, a rota **tenta de novo sem as imagens**
antes de desistir: o professor fica
com o material utilizável (o front já cai no texto da cena como fallback) em
vez de um 500 e o crédito de IA perdido. O registro leva um `aviso` dizendo o
que faltou, e o log guarda o tamanho do payload.

> **Pendência conhecida:** mesmo em JPEG, o certo é as imagens não morarem
> dentro do `resultado_json` — deveriam ir para `ilustracoes.imagem_bytes` (que
> já existe, com rota protegida para servir) e o JSON guardar só a referência.
> Enquanto estiverem embutidas, cada linha do histórico continua sendo pesada e
> a listagem depende do `deferred` do item 1 para não cair. Isso pede um novo
> `contexto_tipo` no enum da tabela, migration, ajuste nas rotas do aluno e no
> `IlustradosViewers`. Não foi feito nesta rodada.

### 5.5 Verificações que passaram
- **Allowlists sincronizadas**: 37 tipos habilitados no backend
  (`TIPOS_HABILITADOS`) e 37 no frontend (`config.js`), sem divergência.
- **Todos os 37 métodos** referenciados em `TIPOS_MATERIAIS` existem no service
  (nenhum `AttributeError` latente).
- **Viewers**: 36 dos 37 tipos adaptados têm viewer dedicado. Só
  `ficha_leitura` cai no `GenericViewer` — que é recursivo e renderiza os
  campos com títulos humanizados, então fica legível, mas sem o tratamento
  visual dos demais. Candidato a viewer próprio numa próxima rodada.

---

## 6. Outras correções menores incluídas

- **Card da Biblioteca rotulava tudo como "Mapa Mental".** O cabeçalho era um
  ternário `tipo === 'visual' ? … : 'Mapa Mental'`: resumo, roteiro, texto
  simplificado e atividades apareciam com o rótulo e a cor errados.
- **Falha de carregamento virou estado, não só toast.** Antes, um 500 na
  listagem mostrava o vazio "Sua biblioteca ainda está vazia" — uma afirmação
  falsa sobre os dados do professor. Agora há um bloco de erro com "Tentar
  novamente", na Biblioteca e na aba Histórico.
- **Material em "Gerando…" agora atualiza sozinho.** A lista faz *polling* a
  cada 8s enquanto houver algum material gerando, e para sozinha. Antes o card
  ficava em "Gerando..." até o professor recarregar a página na mão — que se lê
  naturalmente como "não salvou".
- **Tipo sem gerador não fica preso em "gerando" para sempre.** O `else` que
  faltava em `gerar_material_background` marca erro explícito.
- **N+1 em `GET /student/materiais/`** resolvido com `joinedload`.

---

## Testes

```
tests/test_materiais_biblioteca.py           15 testes  (conteúdo no banco,
                                                        listagem enxuta, N+1,
                                                        portal do aluno,
                                                        background, regenerar)
tests/test_materiais_adaptados_historico.py  10 testes  (listagem sem
                                                        resultado_json no SQL,
                                                        resumo, isolamento)
```

Quatro deles inspecionam o **SQL emitido**, não só a resposta: é a única forma
de travar o que causava o 1038. Uma listagem pode esconder a coluna grande na
serialização e ainda assim tê-la carregado do banco — foi exatamente esse o
caso do portal do aluno, cujo docstring dizia "sem resultado_json" enquanto o
SELECT trazia tudo.

Suíte completa após o merge com o `main`: **170 passed**.
