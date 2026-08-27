# Rodada de 2026-08-17 — validações + duas features

Formato: **sintoma → causa raiz → correção**, igual a `CORRECOES-2026-08-11.md`.
Toca os dois repositórios (`adaptai` e `adaptai-frontend`).

---

## 1. Painel SEDUC removido da UI (código preservado)

**Pedido.** O item aparecia no menu do admin com selo "Em breve" e link
desabilitado — anunciava um módulo que ainda não existe.

**Correção.** Só a **entrada visual** saiu, em
`adaptai-frontend/src/components/Layout.jsx` (`adminNavigation`). A linha ficou
comentada junto com o import do ícone `Map`, com instrução de como republicar.

**Continua intacto e funcional por URL direta (`/seduc`):**
`src/pages/PainelSeduc.jsx`, a rota em `App.jsx` e o backend
`app/api/routes/seduc.py`.

---

## 2. Gráfico de desempenho "não varia entre alunos"

**Sintoma relatado.** O gráfico de desempenho parecia igual para todos os alunos.

**Não era coincidência de dados. Eram duas regras erradas**, duplicadas em
`StudentPerformance.jsx` e `AlunoDesempenhoDetalhado.jsx`:

### 2.1 Filtro de status excluía a maioria das provas

As duas telas filtravam `status === 'concluida'`. O backend, porém, grava dois
estados finais (`app/api/routes/provas.py:705`, `student_provas.py:356`):

| status | significado |
|---|---|
| `concluida` | entregue, **ainda tem dissertativa** aguardando correção |
| `corrigida` | nota final fechada |

Prova só de múltipla escolha é corrigida na hora ⇒ termina em **`corrigida`** e
**nunca entrava nos gráficos**. Um aluno com 5 provas objetivas feitas produzia
série vazia — visualmente idêntico a um aluno sem prova nenhuma.

Detalhe que explica a confusão: os *cards* de cima (média, aprovações) sempre
contaram os dois status, porque vêm de `estatisticas` calculado no backend. Só
os gráficos, calculados no front, é que estavam errados.

### 2.2 Escala 0–10 tratada como 0–100% (só em `StudentPerformance.jsx`)

`ProvaAluno.nota_final` é **0–10** (`pontuacao/maxima * 10`, `provas.py:697`).
A tela assumia porcentagem:

- `<YAxis domain={[0, 100]}>` → toda linha achatada no chão do gráfico;
- faixas `0-40% / 40-60% / 60-80% / 80-100%` → qualquer nota real caía em "0-40%";
- badge com corte `>= 70` / `>= 50` → **todo** aluno virava "Precisa Melhorar";
- textos "Nota: 8.5%", "Média Geral 7.2%".

**Correção.** A regra saiu das telas e virou
`adaptai-frontend/src/utils/desempenhoProva.js` (fonte única):
`STATUS_FINALIZADOS`, `evolucaoNotas()`, `distribuicaoNotas()` em escala 0–10,
`rotuloStatusProva()`, `formatarNota()`. As duas telas passaram a consumir o
util. De quebra:

- o histórico deixou de rotular prova `corrigida` como "Pendente";
- "Ver Detalhes" voltou a aparecer para prova `corrigida`;
- a evolução passou a ordenar por `data_conclusao` de verdade, em vez de um
  `.reverse()` que dependia da ordem do backend.

---

## 3. Imagens dos materiais — o que estava certo e o que faltava

**Sintoma relatado.** "Não consigo ver imagens de materiais adaptados já
processados para um aluno."

### 3.1 Ilustração IA da Biblioteca — correção anterior está correta ✅

O commit `ab2378f` moveu os bytes para `Ilustracao.imagem_bytes` (migration 011).
As rotas do professor e do aluno servem do banco. Está certo.

Linhas **anteriores** à migration ficam com `imagem_bytes` NULL e devolvem 404 —
irrecuperável por design: o arquivo em disco já não existe. Não é bug novo.

### 3.2 Materiais adaptados — o commit tornou a falha visível, não a eliminou

`ab2378f` trocou o `print()` silencioso por `logger.exception` + 500 real. Isso
resolve o "sucesso fingido", mas **a causa suspeita continuava**: as imagens vão
embutidas em base64 dentro de `resultado_json` (PNG 1024×1024 por figurinha ⇒
até ~6,6 MB de JSON num álbum).

**Correção (redução de peso, sem trocar a arquitetura):**
`app/services/image_providers.py` ganhou dimensões compactas
(`quadrado_compacto` 512², `paisagem_compacta` 768×448) e `output_format`
parametrizável; `ai_materiais_service._ilustrar_itens` passou a pedir **JPEG
compacto** para as imagens embutidas. Um álbum de 12 figurinhas sai de ~6 MB
para menos de 1 MB, sem diferença perceptível no tamanho em que a imagem é
exibida. As ilustrações avulsas (`Ilustracao`) seguem em PNG/tamanho cheio —
elas têm linha e rota próprias, o peso não é problema lá.

### 3.3 A causa mais provável do que foi observado: falha muda

Sem `FAL_API_KEY`, `_ilustrar_itens` retornava **em silêncio**. O material salvava
normalmente, sem imagem e **sem nenhum aviso** — indistinguível de "o recurso não
existe". Mesma coisa quando o provedor recusava.

**Correção.** `_ilustrar_itens` passou a devolver
`{solicitadas, geradas, motivo}`, anexado ao material como
`ilustracoes_status`; `IlustradosViewers.jsx` traduz isso numa frase
(`sem_chave`, `provedor_indisponivel`, `falha_geracao`, `parcial`). A degradação
continua elegante — agora ela diz por quê.

### 3.4 Achado novo: a Biblioteca de Materiais tinha o MESMO bug de disco efêmero

O conteúdo gerado (`Material`) era gravado **apenas** em
`storage/materiais/{id}.html|json`, com o banco guardando só `arquivo_path`. O
serviço web do Railway roda em disco efêmero (não há volume em `railway.json`):
a cada redeploy o arquivo some enquanto a linha segue `status='disponivel'`, e
`GET /materiais/{id}/conteudo` passa a devolver 404 para material que a
Biblioteca mostra como pronto. É exatamente o defeito que a migration 011
corrigiu para `ilustracoes` — nunca havia chegado em `materiais`.

**Correção.** `migrations/012_materiais_conteudo_no_banco.sql` cria
`materiais.conteudo_gerado` (LONGTEXT), que passa a ser a fonte de verdade.
`arquivo_path` continua sendo escrito como cache; a leitura só cai nele quando a
coluna está vazia (linhas antigas). O histórico de versões passou a guardar o
conteúdo **inline** pelo mesmo motivo. A leitura virou
`app/services/material_conteudo.ler_conteudo()`, compartilhada pelas rotas do
professor e do aluno.

**Efeito colateral bom:** a rota do aluno só aceitava `visual` e `mapa_mental` e
devolvia **501** para `resumo`, `texto_simplificado`, `roteiro_estudo` e
`atividades`. Com o helper compartilhado, todo tipo que o professor gera o aluno
abre.

---

## 4. Feature — Atividade de Geometria (Biblioteca de Materiais)

Novo `TipoMaterial.GEOMETRIA`, no mesmo fluxo dos demais tipos da Biblioteca
(`POST /materiais/` → geração em background → `/materiais/{id}/conteudo`).

**Por que a figura é SVG escrito pelo Claude, e não imagem do Flux/fal.ai:**
modelo de difusão não respeita medida. "Triângulo retângulo com catetos 3 e 4"
sai plausível e **errado** — e o exercício passa a ensinar coisa errada. Modelo
de imagem também escreve texto mal (por isso o `_ESTILO` de
`ilustracao_service` proíbe texto), e figura geométrica sem rótulo
("A", "B", "5 cm", "60°") não serve. SVG resolve os três pontos e ainda pesa
alguns KB em vez de ~400 KB por imagem em base64.

**Pipeline** (`material_service.gerar_atividade_geometria`): uma chamada monta a
atividade (conceitos, enunciados, `figura_descricao`, dica, resposta,
resolução); depois **uma chamada por figura**, em paralelo (3 workers), com teto
de `MAX_EXERCICIOS_GEOMETRIA = 6`. Falha de uma figura não derruba o material —
o viewer mostra a descrição no lugar e avisa quantas faltaram.

**Segurança.** Todo SVG passa por `app/services/svg_sanitizer.py` antes de ser
gravado: allowlist de tags e atributos (sem `script`, `style`, `foreignObject`,
`image`, `use`, `href`/`xlink:href`, `on*`), teto de 40 KB, `viewBox` garantido.
Coberto por `tests/test_svg_sanitizer.py`.

No frontend (`GeometriaViewer.jsx`) o SVG vai dentro de um **`<img>` com data
URI**, não injetado no DOM. Duas razões: script dentro de SVG carregado por
`<img>` não executa (o sanitizador deixa de ser ponto único de falha), e o
html2canvas do "Salvar como PDF" rasteriza `<img>` de forma confiável, ao
contrário de SVG inline sem `width`/`height`.

---

## 5. Feature — "Gerar ilustração" no tema de redação

O `IlustracoesPanel` já existia na tela do tema, mas gerar exigia três passos
(Adicionar → aba "Gerar com IA" → botão), sendo que os dois primeiros não
acrescentavam nada: o backend já monta o prompt a partir do próprio conteúdo
quando `descricao` vem vazia (`_resolver_conteudo` usa título + área temática +
proposta).

**Correção.** Prop `rotuloAcaoRapida` no `IlustracoesPanel`: um botão que faz a
**mesma chamada** do modal, em um clique, com `tamanho: 'quadrado'` — o formato
padrão das demais ilustrações. Isso é proposital: a imagem cai na mesma galeria,
na mesma célula `aspect-square` com `object-contain`, indistinguível das outras.
Nenhuma rota nova no backend.

---

## 6. Salvar como PDF nas atividades com imagem

Já existia em `MaterialDetail`, `AlunoMaterialVisualizacao`,
`AlunoMaterialAdaptadoView` e no histórico de `MateriaisAdaptados`. Faltava
justamente onde o professor cai **depois de gerar** um material com imagem:

- **Tela de resultado de `MateriaisAdaptados`** (etapa 3): botão adicionado;
  `handleExportarPdf` passou a receber `(elementId, nome)`.
- **Painel de ilustrações** (`IlustracoesPanel`): prop `permitirPdf`, ligada na
  tela do tema de redação.
- **Atividade de geometria**: já coberta pelos botões existentes de
  `MaterialDetail` (professor) e `AlunoMaterialVisualizacao` (aluno). O viewer
  ganhou "Mostrar todas as resoluções" — recolhido, o PDF vira folha do aluno;
  expandido, vira folha do professor com gabarito.

---

## Pendências conscientes

1. **Migration 012 precisa rodar antes do deploy** — e ainda **não foi
   aplicada**. Sem a coluna, todo INSERT/UPDATE de material quebra; sem
   `'GEOMETRIA'` no ENUM, criar material de geometria falha com *Data truncated
   for column 'tipo'*. Use `python scripts/aplicar_migration_012.py` (dry-run) e
   depois `--aplicar`: o script lê o ENUM real em `INFORMATION_SCHEMA` e só
   acrescenta o valor novo, eliminando o risco de errar o case.
2. **Suíte de testes: 150 passed, 0 failed, 0 skipped** (2026-08-17), com as
   versões pinadas de `requirements.txt` sob Python 3.11. Inclui a suíte
   anti-IDOR completa — o que confirma que `LONGTEXT().with_variant(Text,
   'sqlite')` compila no SQLite e não derruba o `create_all()` do conftest (foi
   exatamente esse o achado do code review no MEDIUMBLOB da rodada anterior).
3. **Imagem embutida em base64 continua embutida.** O peso caiu bastante (3.2),
   mas a solução definitiva é a mesma da `Ilustracao`: tabela + rota próprias
   para as imagens do material adaptado. Vale reavaliar se o volume crescer.
4. **Qualidade pedagógica da geometria não foi validada com exemplos reais** —
   nenhuma geração foi disparada (regra do `CLAUDE.md`: não gerar conteúdo de IA
   em massa para teste). Gerar 2 ou 3 atividades e conferir se as figuras batem
   com os enunciados antes de liberar para as escolas.
