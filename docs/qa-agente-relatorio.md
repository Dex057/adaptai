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

> **Nota (rodada de 06/08/2026):** este relatorio deixou de ser so-backend. A rodada
> documentada em [Rodada 06/08/2026](#rodada-06082026---backend--frontend-em-conjunto) teve
> acesso aos tres repositorios (backend `adaptai`, frontend `adaptai-frontend` e a branch
> `fix/qa-correcoes-validadas`) e fechou boa parte dos TCs antes marcados como "fora do escopo
> deste repositorio (frontend)".

---

## Plano de acompanhamento (rodada baseada na coluna "Observações da Revisão")

Releitura da planilha (cópia) mostrou que a coluna `Observações da Revisão` foi editada desde a
última leitura: a maior parte das notas antigas foi limpa, e um subconjunto de TCs recebeu
anotações novas. Esta seção organiza esse subconjunto em planos de ação, por categoria.

### 1. Marcado como corrigido, aguardando reteste

**TC-017 — Criar aluno (validação), Alunos/Turma.** Nota na planilha: *"Corrigido - TESTAR em
app/schemas/student.py (novo StudentCreate.grade_level: str = Field(..., min_length=1,
max_length=50)...) e em app/api/routes/students.py:115 (removido o fallback or 'Não
especificado')"*.
- **Validado no repositório local (nesta rodada):** a correção segue presente e intacta —
  `app/schemas/student.py:15` (`grade_level: str = Field(..., min_length=1, max_length=50, ...)`
  em `StudentCreate`, sobrescrevendo o campo opcional de `StudentBase`) e
  `app/api/routes/students.py:115` (`grade_level=student_data.grade_level`, sem fallback
  `or "Não especificado"`). Nenhuma regressão identificada.
- **Plano de seguimento:** reteste manual do TC-017 (tentar salvar aluno sem informar a série e
  confirmar que a API responde 422 com o campo indicado) para virar `Passou` na planilha. Não
  requer nova ação de código.

### 2. Backend correto, correção pendente é no repositório do front-end

A planilha pede explicitamente **"Liberar acesso ao repositório front-end para correção"** nos
seguintes TCs - já investigados e confirmados nesta e em rodadas anteriores como comportamento
correto no backend:
- **TC-007** (Bloqueio de rota/aluno) - `app/api/dependencies.py` já retorna 401/403 com
  `detail` claro; falta o frontend exibir um aviso antes do redirect.
- **TC-058** (Gerar mensagem, Comunicação Família) - `POST /comunicacao/familia/mensagem` já
  chama a IA corretamente; comportamento de "template" reportado é do app mobile, endpoint a
  confirmar no frontend.
- **TC-059** (Copiar/editar mensagem) - resposta da API já traz o texto completo; falta
  clipboard/textarea editável no frontend.
- **TC-121** (Baixar/exportar material) - backend não tem endpoint de exportação de PDF real
  para este pipeline; a impressão via navegador é o único caminho hoje.
- **Plano de seguimento:** este é um plano de acompanhamento fora do escopo deste repositório
  (é 100% FastAPI/backend). Ação recomendada ao usuário: (a) conceder acesso ao repositório do
  frontend a quem for corrigir esses 4 TCs, citando o TC correspondente em cada PR; (b) não é
  necessária nenhuma mudança adicional de backend para nenhum dos quatro - as APIs já entregam
  o que falta (status/detail no TC-007, texto gerado por IA no TC-058, texto completo no
  TC-059). Único ponto realmente pendente de decisão de arquitetura é o TC-121 (exportação de
  PDF real server-side), que é maior que uma correção de front-end simples.

### 3. Causas raiz já documentadas, sem correção de código pendente (decisão de produto/arquitetura)

Notas de revisão mantidas/atualizadas nesta rodada sem menção de "corrigido", confirmando
causas raiz já eram gaps estruturais e não bugs pontuais (nenhuma ação de código nova aplicada,
consistente com as entradas já existentes mais acima neste relatório por área): TC-006 (e-mail,
RESEND_API_KEY ausente), TC-072 (SEDUC sem CRUD de escola), TC-075 (rota de frontend
desalinhada com `/analytics/*`), TC-089/TC-166/TC-169 (leitor de tela/VLibras, 100% frontend),
TC-090/TC-171 (Meu Perfil, sem endpoint de autoatendimento), TC-112 (qualidade de prompt de IA),
TC-116 (roteiro de estudo ausente no gerador novo), TC-160 (sem endpoint de exportação em
Analytics), TC-175 (sem campo de consentimento LGPD), TC-186 (mesmo gap do TC-006).
- **Plano de seguimento:** nenhum código a alterar sem uma decisão de produto prévia (já
  detalhado por TC nas seções de área abaixo). Sugiro ao usuário priorizar, entre esses, os que
  têm maior prioridade na planilha para a próxima decisão: TC-090/TC-171 (Meu Perfil, 4 TCs
  bloqueados por essa única lacuna) e TC-175 (LGPD, tema sensível/legal).

### 4. Marcados "validar" (usuário pede confirmação/retest, não há nova causa raiz a levantar)

**TC-118, TC-165, TC-184, TC-185** têm a nota "validar" (TC-185: "Validar causa") na coluna de
revisão, sem detalhe adicional de causa raiz.
- **TC-118** (Vários alunos de uma vez, Material Adaptado) - já coberto pelo cluster de Material
  Adaptado (TC-027 etc.) documentado abaixo; "validar" aqui provavelmente significa "confirmar
  se resolve junto com a ponte aluno↔material quando ela for implementada".
- **TC-165** (Notificação push) - aprofundado nesta sessão: confirmado que não existe nenhuma
  infraestrutura de push no backend (só WebSocket para progresso de laudo). "Validar" não muda a
  conclusão: é feature ausente, requer decisão de produto/infra.
- **TC-184, TC-185** (telas brancas) - aprofundado nesta sessão: sem exception handler custom no
  backend que explique respostas inconsistentes; hipótese mais provável é exceção JS não tratada
  no frontend, TC-185 especificamente ligado ao cluster de Material Adaptado.
- **Plano de seguimento:** nenhuma mudança de código adicional recomendada agora. Ação sugerida:
  confirmar com o usuário se "validar" significa "reproduzir de novo em ambiente de teste" -
  nesse caso, o próximo passo é operacional (reteste guiado), não uma investigação de código
  adicional, já esgotada nas rodadas anteriores para esses 4 TCs.

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
- **Aprofundado (rodada seguinte):** revisado `PlanejamentoBNNCService.salvar_planejamento_como_pei`
  (`app/services/planejamento_bncc_service.py:356-420`, chamado por
  `POST /planejamento/salvar-planejamento`) - o PEI é criado corretamente com
  `student_id=student_id` (vindo do `request.student_id`, validado via `verificar_acesso_aluno`
  contra IDOR) e `status="rascunho"`, que já está coberto pelo filtro de `/meu-pei`. Não achei
  nenhum caminho de código em que o `student_id` do PEI divirja do aluno logado, nem nenhum
  ponto em que o `status` seja gravado fora de `["ativo","rascunho"]`. Isso reduz a probabilidade
  da hipótese (a)/(b) e reforça a hipótese (c) como mais provável - a causa mais plausível
  continua sendo o fluxo de criação de objetivo pelo desktop (TC-041/042) falhando
  silenciosamente antes de chegar a este service. Mantido como **Requer decisão do
  usuário/reprodução guiada** - não há edição de código segura a fazer sem reproduzir o passo a
  passo exato do testador (idealmente logando no console do navegador durante a criação do
  PEI/objetivo no desktop).

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
- **Aprofundado (rodada seguinte):** confirmado em `app/models/student.py` (1-62) que não existe
  NENHUM campo relacionado a acomodação/tempo estendido (nem em `profile_data` JSON, que hoje só
  documenta `learning_style`/`support_level`/`interests` como exemplo, sem um campo estruturado
  para isso) e em `app/models/prova.py` que `Prova.tempo_limite_minutos` (linha 65) é único por
  prova - **não existe, em lugar nenhum do schema, um conceito de "tempo adicional por aluno"**.
  Por outro lado, `GET /student/provas/{id}` (`app/api/routes/student_provas.py:76-94`) já expõe
  `tempo_limite_minutos` + `data_inicio`, o suficiente para o frontend montar um cronômetro
  regressivo básico (isso cobriria a leitura mais literal do resultado esperado, "não aparece
  tempo fazendo a prova", se for sobre exibir cronômetro e não sobre acomodação). Mantido como
  **Requer decisão do usuário**: (1) se o problema é "nenhum cronômetro aparece", é gap de
  frontend, dado já existe; (2) se é "tempo estendido por aluno" (o que a pré-condição do TC
  sugere: "Aluno com acomodação"), é feature nova - decidir se o multiplicador fica em
  `Student.profile_data` (JSON, sem migration) ou em coluna dedicada antes de qualquer código.

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
- **Aprofundado (rodada seguinte):** confirmado via `grep` (`push|fcm|onesignal|web_push` em
  `app/`) que o único mecanismo de "tempo real" do backend é
  `app/services/websocket_manager.py` - um `ConnectionManager` usado exclusivamente para
  notificar progresso de processamento de laudo/relatório (`notify_relatorio_progress`,
  `send_progress`/`send_complete`/`send_error`, consumidos por `relatorios_v2.py`). Não existe
  nenhum endpoint de assinatura de push (VAPID/Web Push API), nem integração com FCM/OneSignal/
  APNs, nem tabela para guardar tokens de dispositivo. Ou seja, **notificação push é uma
  feature 100% ausente**, não um bug de uma feature existente - bate com TC-187 (Notificação
  in-app, "sininho") ter **Passou** enquanto TC-165 (push) falha: são mecanismos completamente
  diferentes, e só o in-app existe.
- **Ação tomada:** Não corrigido - **Requer decisão do usuário** (infraestrutura nova: escolher
  provedor de push - Web Push nativo vs FCM/OneSignal -, desenhar armazenamento de
  tokens/assinaturas por usuário, e implementar o disparo nos eventos relevantes). Não é uma
  correção pontual e seria arquitetura de produto nova.

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
- **Aprofundado (rodada seguinte):** conferido `app/main.py` - o projeto **não registra nenhum
  `@app.exception_handler`** customizado (só o `CORSMiddleware`), então qualquer exceção não
  tratada dentro de uma rota já cai no handler padrão do FastAPI/Starlette, que retorna JSON
  `{"detail": "Internal Server Error"}` com status 500 - um formato de erro consistente, não uma
  resposta vazia/quebrada. Isso torna menos provável que o backend esteja devolvendo algo que
  quebre o parser do frontend de forma genérica; reforça a hipótese de que a tela branca é uma
  exceção JS não tratada (React) ao tentar renderizar um campo ausente/`null`, especialmente em
  `GET /student/materiais/` no caso do TC-185 (rota que fica frequentemente vazia por causa do
  cluster de Material Adaptado documentado acima - lista vazia/inconsistente é exatamente o tipo
  de resposta que quebra renderizações que assumem `materiais[0]` etc. sem checar tamanho).
- **Ação tomada:** Não corrigido - fora do escopo deste repositório (frontend), confirmado que
  não há handler de exceção customizado a ajustar no backend para este TC. **Sugestão:**
  adicionar um `@app.exception_handler(Exception)` global no backend só ajudaria a padronizar
  o formato de erro (não resolve a tela branca em si, que é render-side); mais valioso é
  priorizar resolver o cluster de Material Adaptado (TC-027 etc.), que pode eliminar o gatilho
  mais provável do TC-185.

---

## Casos não alcançados nesta rodada (Falhou/Bloqueado ainda sem entrada individual)

Por limite de tempo desta rodada, os seguintes TCs já têm ao menos uma entrada acima (integral
ou dentro de um cluster). Casos com investigação mais rasa (marcados "Requer investigação
adicional" acima) e que devem ser priorizados na próxima rodada: TC-151, TC-165, TC-186,
TC-184, TC-185, TC-034, TC-040, TC-107, TC-127.

**Atualização (rodada de aprofundamento):** todos os 69 TCs Falhou/Bloqueado da planilha já têm
entrada no relatório (confirmado por varredura automatizada TC a TC). TC-107, TC-186 e outros já
citados no início desta rodada (TC-017, TC-111, TC-129, TC-141, TC-055, TC-144, TC-145, TC-150,
TC-152, TC-006) não foram reabertos. Os que estavam marcados "Requer investigação adicional" -
TC-151, TC-165, TC-184, TC-185, TC-034, TC-040 - foram aprofundados nesta rodada (ver seções
"Aprofundado (rodada seguinte)" acima); TC-127 já tinha investigação conclusiva e não precisou de
trabalho adicional. Nenhum bug de código novo, corrigível com segurança, foi encontrado nesse
aprofundamento - todos continuam como feature ausente/decisão de produto (TC-151 tempo estendido,
TC-165 push) ou fora do escopo deste repositório backend (TC-184/185 tela branca, provavelmente
frontend; TC-034/040 aponta mais para o fluxo desktop de criação de objetivo de PEI, TC-041/042,
do que para um bug isolado em `/meu-pei`).

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

### Rodada de aprofundamento (fechar gaps "Requer investigação adicional")

- **Escopo:** varredura completa e automatizada dos 69 TCs Falhou/Bloqueado da planilha
  confirmou que todos já tinham entrada no relatório. Os 7 explicitamente excluídos da
  reinvestigação (TC-017, TC-111, TC-129, TC-141, TC-055/144/145, TC-150/152, TC-107, TC-006,
  TC-186) não foram tocados. O trabalho desta rodada focou nos itens que a rodada anterior
  havia marcado como investigação rasa/incompleta: **TC-151, TC-165, TC-184, TC-185, TC-034,
  TC-040** (TC-127 já estava com investigação conclusiva, não precisou de trabalho adicional).
- **Corrigidos nesta rodada (código alterado):** nenhum. Todos os 6 TCs aprofundados
  confirmaram, com leitura de código adicional, que a causa é feature ausente (TC-151 tempo
  estendido, TC-165 push notification), fora do escopo deste repositório backend (TC-184/185,
  provável exceção não tratada no frontend em `GET /student/materiais/`), ou permanecem sem uma
  causa única localizável no código investigado até agora (TC-034/040 - reforçada a hipótese de
  que o problema está no fluxo de criação de objetivo do PEI pelo desktop, TC-041/042, e não em
  `/meu-pei` em si).
- **Requer decisão do usuário (sem código a alterar com segurança):** TC-151 (schema de
  acomodação de tempo por aluno - onde armazenar: `profile_data` JSON vs coluna dedicada),
  TC-165 (infraestrutura de push notification - provedor, armazenamento de tokens).
- **Requer investigação adicional/reprodução guiada (não é decisão de arquitetura, é falta de
  reprodução):** TC-034/040 (idealmente reproduzir criando um objetivo de PEI pelo desktop e
  conferir se o POST realmente é enviado/persiste), TC-184/185 (idealmente com acesso ao
  console do navegador durante o erro, já que o backend não tem handler de exceção custom que
  explique uma resposta inconsistente).
- **Nenhum arquivo de código foi alterado nesta rodada** - apenas `docs/qa-agente-relatorio.md`
  foi atualizado com as investigações adicionais.

---

# Rodada 06/08/2026 - backend + frontend em conjunto

Primeira rodada com acesso aos **tres** repositorios ao mesmo tempo:

| Repositorio | Caminho | Papel nesta rodada |
|---|---|---|
| Backend | `adaptai` (branch `feature/contador-tokens-ia`) | correcoes aplicadas + testes novos |
| Frontend oficial | `adaptai-frontend` (branch `main`) | base das correcoes novas (branch `fix/qa-rodada-2`) |
| Frontend a11y | `adaptai-frontend-a11y` (branch `fix/qa-correcoes-validadas`) | **auditado, nao modificado** - pendente de merge pelo usuario |

Isso destrava a categoria mais volumosa do relatorio: os TCs repetidamente marcados como
"Backend correto, correcao pendente e no repositorio do front-end" e "fora do escopo deste
repositorio (frontend)". A conclusao central e que **a maioria deles nao era feature ausente -
era contrato desalinhado entre as duas pontas**.

## 1. Auditoria da branch `fix/qa-correcoes-validadas` (nao modificada)

A branch traz ~15 correcoes de QA que ainda **nao estao na `main`**. Cada uma foi conferida
contra o codigo real do backend:

**Validadas - batem com o backend atual:**
- TC-003 (erro de login persistente ate o usuario corrigir os dados) - `Login.jsx`, `StudentLogin.jsx`
- TC-017 (serie obrigatoria no formulario) - bate com `StudentCreate.grade_level` obrigatorio
- TC-107 (ordenacao por nome) / TC-111 (transferir turma) - bate com `StudentUpdate.turma`, ja existente
- TC-049 (filtro de laudos por aluno no servidor, com `size`) - `GET /relatorios/` aceita `student_id` e `size`
- TC-077 (botao Atualizar no Painel SEDUC)
- TC-098 (validacao de expiracao de JWT no cliente + confirmacao com `/auth/me`)
- TC-114 (viewer generico legivel no lugar de JSON cru)
- TC-129 (indicador de prazo vencido no PEI)
- TC-133/135 (`Content-Type: undefined` nos uploads - deixa o axios gerar o boundary do multipart)
- TC-150 (opcao "mista" removida do seletor: **nao existe** no enum `TipoQuestao` do backend -
  era a origem do 422 "Erro ao criar prova")
- TC-152 (textarea para questao dissertativa) - bate com o campo `tipo` ja exposto pelo backend
- TC-166 (widget VLibras) / TC-075 (guarda contra shape incompleto em AlunoDesempenhoDetalhado)
- TC-185 (Error Boundary nas rotas de materiais)

**Dependiam de backend inexistente - resolvido nesta rodada (ver secao 2):**
- `GET /student/materiais-adaptados/` e `/{id}` (TC-027/028): a branch ja consumia essas rotas,
  que **nao existiam**. Como o consumo usa `Promise.allSettled`, a falha era silenciosa: a
  secao "Materiais Adaptados para Voce" simplesmente nunca aparecia.
- `tempo_efetivo_minutos` / `tempo_estendido` em `/student/provas/{id}/questoes` (TC-151): idem,
  campos ainda inexistentes - o cronometro nunca era montado (`tempoEfetivoMin` ficava `null`).

## 2. Correcoes aplicadas no backend (`adaptai`)

### TC-027/028/031/032/033/081/088/118/123/124/125 - "material nao chega no aluno" - **CORRIGIDO**
- **Causa raiz:** ja documentada acima (dois pipelines desconectados). O Portal do Aluno lia de
  `materiais`/`materiais_alunos`; a tela "Criar com IA" grava em `materiais_adaptados_gerados`.
- **Acao tomada:** novo modulo `app/api/routes/student_materiais_adaptados.py`, com
  `GET /student/materiais-adaptados/` (lista) e `GET /student/materiais-adaptados/{id}` (detalhe
  com `resultado_json`), registrado em `app/main.py`.
- **Justificativa da opcao escolhida:** das tres hipoteses levantadas na rodada anterior,
  esta e a de menor risco - **adiciona uma leitura, sem alterar contrato nenhum**.
  `GET /student/materiais/` continua identico, nao ha migration, nao ha duplicacao de dado e
  nao ha backfill (os materiais ja gerados aparecem imediatamente). A alternativa de copiar
  `MaterialAdaptadoGerado` para `Material`/`MaterialAluno` duplicaria dado e exigiria migration.
- **Seguranca:** o `student_id` vem do token, nunca de parametro - a rota nao tem superficie
  para IDOR. Material de outro aluno responde **404** (nao 403), para nao vazar a existencia.
- **Testes:** `tests/test_student_materiais_adaptados.py` (8 casos, incluindo isolamento entre
  alunos e 401 sem token).

### TC-151 - tempo estendido / cronometro na prova - **CORRIGIDO**
- **Causa raiz:** `Prova.tempo_limite_minutos` e unico por prova; nao existia em lugar nenhum do
  schema um conceito de tempo adicional por aluno (confirmado na rodada anterior).
- **Acao tomada:** `calcular_tempo_efetivo()` em `app/api/routes/student_provas.py`, com os
  campos `tempo_limite_minutos`, `tempo_efetivo_minutos`, `tempo_estendido` e `data_inicio`
  expostos em `GET /student/provas/{id}/questoes` e `GET /student/provas/{id}`.
- **Decisao de armazenamento** (o ponto que a rodada anterior deixou em aberto): a acomodacao
  mora em `Student.profile_data` (coluna JSON **ja existente**), nao em coluna dedicada -
  sem migration, e o campo e naturalmente esparso. Duas formas aceitas:
  `{"tempo_estendido": true}` aplica o fator padrao 1.5x; `{"fator_tempo_estendido": 1.75}`
  tem precedencia quando presente.
- **Por que 1.5x:** e a razao usada em avaliacoes brasileiras de larga escala (ENEM/SAEB) para
  candidatos com atendimento especializado - default defensavel ate o produto definir outro.
- **Testes:** `tests/test_tempo_estendido.py` (13 casos). Cobrem explicitamente que um fator
  invalido **nunca reduz** o tempo do aluno, e que `True` (que em Python vale 1) nao e
  confundido com um fator numerico.

## 3. Correcoes aplicadas no frontend (`adaptai-frontend`, branch `fix/qa-rodada-2`)

### TC-184/TC-185/TC-055 - telas brancas - **CORRIGIDO (causa raiz encontrada)**
Esta e a descoberta mais importante da rodada. A hipotese anterior ("excecao JS ao renderizar
campo ausente") estava certa na forma, mas a causa e **unica e sistemica**:

Quatro endpoints passaram a devolver `{items, meta}` (`app/core/pagination.py`) e o frontend
continuou tratando a resposta como array. `data.map`/`data.length`/`data.reduce` lancam
TypeError durante o render; o React desmonta a arvore inteira - **tela branca**.

| Endpoint | Consumidor | Sintoma reportado |
|---|---|---|
| `GET /materiais/` | `MateriaisList.jsx` | TC-185 "unica tela que fica em branco e na aba de materiais" |
| `GET /redacoes/temas` | `RedacoesPage.jsx` | TC-055 "os temas nao sao contabilizados e nao aparecem no final da pagina" |
| `GET /materiais-adaptados/historico/student/{id}` | Dashboard, MateriaisAdaptados, MateriaisAdaptadosAluno | historico truncado (TC-118) |
| `GET /relatorios/` | `RelatoriosList.jsx` | TC-049 (ja corrigido na branch a11y) |

**Correcao importante ao registro anterior:** o relatorio dizia que a tela branca de materiais
ja estava resolvida. **Nao esta na `main`** - o commit `369ddb0` que corrigia exatamente isso
foi revertido por `59daea0`, e a `main` voltou a fazer `setMateriais(data)` com o objeto
paginado. A correcao foi reaplicada nesta rodada.

Em `RedacoesPage` o encadeamento era ainda mais enganoso: `setTemas(response.data)` gravava o
**objeto** no estado e a linha seguinte (`response.data.reduce`) lancava, sendo engolida pelo
`catch` - o erro no console apontava para o `reduce`, mas quem derrubava a tela era o `temas.map`
do render, ja poluido.

- **Acao tomada:** novo `src/utils/pagination.js` com `extrairLista()`/`extrairTotal()`, que
  aceitam os tres formatos que a API pode devolver (array puro, `{items}`, chave legada) e
  **nunca retornam `undefined`**. Aplicado em todos os consumidores acima.
- **Bonus (TC-118):** as chamadas usavam `?limit=100`/`?offset=`, parametros que o backend
  **ignora** (o contrato e `page`/`size`) - o historico vinha silenciosamente truncado em 20
  itens. Trocado por `size`, com `SIZE_MAX = 100` (o teto que o `PaginationParams` aceita).
- **Testes:** 14 asserts sobre os utilitarios (formato novo, chave legada, array puro,
  precedencia de `items`, e entradas invalidas como `null`/string/`{detail: "Not Found"}`).

### TC-007 - aviso de permissao antes do redirect - **CORRIGIDO**
- **Causa raiz (lado frontend):** o backend ja mandava `detail` no 401/403, mas o interceptor
  descartava e fazia `window.location.href = '/login'`. Como e navegacao de pagina inteira,
  qualquer toast em memoria morre antes de ser lido.
- **Acao tomada:** `src/utils/authAviso.js` com dois canais - `sessionStorage` para o aviso que
  precisa **atravessar o redirect** (exibido pelo `Login.jsx`), e `CustomEvent` para o 403 com
  sessao viva (faixa no `Layout.jsx`, sem tirar o usuario da tela). O 403 deixou de ser
  silencioso: antes nao havia tratamento nenhum, so o 401 era interceptado.

### TC-046 - humor/evolucao no Diario - **CORRIGIDO**
`GET /diario-aprendizagem/estatisticas/student/{id}` ja devolvia `por_humor`,
`por_nivel_compreensao` e `registros_por_semana`; a aba Estatisticas so renderizava
total/tempo/media/disciplinas. Os tres dados agora tem visualizacao (barras de humor com
percentual, chips de compreensao e grafico de evolucao por semana). As porcentagens sao
calculadas sobre quem respondeu, nao sobre `total_registros` - humor e compreensao sao
opcionais no registro.

### TC-134 - resumo semanal (IA) - **CORRIGIDO**
Feature 100% pronta no backend (`POST /diario-aprendizagem/resumo-semanal/gerar` e
`GET .../student/{id}`) sem nenhuma entrada na interface - exatamente o "Opcao nao encontrada"
do TC. Nova aba "Resumo Semanal (IA)" lista o historico ao abrir e gera **so por clique
explicito**, para nao disparar custo de IA sem intencao.

### TC-151 (frontend) - acomodacao no cadastro do aluno - **CORRIGIDO**
Nova secao "Acomodacoes em Avaliacoes" no `StudentForm`, gravando em `profile_data`. O PUT
preserva as demais chaves de `profile_data`, para que salvar o aluno aqui nao apague dados de
outras telas. O cronometro que consome isso ja existe na branch `fix/qa-correcoes-validadas`.

### TC-127 - historico do PEI - **CORRIGIDO (parcial)**
Correcao ao registro anterior: a aba "Historico" **ja existia** e ja consumia
`/planejamento/pei/{id}/historico`. O que faltava era que a tela descartava `valor_antigo` e
`valor_novo` de cada ajuste - ou seja, o "ver anteriores" do TC estava na resposta e nao era
exibido. Agora mostra `valor anterior -> valor novo` e o tipo do ajuste. Se "historico" no
sentido do TC for snapshot completo versionado, isso continua sendo decisao de produto.

### TC-059 - copiar/editar mensagem da familia - **NAO APLICAVEL a este repositorio**
Varredura por `comunicacao`/`familia` em `adaptai-frontend/src` nao encontrou **nenhuma** tela
de Comunicacao Familia - o que confirma a observacao do TC-058 ("apenas presente na versao
mobile"). Nao ha o que corrigir aqui: construir a tela do zero seria feature nova, no
repositorio errado. **Acao recomendada:** direcionar TC-058/TC-059 ao repositorio do app mobile.

## 4. Validacao executada

- **Backend:** `pytest tests/` - **106 passaram** (85 antes, +21 novos desta rodada).
- **Frontend:** `npm run build` (vite) - sucesso, 2674 modulos, sem erro.
- **Utilitarios de paginacao:** 14 asserts, todos passando.
- **Lint do frontend:** nao executado na `main` - **nao existe arquivo de configuracao de
  ESLint nesse branch**. O `.eslintrc.cjs` foi adicionado pela branch `fix/qa-correcoes-validadas`
  (junto com `eslint-plugin-jsx-a11y`), entao o gate de lint so passa a existir apos o merge dela.

## 5. Situacao dos TCs apos esta rodada

**Corrigidos e prontos para reteste:** TC-007, TC-027, TC-028, TC-031, TC-032, TC-033, TC-046,
TC-055, TC-081, TC-088, TC-118, TC-123, TC-124, TC-125, TC-127 (parcial), TC-134, TC-151,
TC-184, TC-185.

**Continuam exigindo decisao de produto (sem mudanca segura de codigo):**
- TC-060/061/146/147/148 - CRUD de Plano de Aula (feature nova: model + migration + rotas)
- TC-072/073/074 - CRUD do Painel SEDUC (o proprio codigo marca como v1/demonstracao)
- TC-090/091/171/172 - Meu Perfil (ausente dos dois lados: sem menu e sem endpoint de autoatendimento)
- TC-165 - push notification (infraestrutura inexistente: provedor, tokens de dispositivo)
- TC-175/176 - LGPD (consentimento e portabilidade; implicacao juridica)
- TC-160/121 - exportacao (Analytics e material adaptado): definir formato antes
- TC-112/113/114 - qualidade do conteudo gerado por IA (ajuste de prompt, com custo)
- TC-006/186 - `RESEND_API_KEY` precisa ser provisionada (nao ha correcao de codigo possivel)

**Continuam exigindo reproducao guiada:** TC-034/040 (PEI nao aparece para o aluno - a hipotese
mais forte segue sendo o fluxo de criacao de objetivo pelo desktop, TC-041/042).

**Redirecionados para o repositorio mobile:** TC-058, TC-059.

## 6. Onde esta o codigo

| Repositorio | Branch | Estado |
|---|---|---|
| `adaptai` (backend) | `feature/contador-tokens-ia` (branch em que o repo ja estava) | alteracoes no working tree, sem commit |
| `adaptai-frontend` | `fix/qa-rodada-2` (criada a partir de `main`) | alteracoes no working tree, sem commit |
| `adaptai-frontend-a11y` | `fix/qa-correcoes-validadas` | **intacta** - auditada, nao modificada |

As duas branches de frontend sao independentes e nao foram mescladas. Ha sobreposicao de arquivo
(nao de linha, na maior parte) em `StudentForm.jsx`, `Login.jsx` e `PEIGerenciamento.jsx` -
esperar conflito pequeno e resolvivel ao juntar as duas.

---

# Rodada 07/08/2026 - validacao SO-BACKEND (sem acesso ao frontend)

**Escopo imposto pelo usuario:** analisar exclusivamente `adaptai` (backend FastAPI). O
repositorio de frontend NAO foi aberto nesta rodada (instrucao do `CLAUDE.md` de checar os dois
lados foi explicitamente suspensa). Objetivo: **validar**, nao implementar - conferir se o
backend descrito nas rodadas anteriores realmente existe, esta registrado e serve o contrato
esperado. Nenhum arquivo de codigo foi alterado.

**Metodo de validacao (alem da leitura de codigo):**
- `pytest tests/` -> **106 passaram** (nenhuma regressao das rodadas anteriores).
- Enumeracao real das rotas via `app.main:app.routes` (nao so `grep`), para provar registro e
  prefixo `/api/v1` em vez de assumir pelo arquivo existir.
- Conferencia cruzada `app/core/config.py` x `.env.example` x uso real das settings.

## 1. Confirmado OK e servindo (backend implementado, registrado, contrato coerente)

| TC | Evidencia |
|---|---|
| TC-027/028/031/032/081/088 | `app/api/routes/student_materiais_adaptados.py:26,31,64`; registrado em `app/main.py:37,382`; rotas reais `/api/v1/student/materiais-adaptados/` e `/{material_id}`. Isolamento pelo token (`get_current_student`), material de outro aluno = 404. `tests/test_student_materiais_adaptados.py` passa. |
| TC-151 | `app/api/routes/student_provas.py:32` (`calcular_tempo_efetivo`), campos `tempo_efetivo_minutos`/`tempo_estendido`/`data_inicio` expostos em `:122-142` e `:182-191`. Escrita da acomodacao viavel: `profile_data` esta em `StudentUpdate` (`app/schemas/student.py:35`) e o model tem a coluna JSON (`app/models/student.py:34`) - **sem migration necessaria**. `tests/test_tempo_estendido.py` passa. |
| TC-017 | `app/schemas/student.py:15` (`grade_level` obrigatorio em `StudentCreate`) intacto. |
| TC-107 | `app/api/routes/students.py:141-144,188-189` (`ordenar_por`/`direcao` com `Literal`). |
| TC-111 | `app/schemas/student.py:32-33` (`turma`/`matricula` em `StudentUpdate`); coluna existe (`app/models/student.py:27-28`). |
| TC-141 | `app/api/routes/relatorios_analise.py:20,218-219,263` (cache de IA via `_hash_prompt`/`lookup_cache`/`save_cache`, TTL 30 dias). |
| TC-055/145 | `app/services/redacao_ai_service.py:354` (`max_tokens=6000`) e `:358-366` (strip de cercas markdown). |
| TC-134 | `POST /api/v1/diario-aprendizagem/resumo-semanal/gerar` e `GET .../student/{id}` existem e estao registrados (`diario_aprendizagem.py:376,420`). |
| TC-046 | `GET /api/v1/diario-aprendizagem/estatisticas/student/{id}` (`diario_aprendizagem.py:539`) + `/timeline/student/{id}` (`:652`). |
| TC-006 (parcial) | Warning de startup presente (`app/main.py:88-92`). O envio em si continua dependendo de segredo (ver divergencia D1). |

## 2. Divergencias concretas encontradas nesta rodada (novo)

### D1 - `RESEND_API_KEY`, `EMAIL_FROM` e `FRONTEND_URL` ausentes do `.env.example` (TC-006, TC-186)
As tres settings existem em `app/core/config.py:123,124,126` e sao lidas em runtime
(`app/services/email_service.py:26,38`; `app/api/routes/auth.py:459`), mas **nenhuma das tres
aparece em `.env.example`**. A sugestao da rodada anterior nao foi aplicada.

Agravante ainda nao registrado: `FRONTEND_URL` tem default `http://localhost:5173`
(`config.py:126`) e e usada para montar o link de redefinicao em
`auth.py:459` (`f"{settings.FRONTEND_URL.rstrip('/')}/redefinir-senha?token={token}"`). Ou seja,
**mesmo provisionando `RESEND_API_KEY`, o TC-006 continua falhando** se `FRONTEND_URL` nao for
setada em producao: o e-mail chega com um link apontando para `localhost`. Nao ha nenhum warning
de startup para esse caso (o warning de `main.py:88` cobre so a chave do Resend).

### D2 - A ponte de material adaptado e SO-LEITURA (TC-033, TC-123, TC-124)
A rodada anterior listou TC-033/123/124 como "corrigidos e prontos para reteste". **Nao estao.**
`MaterialAdaptadoGerado` (`app/models/material_adaptado_gerado.py:11-38`) nao tem nenhuma coluna
de interacao do aluno - nao existe `favorito`, `lido`/`data_primeira_visualizacao` nem
`anotacoes_aluno`. Esses campos existem apenas em `MaterialAluno`
(`app/models/material.py:73-80`), do pipeline antigo, e os unicos endpoints de interacao
(`POST /student/materiais/{material_aluno_id}/favorito` e `/anotacoes`,
`app/api/routes/student_materiais.py:123,148`) operam por `material_aluno_id`.

Resultado pratico: com a ponte nova, o aluno **ve e abre** o material (TC-027/028/031/032 OK),
mas **nao consegue favoritar (TC-033), marcar como lido (TC-123) nem anotar (TC-124)** - nao ha
endpoint para isso nesse pipeline. Fechar esses tres exige migration (colunas novas em
`materiais_adaptados_gerados` ou uma tabela de interacao) - **requer decisao do usuario**.

### D3 - Nao existe conceito de "disponibilizar" material adaptado (TC-027)
O resultado esperado do TC-027 diz "aparece na lista do aluno (**status disponivel**)". O
pipeline antigo tem esse controle (`Material.status == DISPONIVEL` + `MaterialAluno`), o novo
nao: `MaterialAdaptadoGerado` nao tem coluna `status`, entao a ponte expoe ao aluno **tudo** que
o professor gerar, no instante em que gerar. Funcionalmente o TC passa; conceitualmente o
professor perdeu o controle de curadoria (inclusive sobre rascunhos/tentativas descartadas).
**Requer decisao de produto**, nao e bug de codigo.

### D4 - `alembic/versions/` esta VAZIO e `docs/migrations.md` nao existe
`app/main.py:62-66` pula `Base.metadata.create_all` em producao ("use Alembic para migrations"),
mas `alembic/versions/` nao tem **nenhuma** migration (o proprio `alembic/README_ADOCAO.md`
admite: "onde as migrations vao morar (vazia ainda)"). Consequencia: em producao, hoje, **nenhuma
coluna ou tabela nova chega ao banco** - nem por `create_all` (desligado) nem por Alembic (sem
versao). Os `migrations/*.sql` avulsos nao cobrem `materiais_adaptados_gerados` (grep por
`CREATE TABLE` nos 6 arquivos nao retorna essa tabela).

Isso **nao bloqueia** TC-027 nem TC-151 (ambos usam tabela/coluna preexistentes - foi uma boa
decisao de projeto), mas bloqueia qualquer correcao futura que precise de schema novo, incluindo
D2 (interacoes do aluno), TC-175 (consentimento LGPD) e TC-150 (tipo por questao).
Alem disso, `app/main.py:61` referencia `docs/migrations.md`, arquivo que **nao existe** em
`docs/`.

### D5 - `analytics.py` usa ownership por criador, ignorando escola (TC-075, TC-076)
`app/api/routes/analytics.py:24-27,225-228,` filtra por `Student.created_by_user_id ==
current_user.id`, em vez do helper canonico `verificar_acesso_aluno`
(`app/api/dependencies.py:185-225`), que respeita SUPER_ADMIN e ADMIN/COORDINATOR por
`escola_id`. Efeito: um **admin ou coordenador** recebe 404/lista vazia nos analytics de alunos
criados por professores da propria escola - compativel com o sintoma "tela branca / sem dado"
do TC-075/TC-076 mesmo que o frontend chame o endpoint certo.

### D6 - Nao existe endpoint de metricas agregadas de escola para ADMIN (TC-076)
O TC-076 espera "metricas agregadas da escola". `GET /api/v1/analytics/dashboard`
(`analytics.py:141-201`) e **por usuario** (todos os filtros sao `== current_user.id`), e
`/api/v1/admin/*` (`admin_monitoring.py:29,42,58,110,117,286`, todos com `require_admin`) sao
metricas de **infraestrutura** (cache de IA, background tasks, consumo de tokens), nao de escola.
O unico agregado real e `/api/v1/seduc/visao-geral`, que e visao de rede. Conclusao revisada em
relacao a rodada anterior: **TC-076 nao e so desalinhamento de rota de frontend - o endpoint que
serviria o caso nao existe.**

### D7 - TC-144 nao e servido pelo contrato atual (redacao curta)
Resultado esperado: "Avisa que e curto / pede mais texto". O que o backend faz hoje:
- `< 50 caracteres` -> `app/schemas/redacao.py:60` (`min_length=50`) gera **422 generico** do
  Pydantic, sem mensagem de "escreva mais";
- `>= 50 caracteres mas < 50 palavras` -> `app/services/redacao_ai_service.py:272-273` chama
  `_redacao_anulada("Texto muito curto (menos de 50 palavras)")`, que retorna **200 com nota 0**
  (`:406-414`) - a redacao e **anulada**, nao devolvida para o aluno complementar.

Ou seja, o TC-055/145 (correcao funcionando) foi corrigido, mas o TC-144 especificamente tem
semantica divergente do esperado. Correcao possivel e pequena (validar antes e responder 400 com
mensagem propria), mas muda contrato de resposta - **nao aplicada nesta rodada** por ser rodada
de validacao.

### D8 - `prazo_vencido` existe em UM unico endpoint (TC-129)
`grep -rn "prazo_vencido" app/` retorna exatamente uma ocorrencia:
`app/api/routes/planejamento_bncc.py:257` (`GET /planejamento/pei/{pei_id}/completo`). Os demais
endpoints que devolvem objetivos de PEI (`/planejamento/pei/{pei_id}/resumo`,
`/planejamento/pei/aluno/{student_id}`, e `ObjetivoResumo` em
`app/api/routes/student_pei.py:116-127`) **nao trazem o campo**. Se a tela do TC-129 consumir
qualquer um desses, o indicador continua invisivel mesmo com a correcao aplicada.

### D9 - `GET /student/meu-pei` responde 200 com corpo `null` (TC-034/TC-040, TC-184/TC-185)
`app/api/routes/student_pei.py:59,73-74`: `response_model=Optional[PEIResumo]` e `return None`
quando nao ha PEI. Um cliente que faca `pei.objetivos` sobre `null` lanca TypeError - exatamente
o padrao de tela branca do TC-184/TC-185. O contrato mais defensivo seria 404 ou um objeto de
estado vazio. Nao alterado (mudanca de contrato, **requer decisao do usuario**), mas e a hipotese
mais concreta ja levantada para TC-034 do lado do backend.

### D10 - `app/api/routes/exam.py` nao esta registrado
O modulo declara `APIRouter(prefix="/exam")` (`exam.py:15`) mas nao e importado nem incluido em
`app/main.py` - nenhuma rota `/api/v1/exam/*` existe no app em execucao (confirmado pela
enumeracao de `app.routes`). Nao ha TC apontando para ele; registrado aqui so como codigo morto
que confunde investigacao futura. **Fora do escopo direto** - nao remover sem confirmacao.

## 3. Reconfirmado: backend ausente (feature nova, sem regressao)

- **TC-090/091/171/172 (Meu Perfil):** so existe `GET /api/v1/auth/me` (`auth.py:181`). Nao ha
  `PUT /auth/me`, troca de senha logado nem upload de foto de usuario (a rota
  `/students/{id}/foto` e do ALUNO, `students.py:716`).
- **TC-072/073/074 (SEDUC):** `seduc.py` expoe **apenas** `/seduc/visao-geral` e `/seduc/escolas`
  (`:62,185`), ambos GET. Sem CRUD de escola, sem turmas, sem vinculo professor/coordenador.
- **TC-060/061/146/147/148 (Plano de Aula):** unica rota e `POST /api/v1/plano-aula/gerar`
  (`plano_aula.py:15`), stateless, rate limit 20/h (`:26-29`) - o 429 do TC-061 e esperado; o 404
  e chamada a rota inexistente. Sem model, sem persistencia, sem editar/exportar/duplicar.
- **TC-116 (Roteiro de estudo):** ausente de `TIPOS_MATERIAIS`
  (`materiais_adaptados.py:33-86`) **e** sem metodo gerador correspondente em
  `app/services/ai_materiais_service.py` (grep por `roteiro` so acha HQ/tirinha e experimento).
  Confirma que **nao e** uma linha de dicionario: exige prompt novo (custo de IA).
- **TC-118 (varios alunos de uma vez):** `MaterialRequest.student_id: int`
  (`materiais_adaptados.py:25`) e singular - o backend nao aceita lote. Falso na sinalizacao
  anterior de "resolve junto com a ponte": a ponte resolveu a entrega, nao a geracao em lote.
- **TC-121/142/143/147/160 (exportar PDF/planilha):** **nao existe nenhum endpoint que GERE
  PDF** em todo o backend - as unicas ocorrencias de `application/pdf` sao validacao de
  **upload** (`pei.py:60,171`, `relatorios.py:103,528,708`). Toda exportacao hoje e client-side.
- **TC-150/152 (dissertativas):** `Prova.tipo_questao` (`app/models/prova.py:61`) e um enum unico
  por prova e todas as questoes herdam dele (`provas.py:161`); `TipoQuestao` nao tem valor
  "mista" (`prova.py:27-32`). Prova de tipos misturados e impossivel no modelo atual. Alem disso,
  em `student_provas.py:235-241` a dissertativa e gravada com `esta_correta=None` e
  `pontuacao_obtida=0` e **nada** corrige depois - uma prova 100% dissertativa sempre fecha com
  nota 0/reprovado (`finalizar`, `:307-313`). TC-152 continua **nao atendido** para discursivas.
- **TC-165 (push), TC-175/176 (LGPD):** sem infraestrutura de push e sem nenhum campo/endpoint de
  consentimento ou portabilidade (grep por `consent`/`notificac` em `app/models` e
  `app/api/routes` nao retorna nada de aluno). Notar que TC-187 ("notificacao in-app", marcado
  Passou) tambem **nao tem backend** - o sininho e inteiramente frontend.

## 4. Descartados nesta rodada por serem puramente frontend/UI

TC-059 (copiar/editar texto - clipboard/textarea), TC-077 (botao Atualizar), TC-089 e TC-169
(leitor de tela / texto alternativo), TC-166 (widget VLibras). Listados sem investigacao de
codigo, conforme instrucao do escopo.

## 5. Conclusao da rodada

Nenhum arquivo de codigo foi alterado (rodada de validacao). Nenhuma regressao encontrada: todas
as correcoes das rodadas anteriores continuam no lugar e os 106 testes passam. As duas
divergencias que mais mudam o quadro anterior sao **D2** (TC-033/123/124 estavam marcados como
corrigidos e nao estao) e **D4** (sem migration versionada, qualquer correcao futura que precise
de schema nao chega a producao).

---

# Rodada 07/08/2026 (b) - implementacao das divergencias validadas

Escopo: so backend, sem consultar o repositorio de frontend. Cada achado da rodada de
validacao anterior foi reconferido no codigo antes de virar codigo novo. O item de
variaveis de ambiente (TC-006/186, D5) ficou **deliberadamente de fora** a pedido do
usuario. O detalhamento do que muda em producao esta em
`docs/deploy-rodada-implementacao.md`.

Suite: **122 testes passam** (eram 106; 16 novos). Nenhuma regressao.

## Confirmado e corrigido

| # | TC | Divergencia confirmada | Correcao |
|---|---|---|---|
| D2 | 033/123/124 | ponte era so leitura; sem coluna para favorito/lido/anotacao | migration `007`, 4 colunas em `materiais_adaptados_gerados` + 3 endpoints POST |
| D1 | 152 | prova 100% discursiva fechava nota 0 e nada corrigia depois | denominador so com o ja corrigido; `POST /provas/aluno/{id}/corrigir-questao` |
| D3 | 075 | `analytics.py` usava regra de professor para todo mundo | 3 endpoints migrados para `verificar_acesso_aluno` |
| D9 | 034/040 | `GET /student/meu-pei` respondia 200 com corpo `null` | resposta sempre objeto, com `tem_pei: false` |
| D6 | 144 | texto entre 50 chars e 50 palavras era anulado com nota 0 | 400 legivel antes de persistir e antes de gastar IA |
| D8 | 129 | `prazo_vencido` existia em um unico endpoint | regra centralizada em `app/utils/pei_prazos.py`, aplicada em 4 lugares |
| — | 150 (parcial) | `provas.py` gravava o tipo da PROVA em toda questao | passa a gravar o tipo que a questao tem, com fallback validado |

## Achado novo desta rodada (nao estava na planilha)

`app/api/routes/provas.py:515` tinha a mesma falha que `student_provas.py` ja havia
corrigido: `questao.resposta_correta.strip()` com `resposta_correta = None` (dissertativa)
levanta AttributeError e derruba `POST /provas/corrigir` inteiro em 500. Corrigido junto
com o TC-152, porque e a mesma causa.

## Confirmado e NAO implementado (com motivo)

- **TC-118 (geracao em lote):** exige N chamadas de IA por requisicao - decisao de
  produto com custo direto. `MaterialRequest.student_id` segue singular.
- **TC-150 (prova mista de verdade):** o prompt em `prova_ai_service.py:159` fixa um unico
  `tipo` para todas as questoes. Mudar isso e mudar prompt de IA, o que o CLAUDE.md exige
  validar antes. A metade segura (persistir o tipo real de cada questao) foi feita.
- **TC-076 (metricas agregadas de escola):** endpoint inexistente, nao divergencia. Sem o
  enunciado exato das metricas esperadas, implementar seria inventar contrato.
- **TC-006/186 (env vars):** adiado a pedido do usuario.
- **D4 (`alembic/versions/` vazio):** segue vazio. A migration `007` foi escrita no padrao
  `.sql` que o projeto ja usa (`migrations/00X_*.sql`), aplicada a mao. **Esta e a
  dependencia critica do TC-033/123/124 em producao.**
- **D10 (`exam.py` codigo morto):** nao removido - continua fora do escopo, sem TC.
