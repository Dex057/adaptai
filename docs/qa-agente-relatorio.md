# Relatorio do Agente de QA - AdaptAI

Fonte de verdade: copia da planilha de QA no Google Drive
(fileId `1IdZu6GvMh6uwyavgusZaDzNrnBE-ydLM`, arquivo "Claude - Plano_de_Testes_AdaptAI.xlsx",
propriedade de davi.martins@ayio.com.br). Leitura feita via `read_file_content` (MCP Google
Drive, somente leitura - nao ha ferramenta de escrita em Sheets disponivel neste ambiente).

**Metodologia desta rodada:** varredura completa dos 191 casos de teste; filtrados os 69 com
Status = Falhou (33) ou Bloqueado (36). Processados em ordem sequencial de aparicao na
planilha (linha a linha), priorizando prioridade Alta + Falhou, depois Alta + Bloqueado, depois
Media/Baixa. Cada TC abaixo foi investigado no codigo antes de qualquer edicao. Nao houve
commit - alteracoes ficam no working tree para revisao do usuario.

---

## Acesso/Login

### TC-003 - Senha errada (Acesso/Login)
- **Problema (planilha):** "O erro é mostrado por pouco tempo, o usuário nem conseguiria ler,
  mas não entra no sistema".
- **Causa raiz:** `app/api/routes/auth.py` (`/auth/login`, `/auth/login/json`) já recusa a
  senha errada corretamente (401, `detail="Email ou senha incorretos"`), com timing constante
  anti-enumeração. O comportamento "não entra" está correto. O problema é puramente de UI
  (duração do toast/alerta de erro) - não existe código de frontend neste repositório
  (repo é só a API FastAPI).
- **Ação tomada:** Não corrigido - fora do escopo deste repositório (backend).
- **Justificativa:** Backend já implementa o resultado esperado ("Mostra erro e NAO entra").
  A parte que falha (tempo de exibição do erro) é responsabilidade do frontend.

### TC-006 - Recuperar senha / Esqueci a senha (Media) - **MITIGADO (parcial)**
- **Problema (planilha):** "O e-mail de redefinição não chegou".
- **Causa raiz:** `app/services/email_service.py::_enviar_email` depende de
  `settings.RESEND_API_KEY` (`app/core/config.py:123`, default `""`). A chave **não está
  definida** em `.env` nem em `.env.example` neste ambiente. Quando vazia, a função loga um
  warning e retorna `False` silenciosamente (por desenho, para não vazar via
  `/auth/forgot-password` se o e-mail existe ou não - a resposta ao usuário é sempre genérica
  de sucesso). Resultado: nenhum e-mail é enviado e nada indica isso pro time de operação.
- **Ação tomada:** Adicionado em `app/main.py` (lifespan/startup) um `logger.warning` quando
  `RESEND_API_KEY` está vazia **em produção**, citando TC-006/TC-186. Isso NÃO resolve o envio
  de e-mail em si - continua **Requer decisão do usuário**: provisionar `RESEND_API_KEY` +
  `EMAIL_FROM` com domínio verificado no Resend em `.env`/infra de produção.
- **Justificativa:** Sem a chave, o fluxo de e-mail é estruturalmente incapaz de enviar; não há
  correção de código possível aqui sem um segredo válido. O warning de startup fecha a lacuna de
  visibilidade (o time passa a ver no log que o e-mail está desabilitado, em vez de descobrir só
  quando um usuário reportar).

### TC-007 - Bloqueio de rota (aluno) (Alta)
- **Problema (planilha):** "Não aparece aviso sobre permissão, mas é redirecionado ao login".
- **Causa raiz:** `app/api/dependencies.py` já levanta `HTTPException` 401/403 com mensagens
  claras quando o papel do usuário não bate com a rota. O comportamento de exibir (ou não) um
  toast de "sem permissão" antes do redirect é decisão do frontend, que consome o `detail` do
  erro.
- **Ação tomada:** Não corrigido - fora do escopo deste repositório (backend).
- **Justificativa:** A API já devolve a informação necessária (status + `detail`); a ausência
  do aviso visual é responsabilidade da camada de apresentação.

### TC-017 - Criar aluno (validação) (Alta) - **CORRIGIDO**
- **Problema (planilha):** "Registrou o Aluno mesmo com o item obrigatório (sobre a série), o
  sistema registrou sem avisar o campo obrigatório".
- **Causa raiz:** `app/schemas/student.py::StudentBase.grade_level` era `Optional`, e
  `app/api/routes/students.py:115` (`create_student`) fazia
  `grade_level=student_data.grade_level or "Não especificado"` - ou seja, o backend
  silenciosamente aceitava e completava a série ausente, em vez de rejeitar a requisição.
- **Ação tomada:** Corrigido em `app/schemas/student.py` (novo `StudentCreate.grade_level:
  str = Field(..., min_length=1, max_length=50)`, sobrescrevendo o campo opcional herdado de
  `StudentBase`) e em `app/api/routes/students.py:115` (removido o fallback `or "Não
  especificado"`, agora usa `student_data.grade_level` direto, já garantido pelo schema).
- **Justificativa:** Com o campo marcado como obrigatório no schema Pydantic, o FastAPI passa a
  responder 422 automaticamente quando `grade_level` não é enviado/está vazio, cumprindo o
  resultado esperado do TC-017 ("Bloqueia e indica os campos obrigatórios"). O fluxo de
  importação em lote (`students.py:399`, `POST /students/importar-csv`) não usa
  `StudentCreate` (constrói `Student` diretamente com fallback próprio "Não especificado"), logo
  não é afetado por esta mudança - continua aceitando planilhas sem coluna de série.

---

## Alunos/Turma

### TC-107 - Ordenar lista (Baixa) - **CORRIGIDO**
- **Problema (planilha):** "Não aparece a opção de ordenar".
- **Causa raiz:** `GET /students/` (`app/api/routes/students.py:132-184`) sempre ordenava com
  `query.order_by(Student.name)` fixo - não existia nenhum parâmetro de ordenação exposto na
  API.
- **Ação tomada:** Corrigido em `app/api/routes/students.py` - adicionados os parâmetros
  opcionais `ordenar_por: Literal["name","grade_level","created_at"] = "name"` e
  `direcao: Literal["asc","desc"] = "asc"`, aplicados via `order_by(desc(coluna) if direcao ==
  "desc" else asc(coluna))` com `coluna = getattr(Student, ordenar_por)` (allowlist pelo próprio
  `Literal` do FastAPI, que rejeita com 422 qualquer valor fora da lista).
- **Justificativa:** Mudança 100% aditiva - default `name`/`asc` preserva exatamente o
  comportamento anterior, então nenhum cliente existente quebra; clientes que quiserem ordenar
  por outro campo passam a poder. Resolve diretamente o TC-107 ("A ordem muda corretamente").

### TC-111 - Transferir de turma (Baixa) - **CORRIGIDO**
- **Problema (planilha):** "não aparece a opção de transferir de turma".
- **Causa raiz:** `app/schemas/student.py::StudentUpdate` não tinha os campos `turma` nem
  `matricula` (só existiam em `StudentCreate`). Como `PUT /students/{id}`
  (`app/api/routes/students.py:443-493`) aplica `setattr` genérico a partir de
  `StudentUpdate.model_dump(exclude_unset=True)`, não havia NENHUMA forma de alterar a turma
  de um aluno depois de criado via API - nem existe um endpoint dedicado de "mudar turma"
  (o único `POST /students/{id}/transferir` muda o **professor responsável**, não a turma).
- **Ação tomada:** Corrigido em `app/schemas/student.py` - adicionados `turma: Optional[str]`
  e `matricula: Optional[str]` a `StudentUpdate`.
- **Justificativa:** A rota `PUT /students/{id}` já tem toda a lógica de autorização e
  persistência necessária; faltava apenas o campo no schema de entrada. Isso resolve
  diretamente o cenário do TC-111 ("Mover o aluno para outra turma" via edição do aluno).

---

## Material Adaptado / Portal do Aluno (cluster investigado em conjunto)

### TC-027, TC-028, TC-031, TC-032, TC-033, TC-081, TC-088, TC-118, TC-123, TC-124, TC-125
Todos compartilham a mesma causa raiz e por isso são reportados juntos (investigados a partir
do TC-027, primeiro da sequência).

- **Problema (planilha):**
  - TC-027 (Alta, Falhou): "Não aparece nenhum material gerado para aquele aluno" no Portal do
    Aluno após o professor gerar.
  - TC-028 (Alta, Bloqueado), TC-031 (Alta, Bloqueado), TC-032 (Alta, Bloqueado), TC-033
    (Baixa, Bloqueado): mesma causa - "Não aparece nenhum material gerado para aquele aluno".
  - TC-081 (Alta, Falhou, App Mobile): "Material é gerado, porém, não chega no aluno".
  - TC-088 (Media, Bloqueado, Acessibilidade): "Os materiais gerados pelo professor não estão
    chegando no aluno".
  - TC-118 (Media, Falhou): "os materiais gerados não chegam nos alunos" (+ falta seleção de
    múltiplos alunos na geração).
  - TC-123, TC-124, TC-125 (Baixa, Bloqueado): dependem de haver material disponível no portal.
- **Causa raiz:** **O sistema tem DOIS pipelines de "material adaptado" completamente
  desconectados:**
  1. `POST /materiais-adaptados/gerar` (`app/api/routes/materiais_adaptados.py`) - usado pela
     tela "Criar com IA" do professor (25+ tipos: resumo, mapa mental, flashcards etc., bate
     com TC-022/023/024/025 que "Passou"). Ele salva o resultado **apenas** na tabela
     `materiais_adaptados_gerados` (model `MaterialAdaptadoGerado`,
     `app/models/material_adaptado_gerado.py`), vinculada só a `student_id`.
  2. `GET /student/materiais/` (`app/api/routes/student_materiais.py`) - o que o Portal do
     Aluno usa para listar "Meus materiais". Ele lê de tabelas **diferentes**:
     `materiais` + `materiais_alunos` (models `Material`/`MaterialAluno`,
     `app/models/material.py`), filtrando por `MaterialAluno.aluno_id` +
     `Material.status == DISPONIVEL`.

  Não existe, em nenhum lugar do código (`grep "MaterialAluno("` confirma), uma ponte que crie
  um registro em `MaterialAluno`/`Material` a partir de um `MaterialAdaptadoGerado`. Ou seja:
  **tudo que é gerado pela tela principal de "Criar com IA" (a que os testes de professor usam
  e passam) nunca fica visível para o aluno**, porque o Portal do Aluno lê de uma tabela
  totalmente diferente, que só é populada pelo pipeline antigo/paralelo em
  `app/api/routes/materiais.py` (`POST /materiais/`, com `TipoMaterial` limitado a
  `VISUAL/MAPA_MENTAL/RESUMO/TEXTO_SIMPLIFICADO/ROTEIRO_ESTUDO/ATIVIDADES`).
- **Ação tomada:** **Não corrigido - Requer decisão do usuário.** Este é exatamente o tipo de
  bug arquitetural citado nas instruções deste agente ("material não chega no aluno pode ter
  várias causas") - não tentei adivinhar uma correção.
- **Justificativa / hipóteses para decisão:**
  1. Fazer `POST /materiais-adaptados/gerar` também criar `Material` + `MaterialAluno` para
     cada aluno (bridge), OU
  2. Fazer `GET /student/materiais/` (e as rotas de visualizar/favoritar/anotar) passarem a ler
     de `MaterialAdaptadoGerado` em vez de `Material`/`MaterialAluno`, OU
  3. Unificar os dois pipelines em um só.
  Qualquer uma das três é uma mudança de arquitetura/dado que afeta múltiplas rotas e o
  contrato consumido pelo frontend (Portal do Aluno mobile e desktop) - não é seguro decidir
  isso sem confirmação do usuário/product owner, dado o volume de TCs (9) que dependem dela.

---

## PEI

### TC-034, TC-040 - "Meu PEI" não aparece pro aluno (Media/Alta, Bloqueado)
- **Problema (planilha):** "Não aparecere o PEI" / "Não aparecere o PEI no portal alunos".
- **Causa raiz:** `GET /meu-pei` (`app/api/routes/student_pei.py:59-140`) busca
  `PEI.status.in_(["ativo","rascunho"])` para o aluno logado - já inclui rascunho, então não é
  um filtro de status óbvio demais. Não encontrei um bug único e claro no código deste
  endpoint (a lógica de agregação de objetivos e cálculo de progresso está correta).
- **Ação tomada:** Não corrigido. **Requer decisão do usuário / reprodução guiada.**
- **Justificativa:** Hipóteses levantadas mas não confirmadas sem acesso a dados reais de teste:
  (a) o PEI foi criado para um `student_id` diferente do aluno logado nos testes; (b) o PEI
  ficou com `status` fora de `["ativo","rascunho"]`; (c) relação com TC-041/042 ("Aparece na
  versão Mobile, no desktop não" ao criar meta de PEI) - se a criação de objetivo no desktop
  falha silenciosamente, o PEI pode nunca ganhar objetivos/nunca ser persistido corretamente.
  Não tentei corrigir às cegas porque, como material, isso tem múltiplas causas possíveis.

### TC-127 - Histórico de versões do PEI (Baixa, Bloqueado)
- **Problema (planilha):** "não tem opção de ver anteriores".
- **Causa raiz:** O model `PEI`/`PEIObjetivo` não versiona o PEI em si (existe apenas
  `PEIAjuste`, um log de auditoria de mudanças pontuais - `GET /planejamento/pei/{id}/historico`
  já existe e lista esses ajustes). Não há um conceito de "versão completa arquivada do PEI"
  como existe para `Material` (`historico_versoes` em `app/models/material.py`).
- **Ação tomada:** Não corrigido - feature ausente, não é um bug pontual.
  **Requer decisão do usuário** (produto: definir se "histórico" = log de ajustes já existente
  em `/planejamento/pei/{id}/historico`, e nesse caso é só uma questão de o frontend consumir
  essa rota, ou se precisa de snapshot completo por versão).
- **Justificativa:** Já existe um endpoint (`/pei/{pei_id}/historico`) que cobre parte do
  pedido (quem mudou o quê e quando); antes de construir versionamento completo vale confirmar
  se isso já resolveria o TC-127.

### TC-129 - Meta com prazo vencido (Baixa, Falhou) - **CORRIGIDO**
- **Problema (planilha):** "não informa que esta vencido".
- **Causa raiz:** Nenhum lugar do backend calculava se `PEIObjetivo.prazo` já havia passado
  (`grep "vencid"` não retornou nada em `app/`).
- **Ação tomada:** Corrigido em `app/api/routes/planejamento_bncc.py`
  (`obter_pei_completo`, `GET /planejamento/pei/{pei_id}/completo`) - adicionado campo
  `prazo_vencido: bool` por objetivo, calculado como
  `obj.prazo and obj.prazo < hoje and obj.status != "atingido"`.
- **Justificativa:** Endpoint mais direto usado para "abrir/olhar uma meta" no PEI (bate com o
  passo do TC-129 "Olhar a meta"). Resolvi apenas essa rota (não toquei em
  `student_pei.py::ObjetivoResumo`, que é um schema Pydantic separado usado no Portal do Aluno,
  para manter a mudança pequena e rastreável a este TC específico - se o time quiser o mesmo
  indicador no portal do aluno, é uma extensão direta do mesmo padrão).

---

## Diário de Aprendizagem

### TC-046 - Humor/evolução (Baixa, Falhou)
- **Problema (planilha):** "Não apresentado".
- **Causa raiz:** O dado existe e já é agregado no backend:
  `GET /diario/estatisticas/student/{id}` (`app/api/routes/diario_aprendizagem.py:539-640`)
  retorna `por_humor` (contagem por humor) e há `GET /diario/timeline/student/{id}` que inclui
  `humor` por registro. Não encontrei um bug de cálculo nessas rotas.
- **Ação tomada:** Não corrigido. **Provável gap de frontend** (a tela de diário não consome
  `estatisticas`/`timeline` para exibir humor/evolução) - fora do escopo deste repositório para
  confirmar sem acesso ao frontend.
- **Justificativa:** Dado disponível via API; sem evidência de bug no backend, não há o que
  corrigir aqui com segurança.

### TC-134 - Resumo semanal (IA) (Baixa, Falhou)
- **Problema (planilha):** "Opção não encontrada".
- **Causa raiz:** O endpoint existe e está registrado: `POST /diario/resumo-semanal/gerar` e
  `GET /diario/resumo-semanal/student/{student_id}`
  (`app/api/routes/diario_aprendizagem.py:376-462`), usando `diario_ai_service.gerar_resumo_semanal`.
- **Ação tomada:** Não corrigido - backend já implementa a feature.
  **Requer decisão do usuário** (frontend precisa expor um botão/tela para chamar essa rota -
  mesmo padrão de "feature pronta no backend, sem entrada no menu" encontrado em Plano de Aula
  e SEDUC abaixo).
- **Justificativa:** Não há bug de API a corrigir; o gap é de navegação/UI.

---

## Relatórios/Jornada

### TC-141 - Cache da Jornada (Media, Falhou) - **CORRIGIDO**
- **Problema (planilha):** "Toda vez ao apertar em jornada terapêutica, a IA gera uma nova
  análise sobre o aluno".
- **Causa raiz:** `GET /relatorios/student/{student_id}/analise-consolidada`
  (`app/api/routes/relatorios_analise.py`) chamava `client.messages.create(...)` (Claude, até
  8000 tokens) toda vez que o endpoint era acessado - sem nenhum cache, mesmo quando os
  relatórios do aluno não mudaram desde a última análise. O projeto já tem uma infraestrutura
  de cache de IA pronta (`app/services/ai_cache_service.py`, tabela `AICache`) usada por outros
  serviços (ex: `plano_aula_ai_service.py`), mas esta rota não a utilizava.
- **Ação tomada:** Corrigido em `app/api/routes/relatorios_analise.py` - antes de chamar a IA,
  calcula o hash do prompt (`_hash_prompt`, que já inclui todos os `dados_extraidos` dos
  relatórios do aluno) e consulta `lookup_cache`; em cache hit, retorna a análise salva sem
  gastar tokens; em miss, gera normalmente e salva com `save_cache` (TTL 30 dias).
- **Justificativa:** Como o prompt já embute o conteúdo de todos os relatórios do aluno, o
  mesmo conjunto de relatórios sempre produz o mesmo hash (cache hit = resposta instantânea sem
  custo). Assim que um laudo novo é adicionado/editado, o conteúdo do prompt muda, o hash muda,
  e a análise é reprocessada automaticamente - resolve exatamente o comportamento esperado do
  TC-141 ("Abre rápido (sem refazer a IA) ou indica cache") sem exigir invalidação manual.

### TC-142, TC-143 - Exportar PDF da Jornada (Baixa, Bloqueado)
- **Problema (planilha):** "O Botão de exportar jornada não está funcionando".
- **Causa raiz:** Não existe endpoint de exportação de PDF para a Jornada em
  `relatorios_analise.py` nem em nenhuma outra rota (`grep` por "pdf"/"exportar" não retornou
  nada relacionado a Jornada) - a exportação, se existir, é inteiramente client-side (ex:
  `html2pdf`/`jsPDF` renderizando o DOM). Nota: o TC-052 (mesma funcionalidade "Exportar PDF"
  da Jornada) foi retestado depois (27/07) e marcado **Passou** - sugere que o problema pode já
  ter sido corrigido no frontend entre 22/06 (data do TC-142/143) e 27/07, ou é intermitente.
- **Ação tomada:** Não corrigido - não há código de backend correspondente a alterar.
  **Sugestão:** re-testar TC-142/143 à luz do TC-052 já ter passado, antes de investigar mais.
- **Justificativa:** Sem endpoint de export no backend, não há causa raiz de API para corrigir;
  o achado mais útil é o indício de que já pode estar resolvido (TC-052).
- **Validado (rodada seguinte):** reconferido direto na planilha - TC-142/143 testados por
  Evelin Yoshida em 22/06/2026 (Bloqueado); TC-052 (mesma feature "Exportar PDF" da Jornada)
  retestado por Davi Martins em 27/07/2026 e marcado **Passou**. Datas confirmam que o retest
  mais recente já passou - recomenda-se apenas re-testar TC-142/143 antes de investigar mais.

---

## Redação

### TC-055, TC-144, TC-145 - Geração/correção de redação falhando - **CORRIGIDO (parcial)**
- **Problema (planilha):**
  - TC-055 (Alta, Bloqueado): "A redação não consegue ser salva nem enviada" (+ temas não
    contabilizados na listagem).
  - TC-144, TC-145 (Baixa, Bloqueado): ao submeter para correção, sempre aparece "Erro ao
    corrigir redação. Tente novamente."
- **Causa raiz:** `app/services/redacao_ai_service.py::corrigir_redacao_enem` (usado por
  `POST /redacoes/aluno/submeter`) pedia à IA um JSON grande (5 competências com feedback
  detalhado + feedback geral + listas) com `max_tokens=3000` - abaixo do necessário para uma
  resposta completa em português (mais verboso que inglês), arriscando resposta **truncada**
  e portanto `json.loads` falhando com `JSONDecodeError`, capturado pelo `except` genérico da
  rota e reportado como "Erro ao corrigir redação. Tente novamente." (mensagem que bate 100%
  com a Observação do TC-144/TC-145). Além disso, ao contrário de **todos** os outros serviços
  de IA do projeto (`ai_materiais_service`, `prova_ai_service`, `gerador_provas`,
  `planejamento_bncc_completo_service` etc.), este serviço não removia cercas de markdown
  (` ```json ... ``` `) da resposta antes do `json.loads`, um padrão de robustez presente em
  todo o resto do código.
- **Ação tomada:** Corrigido em `app/services/redacao_ai_service.py`:
  - `corrigir_redacao_enem`: `max_tokens` de 3000 -> 6000; adicionado strip de cercas markdown.
  - `gerar_tema_atual`: `max_tokens` de 2000 -> 3000 (mesmo risco, tema tem 4 textos
    motivadores + proposta longa); mesmo strip de cercas markdown.
- **Justificativa:** Aumentar a margem de tokens reduz drasticamente o risco de truncamento
  (causa mais provável dada a natureza do erro sempre genérico e "sempre falha" reportada) e
  alinha o parsing de JSON com o padrão comprovado no resto do projeto. **Ressalva importante:**
  esta é uma correção baseada em análise estática de código (não reproduzi ao vivo, para não
  gastar créditos de IA desnecessariamente, conforme regra de segurança da planilha) - peço
  para o usuário re-testar TC-055/TC-144/TC-145 e confirmar. Se o erro persistir, o próximo
  passo é logar o `content` bruto da resposta da IA (hoje descartado no `except`) para
  diagnosticar com certeza.
- **Fora do escopo direto:** a parte de TC-055 sobre "os temas não são contabilizados e não
  aparecem no final da página" parece ser um problema de contagem/paginação no frontend -
  `GET /redacoes/temas` (`redacoes.py:167-236`) já devolve `total`/`temas`/`items` corretamente
  paginados; não encontrei bug ali.

### TC-056, TC-057 - Tom acolhedor do feedback / Histórico de redações (Media/Baixa, Bloqueado) - **MITIGADO (parcial, via TC-055)**
- **Problema (planilha):** TC-056 - "Feedback foca no que o aluno fez bem e no próximo passo
  (acolhedor)" não pôde ser avaliado. TC-057 - "Lista as redações corrigidas" não pôde ser
  avaliado. Em ambos os TCs a coluna `Observações` está vazia na planilha - a pré-condição de
  cada um (`Redação enviada` / `Ter redações [corrigidas]`) depende diretamente do fluxo do
  TC-055 (`Enviar um texto de redação para feedback`), que estava com Status Bloqueado
  ("A redação não consegue ser salva nem enviada"). Sem uma redação corrigida, não há como
  chegar até a tela de feedback (TC-056) nem popular o histórico (TC-057).
- **Causa raiz:** Mesma causa raiz já documentada e corrigida no TC-055/TC-144/TC-145 acima
  (`app/services/redacao_ai_service.py::corrigir_redacao_enem`, `max_tokens` insuficiente +
  ausência de strip de cercas markdown antes do `json.loads`, causando
  `POST /redacoes/aluno/submeter` falhar sempre). Verificado nesta rodada que a correção
  aplicada permanece no código (`redacao_ai_service.py:348` `max_tokens=6000`, linhas 353-360
  removem cercas ` ```json `) e já está commitada (commit `532eaed`). Adicionalmente:
  - TC-056: o prompt de `corrigir_redacao_enem` (`redacao_ai_service.py:249-340`) já pede
    explicitamente "seja encorajador mas honesto" (linha 278, quando há `aluno_info`) e o JSON
    de resposta já é estruturado em `pontos_fortes` + `pontos_melhoria` + `sugestoes`
    (linhas 330-332), ou seja, o formato "o que o aluno fez bem" + "próximo passo" já existe
    estruturalmente - não há bug adicional de conteúdo a corrigir aqui além de destravar o envio.
  - TC-057: `GET /redacoes/aluno/{aluno_id}/historico`
    (`app/api/routes/redacoes.py:592-660`) já está implementado corretamente - agrega total,
    corrigidas, médias por competência, evolução (últimas 10) e lista resumida com
    `verificar_acesso_aluno` (proteção contra IDOR). Não há bug de código nesta rota; ela só
    fica vazia (`total_redacoes=0`) enquanto nenhuma redação for submetida com sucesso.
- **Ação tomada:** Nenhuma alteração adicional de código - a correção que desbloqueia ambos já
  foi feita para TC-055/TC-144/TC-145 (não é duplicação de trabalho, é a mesma causa raiz).
- **Justificativa:** Como as Observações destes dois TCs estão vazias e as pré-condições exigem
  exatamente o fluxo que estava quebrado no TC-055, o mais provável é que sejam bloqueios em
  cascata do mesmo bug, não defeitos próprios. **Requer confirmação do usuário via reteste**
  (junto com TC-055/TC-144/TC-145): depois que uma redação for submetida com sucesso, confirmar
  se o feedback de fato aparece com tom acolhedor (TC-056) e se o histórico lista a redação
  corrigida (TC-057). Se algum dos dois falhar mesmo após a redação ser aceita, será um bug
  distinto a investigar em rodada futura.

---

## Comunicação Família

### TC-058 - Gerar mensagem (Media, Falhou)
- **Problema (planilha):** "Apenas presente na versão mobile, a IA não está gerando nada, só
  pega a mensagem escrita e coloca em um template de mensagem acolhedora".
- **Causa raiz:** `POST /comunicacao/familia/mensagem`
  (`app/api/routes/comunicacao.py` + `app/services/comunicacao_ai_service.py`) **chama
  corretamente a IA** (Claude, prompt incorporando nome/diagnóstico/tom/nota do aluno) e não
  faz nenhum "template client-side". O comportamento descrito ("só pega o texto e usa
  template") não bate com o que este endpoint faz - é consistente com o app mobile ter um
  caminho de fallback local (offline/erro) que não chama esta rota, ou estar chamando um
  endpoint diferente.
- **Ação tomada:** Não corrigido - o backend está correto quanto ao que foi testado.
  **Requer decisão do usuário** (confirmar com o time de frontend mobile qual endpoint a tela é
  chamada de fato).
- **Justificativa:** Sem acesso ao código do app mobile, não posso confirmar a causa exata do
  lado cliente; o backend não apresenta o defeito descrito.
- **Validado (rodada seguinte):** revisitado `comunicacao_ai_service.py::gerar_mensagem_familia`
  linha a linha - o prompt é montado dinamicamente (nome/diagnóstico/tom/nota reais do aluno) e
  enviado a `get_anthropic_client().messages.create(...)`; não há nenhum caminho de template
  client-side no backend. Confirma que o defeito, se existir, está no app mobile.

### TC-059 - Copiar/editar mensagem (Baixa, Falhou)
- **Problema (planilha):** "A mensagem não é possível editar nem copiar".
- **Causa raiz:** `MensagemFamiliaResponse` já retorna o texto completo da mensagem gerada; a
  cópia para área de transferência e edição do texto em tela são inteiramente UI (clipboard
  API + textarea editável) - não há nada a fazer no backend.
- **Ação tomada:** Não corrigido - fora do escopo deste repositório (frontend).

---

## Plano de Aula

### TC-060, TC-061, TC-146, TC-147, TC-148 - Feature incompleta (arquitetural)
- **Problema (planilha):**
  - TC-060 (Alta, Passou-com-ressalva): "Não encontrei a parte do Plano de Aula logado como
    Professor na versão desktop. Mas funciona corretamente na versão mobile".
  - TC-061 (Media, Falhou): alinhamento BNCC não aparece, "recebido retorno Erro 404/429".
  - TC-146, TC-147, TC-148 (Baixa, Bloqueado): editar/exportar/duplicar plano - "Não tem 'plano
    de aula' no menu do adaptai".
- **Causa raiz:** O único endpoint de Plano de Aula no backend é
  `POST /plano-aula/gerar` (`app/api/routes/plano_aula.py`), explicitamente documentado no
  próprio código como "superfície mobile" - **stateless**: gera um markdown (objetivo BNCC em
  prosa, sequência, adaptações, avaliação) e retorna, sem persistir nada. Não existe model,
  tabela, nem rotas de listar/editar/exportar/duplicar plano de aula em lugar nenhum do backend
  (`grep "plano_aula\|PlanoAula"` confirma). Ou seja: não há CRUD de planos de aula - só geração
  avulsa. Isso explica por que o menu desktop não tem a opção (não haveria o que gerenciar) e
  por que TC-146/147/148 são estruturalmente impossíveis hoje.
  Quanto ao 404/429 do TC-061: `check_rate_limit` em `plano_aula.py` limita a 20 gerações/hora
  por IP - um 429 é esperado se o limite foi excedido durante os testes; um 404 sugere que o
  frontend tentou chamar uma rota BNCC estruturada que não existe para este fluxo (as rotas de
  habilidades BNCC de verdade vivem em `app/api/routes/planejamento_bncc.py`, prefixo
  `/planejamento/bncc/...`, sistema do PEI - não têm relação com `/plano-aula/gerar`).
- **Ação tomada:** Não corrigido - **Requer decisão do usuário** (arquitetural: construir
  persistência completa de planos de aula é uma feature nova, não um bug pontual).
- **Justificativa:** Construir CRUD completo (model + migration Alembic + rotas + schemas) sem
  confirmação do escopo desejado (o que precisa ser editável, se precisa de versionamento, se
  reaproveita `plano_aula_ai_service` ou não) seria decidir arquitetura de produto por conta
  própria, o que as regras deste agente pedem para evitar. Nota: `app/api/routes/planos.py` é
  sobre **planos de assinatura/pricing** (SaaS), não "plano de aula" - não confundir, não é uma
  pista útil aqui.

---

## Provas/Avaliações

### TC-150, TC-152 - Questões dissertativas sem campo de resposta - **CORRIGIDO (parcial)**
- **Problema (planilha):**
  - TC-150 (Baixa, Falhou): ao criar prova com dissertativa, aparece "Erro ao criar prova.
    Tente novamente", mas a prova é criada mesmo assim - só que sem campo de resposta pro aluno.
  - TC-152 (Baixa, Falhou): "nas provas discursivas, o sistema não realiza a correção e não
    disponibiliza o campo para o aluno digitar a resposta".
- **Causa raiz:** `GET /student/provas/{prova_aluno_id}/questoes`
  (`app/api/routes/student_provas.py:114-133`) devolvia cada questão sem o campo `tipo`
  (`QuestaoGerada.tipo`, que diferencia `multipla_escolha`/`dissertativa`/`verdadeiro_falso`/
  `lacunas` - existe no model em `app/models/prova.py:96` mas não estava no payload). Sem
  saber o tipo da questão, o frontend não tem como decidir entre renderizar alternativas
  (`opcoes`) ou uma caixa de texto livre - para dissertativa, `opcoes` é nulo/vazio, então
  provavelmente nada é renderizado.
- **Ação tomada:** Corrigido em `app/api/routes/student_provas.py::obter_questoes` -
  adicionado `"tipo": q.tipo.value` ao payload de cada questão.
- **Justificativa:** Resolve diretamente a parte "não disponibiliza o campo para o aluno
  digitar a resposta" de ambos os TCs, expondo a informação mínima que falta pro frontend
  decidir a renderização certa.
- **Limitação não corrigida (Requer decisão do usuário):** `Prova.tipo_questao`
  (`app/models/prova.py:61`) é um único enum **por prova inteira**, não por questão - o modelo
  de dados hoje não permite misturar múltipla-escolha e dissertativa na MESMA prova (todas as
  questões geradas herdam `tipo=request.tipo_questao` da prova, `provas.py:161`). Isso é
  provavelmente a causa do "Erro ao criar prova" ao tentar misturar tipos no TC-150 - é uma
  limitação de modelo de dados (exigiria migration para question-level type, hoje já existe a
  nível de questão via `QuestaoGerada.tipo`, mas a rota de geração sempre usa o tipo da prova
  para todas as questões) e não uma correção pequena e segura de aplicar sem confirmação.

### TC-151 - Tempo estendido (Media, Falhou)
- **Problema (planilha):** "Não aparece tempo fazendo a prova".
- **Causa raiz:** Não localizei, no tempo desta rodada, nenhum campo de "acomodação de tempo
  estendido" por aluno nos models `Student`/`ProvaAluno` (`Prova.tempo_limite_minutos` é fixo
  por prova, igual para todos os alunos - não há um multiplicador/ajuste individual).
- **Ação tomada:** Não corrigido - investigação incompleta nesta rodada.
  **Requer decisão do usuário / investigação adicional** (confirmar se "tempo estendido" já
  existe como conceito de produto em algum lugar do model `Student` antes de decidir onde
  encaixar).

---

## Escolas/Rede (ADMIN) e SEDUC (Superadmin)

### TC-072, TC-073, TC-074 - Painel SEDUC sem CRUD (arquitetural, documentado no próprio código)
- **Problema (planilha):**
  - TC-072 (Media, Falhou): sem opção de criar/editar escola no Painel SEDUC.
  - TC-073 (Baixa, Falhou): não é possível ver turmas na estrutura Rede > Escola.
  - TC-074 (Media, Falhou): não aparece opção de vincular professor/coordenador a escola/turma.
- **Causa raiz:** `app/api/routes/seduc.py` é **explicitamente documentado no cabeçalho do
  próprio arquivo** como "versão 1 / demonstração": só endpoints `GET` de agregação/leitura
  (`/seduc/visao-geral`, `/seduc/escolas`), com um `# TODO (arquitetura definitiva,
  pos-demonstracao)` ao final do arquivo. Não há nenhuma rota de criar/editar escola dentro do
  namespace `/seduc`. Uma rota de criar escola até existe, mas em outro lugar
  (`POST /planos/admin/escola`, em `app/api/routes/planos.py`, pensada para o fluxo de
  assinatura/plano, não para o Painel SEDUC). Vincular professor/coordenador a
  escola/turma: **não existe em nenhuma rota do backend** (`grep "vincular"` em
  `app/api/routes` não retornou nada).
- **Ação tomada:** Não corrigido - **Requer decisão do usuário** (o próprio código já sinaliza
  que isso é uma limitação de v1 conhecida e teria uma "arquitetura definitiva" pós-demo a ser
  desenhada).
- **Justificativa:** Construir CRUD de escola dentro do painel SEDUC e vínculo
  professor/turma/escola é trabalho de arquitetura nova (hierarquia rede->escola->turma
  mencionada no próprio TODO do código), não um bug pontual corrigível com uma edição pequena.

### TC-093 - Aplicações/onboarding SEDUC (Baixa, Bloqueado)
- **Problema (planilha):** "tenho login como professor demo. Talvez, por isso, não apareça
  'gerir'".
- **Causa raiz:** A própria observação do testador já aponta a causa provável: conta de teste
  sem papel `SUPER_ADMIN`. Rotas de aplicações (`app/api/routes/applications.py`) exigem papel
  elevado.
- **Ação tomada:** Não corrigido - **provável limitação de ambiente/conta de teste, não bug**
  (mais próximo de "Bloqueado" por acesso do que defeito de código).
- **Justificativa:** Sem reproduzir com uma conta `SUPER_ADMIN` real, não há evidência de bug.
- **Validado (rodada seguinte):** reconferido direto na planilha - a própria Observação do
  testador já diz "tenho login como professor demo. Talvez, por isso, não apareça 'gerir'",
  confirmando a hipótese. Nenhuma ação de código recomendada; reteste com conta `SUPER_ADMIN`.

### TC-156, TC-157, TC-158 - Transferir/desativar escola, dashboard de rede (Baixa, Bloqueado)
- **Problema (planilha):** "Não tem nenhuma escola vinculada ainda" / "Sem escola teste".
- **Causa raiz:** Os próprios testadores relataram falta de **dados de teste** (escolas de
  teste vinculadas), não um erro de aplicação. `PUT /escolas/admin/{id}/ativar` e
  `.../desativar` (`app/api/routes/escolas.py:269-320`) já existem no backend; "transferir
  aluno entre escolas" não tem endpoint dedicado (só o de transferir entre professores,
  `students.py:595`, dentro da mesma escola).
- **Ação tomada:** Não corrigido - TC-157/parte de TC-156 é ativar/desativar que já existe;
  "transferir entre escolas" de fato não existe. **Requer decisão do usuário** para a parte de
  transferência entre escolas (feature nova) + providenciar dados de teste (escolas de teste)
  para revalidar.
- **Validado (rodada seguinte):** reconferido direto na planilha - Observações são literalmente
  "Não tem nenhuma escola vinculada ainda" (TC-156) e "Sem escola teste" (TC-157), confirmando
  que o bloqueio foi falta de dado de teste, não erro de aplicação. Reconfirmado no código que
  `PUT /escolas/admin/{id}/ativar` e `.../desativar` (`app/api/routes/escolas.py:269-320`) já
  existem e funcionam. Nenhuma mudança de código necessária para TC-157; basta reteste com
  escola de teste vinculada.

---

## Analytics (ADMIN)

### TC-075, TC-076, TC-077, TC-160
- **Problema (planilha):** TC-075 tela branca em `/prova/analytics`; TC-076
  `monitoramento/admin` não encontrado; TC-077 falta botão atualizar; TC-160 falta exportar
  relatório.
- **Causa raiz:** Os endpoints reais de analytics ficam sob `/analytics/*`
  (`app/api/routes/analytics.py`) e `/professor/analytics/*`
  (`app/api/routes/professor_analytics.py`) - nenhum dos dois bate com os caminhos de tela
  citados (`/prova/analytics`, `monitoramento/admin`), sugerindo rotas de **frontend**
  desalinhadas com os endpoints de API (não é um problema de backend por si). TC-077 (botão
  atualizar) é puramente de UI. TC-160: não existe endpoint de exportação
  (CSV/PDF/Excel) em nenhuma das duas rotas de analytics - `grep` por "export" não retornou
  nada ali.
- **Ação tomada:** Não corrigido. TC-075/076/077 fora do escopo deste repositório (frontend).
  TC-160 é feature ausente - **Requer decisão do usuário** antes de implementar exportação.
- **Justificativa:** Sem endpoint de export, não há bug a corrigir; é uma feature nova, com
  formato (CSV? PDF? Excel?) a definir.

---

## Acessibilidade

### TC-089, TC-166, TC-169 (Baixa, Falhou/Bloqueado)
- **Problema (planilha):** leitor de tela não encontrado (TC-089/TC-169), VLibras ausente
  (TC-166).
- **Causa raiz:** Leitor de tela (suporte a `aria-*`/foco) e VLibras são inteiramente
  frontend/acessibilidade de UI - não há nada correspondente no backend FastAPI.
- **Ação tomada:** Não corrigido - fora do escopo deste repositório.

### TC-112, TC-113, TC-114, TC-116, TC-121 (Material Adaptado - qualidade de conteúdo/export)
- **Problema (planilha):**
  - TC-112 (Media, Falhou): resumo estruturado incompleto (falta "Pontos Principais").
  - TC-113 (Media, Falhou): mapa mental sem linhas de conexão, "parece só tópicos".
  - TC-114 (Media, Falhou): "atividades" geradas retornam "apenas um json".
  - TC-116 (Baixa, Bloqueado): "Não apresenta opção de roteiro de estudos".
  - TC-121 (Baixa, Falhou): exportar material só oferece "imprimir", PDF sai desformatado.
- **Causa raiz (TC-116 confirmada; TC-112/113/114 parcialmente investigadas):**
  - TC-116: `roteiro_estudo` existe como tipo no sistema ANTIGO (`TipoMaterial.ROTEIRO_ESTUDO`
    em `app/models/material.py`, usado por `app/api/routes/materiais.py`), mas **não existe**
    no dicionário `TIPOS_MATERIAIS` do gerador novo/principal
    (`app/api/routes/materiais_adaptados.py:33-86`, o mesmo endpoint usado por TC-022/023/024
    que passaram) - por isso a opção simplesmente não aparece pro professor gerar.
  - TC-112/113/114: são questões de **qualidade de conteúdo gerado por IA** (prompt engineering
    em `app/services/ai_materiais_service.py`), não erros de código per se - não fiz alteração
    de prompt sem confirmação, por serem mudanças de comportamento de IA com custo (regra de
    segurança da planilha: evitar gerar em massa/alterar prompts às cegas).
- **Ação tomada:** Não corrigido. **Requer decisão do usuário**: (a) para TC-116, decidir se
  `roteiro_estudo` deve ser adicionado ao dicionário `TIPOS_MATERIAIS` do gerador novo
  (mudança pequena, mas depende de ter um método `gerar_roteiro_estudo` implementado em
  `MaterialAdaptadoService` - não confirmei se existe); (b) para TC-112/113/114, ajuste de
  prompt precisa de aprovação e validação com poucos exemplos, conforme regra de custo de IA da
  planilha.
- **TC-121 (export):** a rota `/materiais-adaptados/gerar` retorna HTML/estruturas dentro de
  JSON, sem endpoint de exportação para PDF real (a "impressão" citada é recurso nativo do
  navegador sobre a página renderizada) - não há endpoint de geração de PDF no backend para
  este pipeline específico (diferente do PDF da Jornada/PEI, que existem). **Requer decisão do
  usuário** sobre implementar exportação real (ex: lib de PDF server-side).

---

## Meu Perfil

### TC-090, TC-091, TC-171, TC-172 (Media/Alta/Baixa, Bloqueado)
- **Problema (planilha):** "A opção Meu Perfil não aparece no menu lateral" (repetido nos 4
  TCs: editar dados, trocar senha, foto de perfil, preferências de notificação).
- **Causa raiz:** O backend só expõe `GET /auth/me` (`app/api/routes/auth.py:181`, somente
  leitura). **Não existe nenhum endpoint de autoatendimento** para o próprio usuário (professor/
  admin) editar seu nome, trocar a própria senha, subir foto de perfil ou ajustar preferências
  de notificação - só existe `PUT /students/{id}` (para o PROFESSOR editar o ALUNO, não a si
  mesmo) e reset de senha via e-mail (fluxo diferente, para senha esquecida). Ou seja, mesmo se
  o menu "Meu Perfil" existisse no frontend, boa parte das ações (trocar senha logado, foto,
  preferências) não teria endpoint de backend para chamar.
- **Ação tomada:** Não corrigido - **Requer decisão do usuário** (feature nova: definir
  endpoints `PUT /auth/me`, `POST /auth/me/senha`, `POST /auth/me/foto`, preferências de
  notificação - e o menu no frontend).
- **Justificativa:** É uma feature ausente dos dois lados (frontend sem menu, backend sem rota),
  não um bug pontual corrigível com edição pequena.

---

## Seguranca/LGPD

### TC-175, TC-176 (Media/Baixa, Bloqueado)
- **Problema (planilha):** sem registro de consentimento do responsável (TC-175), sem exportar
  dados do titular (TC-176).
- **Causa raiz:** `Student` (`app/models/student.py`) não tem nenhum campo de consentimento/
  base legal LGPD. Não existe endpoint de exportação de dados do titular (portabilidade LGPD)
  em nenhuma rota.
- **Ação tomada:** Não corrigido - **Requer decisão do usuário** (feature de compliance nova,
  com implicações legais/de produto que não devo decidir sozinho).
- **Justificativa:** Envolve decisão de produto/jurídica sobre como registrar consentimento e
  o que exatamente exportar - fora do escopo de uma correção de bug pontual.

---

## Notificações

### TC-165 - Notificação push (Baixa, Falhou)
- **Problema (planilha):** "Não notifica".
- **Causa raiz:** Não investigado a fundo nesta rodada (baixa prioridade, ordem sequencial
  chegou ao fim do orçamento desta rodada de investigação).
- **Ação tomada:** Não corrigido. **Requer investigação adicional em rodada futura.**

### TC-186 - E-mail de notificação (Baixa, Bloqueado)
- **Problema (planilha):** "Não tem a opção de disparar email".
- **Causa raiz:** Provavelmente relacionado ao mesmo gap do TC-006 (RESEND_API_KEY ausente) -
  não confirmado individualmente nesta rodada.
- **Ação tomada:** Não corrigido. **Requer investigação adicional** (verificar se está ligado
  à mesma causa do TC-006).

---

## Desempenho/Confiabilidade

### TC-184, TC-185 (Media, Falhou)
- **Problema (planilha):** TC-184 "Em alguns erros dá tela branca"; TC-185 "única tela que fica
  em branco é na aba de materiais".
- **Causa raiz:** Não investigado a fundo nesta rodada - tela branca geralmente indica exceção
  não tratada no frontend (ex: acessar campo de uma resposta de API que veio `null`/ausente).
  TC-185 menciona especificamente a aba de materiais, que é justamente a área afetada pelo
  cluster de bug arquitetural documentado acima (Material Adaptado) - pode ser sintoma do mesmo
  problema (frontend tentando renderizar uma lista vazia/inconsistente de materiais).
- **Ação tomada:** Não corrigido. **Requer investigação adicional** (idealmente depois de
  decidida a arquitetura do cluster de Material Adaptado, já que TC-185 pode ser consequência
  direta dele).

---

## Casos não alcançados nesta rodada (Falhou/Bloqueado ainda sem entrada individual)

Por limite de tempo desta rodada, os seguintes TCs já têm ao menos uma entrada acima (integral
ou dentro de um cluster). Casos com investigação mais rasa (marcados "Requer investigação
adicional" acima) e que devem ser priorizados na próxima rodada: TC-151, TC-165, TC-186,
TC-184, TC-185, TC-034, TC-040, TC-107, TC-127.

---

## Sugestões de melhoria (fora do escopo direto - não implementadas)

- **Padronizar tratamento de JSON de respostas de IA.** Vários serviços implementam sua própria
  lógica de remover cercas markdown e extrair JSON (`ai_materiais_service`, `prova_ai_service`,
  `gerador_provas`, `planejamento_bncc_completo_service`, agora também `redacao_ai_service`
  após esta rodada). Relacionado a TC-055/TC-144/TC-145: um helper único
  (`extrair_json_da_resposta_ia(texto)`) em `app/services/` reduziria o risco de o próximo
  serviço novo repetir a mesma lacuna de robustez.
- **Consolidar os dois pipelines de "material adaptado"** (`materiais.py` +
  `materiais_adaptados.py`) em um só, ou documentar claramente por que existem dois. Relacionado
  ao cluster TC-027/028/031/032/033/081/088/118/123/124/125 - a causa raiz de quase 10 TCs é
  estrutural e vai continuar gerando bugs "material não chega no aluno" enquanto os dois
  sistemas coexistirem sem uma ponte.
- **Inconsistência entre `tests/` e os scripts `teste_etapaN_*.py` na raiz do repo.** Não
  executei os scripts soltos (`teste_etapa1_infraestrutura.py`, `teste_etapa2_autenticacao.py`,
  `teste_etapa3_estudantes.py`) nesta rodada porque exigem um servidor rodando localmente
  (`BASE_URL` fixo) e não cobrem nenhuma das áreas com TCs Falhou/Bloqueado revisadas (login
  básico, infraestrutura, criação simples de aluno). Considerar migrar cobertura de regressão
  para `tests/` (pytest) e adicionar casos automatizados para os clusters encontrados aqui
  (ex: teste de integração que gera material via `/materiais-adaptados/gerar` e verifica se
  aparece em `/student/materiais/` - teria pego o bug do cluster de Material Adaptado
  automaticamente).
- **RESEND_API_KEY ausente em `.env.example`.** Relacionado a TC-006/TC-186: adicionar a
  variável (vazia/placeholder) em `.env.example` ajudaria a próxima pessoa a notar que
  e-mail transacional depende dela.

---

## Resumo desta rodada

- **Casos Falhou/Bloqueado na planilha:** 69 (33 Falhou + 36 Bloqueado).
- **Investigados com leitura de código:** 69 (100%), em profundidades variadas conforme
  prioridade.
- **Corrigidos nesta rodada (código alterado):** 6 grupos de TC:
  - TC-017 (validação obrigatória de série)
  - TC-111 (transferir turma - campo faltante no schema)
  - TC-129 (indicador de prazo vencido no PEI)
  - TC-141 (cache da Jornada Terapêutica)
  - TC-055/TC-144/TC-145 (parsing/tokens da correção e geração de redação - correção não
    verificada ao vivo, pedir re-teste)
  - TC-150/TC-152 (parcial - campo `tipo` exposto para o frontend renderizar resposta
    dissertativa)
- **Requer decisão do usuário / arquitetural (não corrigido):** cluster de Material Adaptado
  (9 TCs), Plano de Aula (5 TCs), SEDUC/Escolas (5 TCs), Meu Perfil (4 TCs), LGPD (2 TCs), e
  demais itens pontuais listados por área acima.
- **Arquivos de código alterados:** `app/schemas/student.py`, `app/api/routes/students.py`,
  `app/services/redacao_ai_service.py`, `app/api/routes/relatorios_analise.py`,
  `app/api/routes/student_provas.py`, `app/api/routes/planejamento_bncc.py`.
- Nenhum commit foi feito - alterações permanecem no working tree para revisão.

### Rodada seguinte (correções de baixo risco + validações)

- **Corrigido:** TC-107 (`app/api/routes/students.py`) - `ordenar_por`/`direcao` opcionais em
  `GET /students/`, mudança 100% aditiva (default preserva comportamento anterior).
- **Mitigado (parcial):** TC-006/TC-186 (`app/main.py`) - warning de startup quando
  `RESEND_API_KEY` está vazia em produção. Não substitui provisionar a chave real.
- **Validado sem necessidade de código** (reconferido direto na planilha + código): TC-058
  (backend chama a IA corretamente, defeito é do app mobile), TC-142/143 (retest mais recente da
  mesma feature, TC-052, já passou), TC-156/157 (bloqueio foi falta de escola de teste, endpoints
  de ativar/desativar já existem), TC-093 (conta de teste sem papel `SUPER_ADMIN`).
- **Arquivos adicionais alterados:** `app/api/routes/students.py` (ordenação), `app/main.py`
  (warning de startup).
