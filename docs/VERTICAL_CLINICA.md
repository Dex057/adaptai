# Vertical Clínica — ADAPT AI (referência de engenharia)

Gestão clínica multidisciplinar para TEA, construída como um **vertical isolado**
ao lado do vertical Escola já existente, sobre um **kernel compartilhado**. Este
documento é o mapa completo do que foi implementado.

> Estado: implementado e validado por `py_compile` + `@babel/parser`. Falta
> rodar em runtime (ver §10). Repos separados: `backend/` e `frontend/`.

---

## 1. Arquitetura modular (vender separado ou junto)

Regra: **kernel compartilhado + verticais isolados + licenciamento por módulo**.

- **Kernel** (compartilhado): auth, multi-tenant (tabela `escolas` = tenant),
  usuários, conteúdo, ilustrações ARASAAC/IA, Modo Papel (Claude Vision), LGPD.
- **Vertical Escola** (existente): Aluno, Prova, Redação, Material, IDEB.
- **Vertical Clínica** (este): Paciente, PTI, Sessão, Evolução, CAA, Agenda,
  Portal da Família.
- **Regra de isolamento:** `escola/` e `clinica/` **não se importam**; troca via
  kernel ou pela ponte opcional Aluno↔Paciente.

### Entitlement (licenciamento)
- Tabela `escola_modulos(escola_id, modulo ENUM[ESCOLA|CLINICA|INTELIGENCIA], ativo)`.
- `app/core/entitlements.py`: `Modulo`, `modulos_ativos()`, `requer_modulo(Modulo.CLINICA)`
  (dependency que retorna 403 se o tenant não tem o módulo).
- Todo router clínico declara `dependencies=[Depends(requer_modulo(Modulo.CLINICA))]`.
- Camadas: **entitlement** (tem direito ao módulo) > Assinatura/Plano (limites) >
  `core/features.py` (feature flags finos de custo de IA).
- Habilitar num tenant:
  `INSERT INTO escola_modulos (escola_id,modulo,ativo,ativado_em) VALUES (<id>,'CLINICA',1,NOW());`
  ou a tela admin (§7).

---

## 2. Migrations (MySQL, `backend/migrations/`)

| Migration | Tabelas |
|---|---|
| `011_clinica_core.sql` | escola_modulos, profissionais, pacientes, equipe_caso, consentimentos, vinculo_aluno_paciente, auditoria_acesso |
| `012_clinica_pti_sessao.sql` | planos_terapeuticos, objetivos_terapeuticos, sessoes, registros_tentativa, evolucoes |
| `013_clinica_caa.sql` | pranchas, prancha_itens |
| `014_clinica_agenda.sql` | agendamentos |
| `015_clinica_programa_casa.sql` | tarefas_casa, tarefa_casa_check |
| `016_clinica_mensagens.sql` | mensagens_familia |

Padrão: SQL cru, `INT AUTO_INCREMENT`, InnoDB/utf8mb4, ENUM inline em MAIÚSCULO
(= nome do membro que o SQLAlchemy persiste), idempotente, com `SELECT` de
conferência. Aplicar em **homologação** (o `.env` aponta pro banco real).

---

## 3. Modelos (`backend/app/models/`)

- `clinica_core.py` — EscolaModulo, Profissional, Paciente, EquipeCaso,
  Consentimento, VinculoAlunoPaciente, AuditoriaAcesso (+ enums Especialidade,
  Conselho, PapelProfissional, PapelNoCaso, StatusPaciente, TipoConsentimento,
  AcaoAuditoria, ModuloEscola).
- `clinica_terapia.py` — PlanoTerapeutico, ObjetivoTerapeutico, Sessao,
  RegistroTentativa, Evolucao (+ StatusPlanoTerapeutico, StatusObjetivoTerapeutico,
  Presenca, NivelAjuda).
- `clinica_caa.py` — Prancha, PranchaItem (+ TipoPrancha).
- `clinica_agenda.py` — Agendamento (+ StatusAgendamento).
- `clinica_casa.py` — TarefaCasa, TarefaCasaCheck.
- `clinica_mensagens.py` — MensagemFamilia (+ OrigemMensagem).

Todos registrados em `app/models/__init__.py`. Enums com **valor == nome
MAIÚSCULO** para casar com os literais das migrations.

Ciclo de vida do objetivo (mastery): `BASELINE → EM_AQUISICAO → MASTERY →
MANUTENCAO → GENERALIZACAO` (ou `DESCONTINUADO`). Recalculado em
`clinica_sessao._recalcular_status_objetivo` ao confirmar a folha.

---

## 4. API (todas gated por CLINICA, exceto `/tenant/modulos` e `/familia/*`)

**Prontuário — `routes/clinica.py`**
- `POST/GET /clinica/pacientes`, `GET/PATCH /clinica/pacientes/{id}[/status]`
- `POST/GET /clinica/profissionais`
- `POST/GET /clinica/pacientes/{id}/equipe`
- `POST/GET /clinica/pacientes/{id}/planos`, `POST /clinica/planos/{id}/objetivos`
- `POST/GET /clinica/pacientes/{id}/sessoes`
- `POST /clinica/pacientes/{id}/evolucoes`, `POST /clinica/evolucoes/{id}/assinar`
- `POST /clinica/pacientes/{id}/token-familia`
- `GET /clinica/pacientes/{id}/relatorio-evolucao?de&ate` (IA)
- `POST /clinica/pacientes/{id}/pti/sugerir` e `/pti/aplicar` (IA)
- `GET /clinica/pacientes/{id}/auditoria`

**Sessão/Modo Papel/gráfico — `routes/clinica_sessao.py`**
- `GET /clinica/pacientes/{id}/objetivos`
- `POST /clinica/sessoes/{id}/evolucao/rascunhar` (IA)
- `GET /clinica/objetivos/{id}/evolucao` (série do gráfico)
- `GET /clinica/sessoes/{id}/folha-impressao`, `POST .../folha` (Vision),
  `POST .../folha/confirmar` (grava registros + recalcula mastery)

**Agenda — `routes/clinica_agenda.py`**
- `POST/GET /clinica/agendamentos`, `PATCH /agendamentos/{id}/status`,
  `POST /agendamentos/{id}/realizar` (→ cria Sessao)

**Dashboard — `routes/clinica_dashboard.py`**: `GET /clinica/dashboard`

**CAA — `routes/clinica_pranchas.py`**: `GET /clinica/pictogramas`,
CRUD `/clinica/pranchas` + itens

**Programa de casa — `routes/clinica_casa.py`**: CRUD `/clinica/pacientes/{id}/tarefas-casa`

**Mensagens — `routes/clinica_mensagens.py`**: `GET/POST /clinica/pacientes/{id}/mensagens`

**Módulos — `routes/modulos.py`**: `GET /tenant/modulos` (gate do front);
`GET/PUT /tenant/{escola_id}/modulos[/{modulo}]` (require_admin)

**Portal da Família (público, token) — `routes/familia.py`**:
`GET /familia/{token}`, `GET/POST /familia/{token}/tarefas[...]`,
`GET/POST /familia/{token}/mensagens`

---

## 5. Serviços de IA (gancho `@tm.feature`, Anthropic centralizado)

- `pti_service.py` (`F.PTI_RASCUNHO`) — sugere objetivos do contexto/laudo (JSON).
- `evolucao_service.py` (`F.EVOLUCAO_RASCUNHO`) — rascunha nota de evolução.
- `sessao_folha_service.py` (`F.SESSAO_FOLHA_LEITURA`) — lê folha de sessão (Vision).
- `relatorio_evolucao_service.py` (`F.RELATORIO_EVOLUCAO_CLINICO`) — consolida evoluções.

Regra transversal: **a IA só rascunha/transcreve; o profissional revisa e assina.**
Nunca envia nome do paciente à IA (minimização de dado).

---

## 6. Guard de acesso (`services/acesso_clinico.py`)

`verificar_acesso_paciente(db, paciente_id, current_user, acao?, recurso?)`:
- SUPER_ADMIN → ok; ADMIN/COORDINATOR da mesma escola → ok;
- profissional com papel amplo (RT/COORDENADOR/ADMIN_CLINICA) → ok;
- senão, só se estiver na `equipe_caso` ativa do paciente;
- caso contrário **404** (anti-IDOR, não vaza existência).
- Se `acao` informada, grava `auditoria_acesso` (best-effort).

---

## 7. Frontend (`frontend/src/`)

- Gate: `hooks/useModulos.js` (consulta `/tenant/modulos`); menu **Clínica** no
  `components/Layout.jsx` só aparece com o módulo (`temModulo('CLINICA')`).
- Serviço: `services/clinica.js` (todas as chamadas).
- Menu Clínica: **Painel**, **Pacientes**, **Agenda**, **Pranchas (CAA)**, **Módulos**.
- Páginas: ClinicaPainel, ClinicaDashboard (pacientes), ClinicaPacienteDetail
  (PTI/objetivos/sessões/gráfico/programa de casa/mensagens + links PTI-IA,
  Relatório, Auditoria, Link família), ClinicaAgenda, ClinicaPtiIA,
  ClinicaRelatorio, ClinicaAuditoria, ClinicaAdminModulos, ClinicaPranchas,
  PranchaEditor, SessaoFolhaImpressao, SessaoFolhaEnviar, PortalFamilia (público).
- Componente: `components/GraficoEvolucao.jsx` (curva de mastery em SVG inline).

---

## 8. Fluxo principal

Agenda → **Realizar** (cria Sessão) → registrar folha (papel→Vision→revisar→gravar)
ou registrar direto → **IA rascunha evolução** → profissional **assina** →
mastery recalcula → **relatório consolidado** por período. O PTI pode nascer
**sugerido pela IA** a partir do laudo. A família acompanha objetivos, evoluções
assinadas, tarefas de casa e recados pelo **portal (token)**.

---

## 9. LGPD

Dado sensível de saúde: `consentimentos` (tipo TRATAMENTO_DADOS etc., versão do
termo, revogação), `auditoria_acesso` (trilha de quem acessou o prontuário),
minimização (IA não recebe nome). Alertas no dashboard: consentimento ausente.

---

## 10. Validação + commit

```bash
cd backend
python -c "import app.main"                         # erro de import/mapper
pytest tests/test_clinica_models.py tests/test_clinica_services.py tests/test_clinica_acesso.py -q
# aplicar migrations 011→016 em HOMOLOGAÇÃO (não no banco do .env)
```
Frontend: `npm run dev`, habilitar CLINICA no tenant, percorrer os fluxos.

Commit (repos separados, `add` seletivo dos arquivos clínicos; remover
`.git/index.lock` antes): branch `feat/clinica-vertical`.

---

## 11. Roadmap (próximo)

Fase B (receita): convênios TISS/faturamento, assinatura digital, LGPD export.
Fase C (clínico): registro de comportamento (ABC), instrumentos padronizados
(VB-MAPP etc.), supervisão/qualidade ABA, CAA turbinado (histórias sociais IA,
timer, TTS). Fase D: app/PWA do terapeuta, sincronização PEI↔PTI.

## Assinatura digital de evoluções (migration 019)

Ao assinar uma evolução (`POST /clinica/evolucoes/{id}/assinar`), o backend grava
`evolucoes.assinatura_hash` = SHA-256 de `id | texto | assinado_por_id | assinado_em`.
Isso permite comprovar integridade depois: `GET /clinica/evolucoes/{id}/verificar`
recalcula o hash e retorna `{assinada, valido, hash, assinado_em, assinado_por_id}`.
`valido=false` indica que o conteúdo assinado foi alterado no banco.

- Migration: `019_clinica_assinatura.sql` (idempotente, `ADD COLUMN assinatura_hash VARCHAR(64)`).
- Model: `Evolucao.assinatura_hash` (nullable).
- Rotas novas em `clinica.py`: `GET /clinica/pacientes/{id}/evolucoes` (lista) e
  `GET /clinica/evolucoes/{id}/verificar`.
- Frontend: página `ClinicaEvolucoes.jsx` (rota `clinica/paciente/:id/evolucoes`,
  link no cabeçalho do paciente): lista rascunho/assinada, botão Assinar, botão
  Verificar integridade (mostra hash e se confere).
- Ordem de migrations do vertical em homologação passa a ser 011→019.

## Consentimentos LGPD (tabela já existente em 011 — sem migration nova)

Base legal do tratamento/compartilhamento de dados do paciente. A tabela
`consentimentos` (model `Consentimento`, enum `TipoConsentimento`:
TRATAMENTO_DADOS, USO_IMAGEM, COMPARTILHA_ESCOLA, COMPARTILHA_CONVENIO) já
existia desde a 011; faltavam rotas e UI.

- Rotas novas em `clinica.py` (guardadas por `verificar_acesso_paciente`, com auditoria):
  - `GET  /clinica/pacientes/{id}/consentimentos` — lista (mais recente primeiro).
  - `POST /clinica/pacientes/{id}/consentimentos` — registra {tipo, versao_texto, concedido_por}.
  - `POST /clinica/consentimentos/{id}/revogar` — grava `revogado_em` (preserva histórico; 409 se já revogado).
- Frontend: página `ClinicaConsentimentos.jsx` (rota `clinica/paciente/:id/consentimentos`,
  link "Consentimentos" no cabeçalho do paciente): formulário de registro + lista
  com selo Vigente/Revogado e botão Revogar. Serviços em `clinica.js`.
- Não há migration nova; ordem do vertical segue 011→019.

## Enforcement do consentimento no Portal da Família

O Portal da Família (`familia.py`, público via `token_familia`) agora só expõe o
conteúdo clínico (`GET /familia/{token}`) se houver consentimento
`TRATAMENTO_DADOS` **vigente** (não revogado). Sem ele, retorna 403 com mensagem
amigável; a tela `PortalFamilia.jsx` mostra "Compartilhamento ainda não
autorizado. Fale com a clínica." É reversível: a clínica registra o consentimento
e o portal reabre; revoga e volta a bloquear.

- Helpers em `familia.py`: `_tem_consentimento_vigente` e `_exigir_consentimento`.
- Teste: `tests/test_clinica_consentimento.py` (sqlite, sem IA/rede) cobre
  bloqueado→liberado→outro tipo bloqueado→revogado bloqueia.
- Canais tarefas/mensagens não foram bloqueados de propósito (comunicação
  operacional); só o conteúdo clínico exige a base legal.

## Relatório de evolução imprimível / PDF

`ClinicaRelatorioImpressao.jsx` (rota `clinica/paciente/:id/relatorio/impressao`,
FORA do Layout, protegida) gera a versão para enviar/arquivar do relatório
consolidado. O texto revisado chega via router state (botão "Imprimir / PDF" em
`ClinicaRelatorio`); o profissional preenche identificação (paciente, profissional,
registro no conselho, data) e assina. Rodapé traz a base legal (consentimentos
vigentes no momento da emissão). Impressão limpa via `window.print()` (@media print
esconde a toolbar) — serve tanto para papel quanto "Salvar como PDF" do navegador.
Minimização preservada: o nome do paciente não vem do backend, é digitado aqui sob
responsabilidade do profissional. Sem backend novo.

## Faturamento e convênios (migration 020)

MVP de gestão financeira do vertical CLINICA. Duas tabelas novas (não altera
`sessoes`/`pacientes`):
- `convenios`    — fontes pagadoras por tenant (tipo PARTICULAR/CONVENIO/SUS, registro ANS, ativo).
- `faturamentos` — item faturável por competência ('YYYY-MM'), FK opcional para sessão e convênio,
  valor DECIMAL(10,2), status A_FATURAR/FATURADO/PAGO/GLOSADO.

Backend:
- Model `clinica_faturamento.py` (registrado em `app/models/__init__.py`).
- Rotas `clinica_faturamento.py` (gated CLINICA), montadas em `main.py`:
  - `GET/POST /clinica/convenios`, `PATCH /clinica/convenios/{id}` (tenant-scoped, super-admin bypass).
  - `GET/POST /clinica/pacientes/{id}/faturamentos` (acesso via equipe do caso).
  - `PATCH /clinica/faturamentos/{id}/status`.
  - `GET /clinica/faturamento/resumo?competencia=YYYY-MM` — agrega total/recebido/a_receber e por status.

Frontend:
- `ClinicaFaturamento.jsx` (rota `clinica/faturamento`, nav "Faturamento" no grupo Clínica):
  resumo mensal por status, lançamento de item (paciente/valor/convênio) e cadastro de convênios.
- Serviços em `clinica.js`.
- Teste: `test_clinica_models.py` inclui `convenios` e `faturamentos` no metadata esperado.

Ordem de migrations do vertical passa a ser 011→020.

## Faturamento por sessão (migration 021)

Preço padrão por especialidade (por tenant) + geração automática do item de
faturamento ao confirmar a folha de sessão.

- Migration `021_clinica_precos.sql`: tabela `precos_especialidade`
  (escola_id, especialidade, valor; único por escola+especialidade).
- Model `PrecoEspecialidade` (registrado no `__init__`).
- Serviço `faturamento_service.faturar_sessao(db, sessao, criado_por_id)`:
  cria um `Faturamento` para a sessão (dedup por `sessao_id`), competência =
  mês da sessão, valor = preço da especialidade (0 se não configurado),
  status A_FATURAR. Chamado por `confirmar_folha` em modo best-effort
  (nunca derruba a confirmação da folha).
- Rotas: `GET /clinica/precos` (todas as especialidades com valor, 0 default) e
  `PUT /clinica/precos/{especialidade}`.
- Frontend: seção "Preços por especialidade" em `ClinicaFaturamento.jsx`
  (edita e salva no blur). Serviços `listarPrecos`/`definirPreco`.
- Os itens gerados por sessão entram no resumo mensal e na lista do paciente.
- Migrations do vertical: 011→021 (aplicadas automaticamente no deploy).
