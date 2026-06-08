# Roteiro de teste — Logout/Refresh + Pagamento Asaas (sandbox)

Este guia valida, em ambiente de testes, duas entregas recentes:

1. **Logout server-side** (revogação de refresh token).
2. **Pagamento Asaas** (checkout cria cliente + assinatura, webhook ativa a assinatura).

> Endpoints assumem o prefixo `/api/v1`. Ajuste a **porta** para a que o seu
> uvicorn mostrar ao subir (ex.: `8000` ou `8001`). Os exemplos usam PowerShell
> (Windows), que é a forma mais simples de mandar JSON aqui.

---

## 0. Pré-requisitos

1. Backend rodando localmente e conectado ao banco.
2. Rodar uma vez o setup (cria a tabela `revoked_tokens`, entre outras):
   ```
   python setup_modulos_acabamento.py
   ```
   No fim, confira o bloco "5/5 - Conferindo configuracoes": deve listar
   `ASAAS_API_KEY` (definida ou não) e as migrações como concluídas.

---

## 1. Teste do Logout / Refresh (não precisa de Asaas)

Objetivo: depois do logout, o refresh token **não** pode mais gerar access token.

```powershell
$base = "http://localhost:8000/api/v1"   # ajuste a porta

# 1.1 Login (use um usuario que ja existe no seu banco)
$login = Invoke-RestMethod -Method Post -Uri "$base/auth/login/json" `
  -ContentType "application/json" `
  -Body (@{ email = "SEU_EMAIL"; password = "SUA_SENHA" } | ConvertTo-Json)

$refresh = $login.refresh_token
$refresh   # deve imprimir um token

# 1.2 Refresh ANTES do logout -> deve funcionar (200 + novo access_token)
Invoke-RestMethod -Method Post -Uri "$base/auth/refresh" `
  -ContentType "application/json" `
  -Body (@{ refresh_token = $refresh } | ConvertTo-Json)

# 1.3 Logout (revoga o refresh token)
Invoke-RestMethod -Method Post -Uri "$base/auth/logout" `
  -ContentType "application/json" `
  -Body (@{ refresh_token = $refresh } | ConvertTo-Json)

# 1.4 Refresh DEPOIS do logout com o MESMO token -> deve dar 401
try {
  Invoke-RestMethod -Method Post -Uri "$base/auth/refresh" `
    -ContentType "application/json" `
    -Body (@{ refresh_token = $refresh } | ConvertTo-Json)
  Write-Host "FALHOU: o refresh ainda funcionou (nao deveria)" -ForegroundColor Red
} catch {
  Write-Host "OK: refresh recusado apos logout (401 esperado)" -ForegroundColor Green
}
```

**Resultado esperado:** 1.2 retorna token novo; 1.4 cai no `catch` (401
"Sessao encerrada. Faca login novamente.").

No frontend, o mesmo acontece sozinho ao clicar em "Sair" (o `logout()` chama
`/auth/logout` antes de limpar o storage).

---

## 2. Configurar o Asaas (sandbox)

1. Crie uma conta de testes em **https://sandbox.asaas.com** (contas de sandbox
   são aprovadas automaticamente; envie qualquer imagem como documento).
2. No painel sandbox: **Integrações → Chaves de API** → gere a chave
   (começa com `$aact_hmlg_...`). Copie e guarde (ela só aparece uma vez).
3. No `.env` do backend:
   ```
   ASAAS_API_KEY=$aact_hmlg_sua_chave_de_sandbox
   ASAAS_ENV=sandbox
   ASAAS_WEBHOOK_TOKEN=um_token_secreto_que_voce_inventar
   ```
4. **Reinicie o backend** para carregar o `.env`.

> ⚠️ O sandbox envia e-mails de verdade. Use no checkout um e-mail **seu** (que
> você controla), não invente endereços de terceiros.

### Webhook
- Para o Asaas alcançar o seu backend local, é preciso uma **URL pública**.
  Use um túnel (ex.: `ngrok http 8000` ou `cloudflared`) e configure no painel
  sandbox em **Integrações → Webhooks**:
  - URL: `https://SEU_TUNEL/api/v1/checkout/webhook/asaas`
  - Token de autenticação: **o mesmo** valor de `ASAAS_WEBHOOK_TOKEN`.
- Se não quiser montar túnel agora, pule para a **Seção 4** (simula o webhook
  localmente com PowerShell — testa exatamente o mesmo código).

---

## 3. Teste do checkout (cria cliente + assinatura no Asaas)

Faça um cadastro novo pela tela de planos/checkout do AdaptAI (ou chame
`POST /api/v1/checkout/iniciar`). Depois, verifique:

**No painel sandbox do Asaas:**
- Em **Clientes**, deve existir um novo cliente (`cus_...`).
- Em **Assinaturas**, deve existir uma assinatura (`sub_...`) com vencimento
  para daqui ~14 dias (fim do trial) e ciclo mensal.

**No seu banco:**
```sql
SELECT id, escola_id, status, asaas_customer_id, asaas_subscription_id
FROM assinaturas ORDER BY id DESC LIMIT 5;
```
- `status` = `trial`
- `asaas_customer_id` e `asaas_subscription_id` preenchidos.

> Se a chave do Asaas **não** estiver configurada, o checkout ainda cria o trial
> normalmente, só não gera cobrança (campos `asaas_*` ficam nulos). Isso é o
> comportamento esperado (a integração é best-effort).

Anote o `sub_...` e o `cus_...` — você vai usá-los na próxima seção.

---

## 4. Teste da ativação por pagamento

Há dois caminhos. O **4A** é o mais fiel (passa pelo Asaas de verdade) e exige o
webhook acessível (túnel). O **4B** simula o webhook e testa o seu código sem
depender de túnel.

### 4A. Pelo painel (precisa do webhook configurado na Seção 2)
1. No painel sandbox, abra a cobrança gerada pela assinatura.
   (Se ainda não há cobrança por causa do vencimento futuro, use a ação de
   sandbox "Forçar vencimento" ou gere uma cobrança avulsa para o mesmo cliente.)
2. Clique em **CONFIRMAR PAGAMENTO** (disponível para PIX/boleto em sandbox).
3. O Asaas dispara o webhook `PAYMENT_CONFIRMED`/`PAYMENT_RECEIVED` para o seu
   backend.

### 4B. Simulando o webhook localmente (PowerShell)
Use os IDs reais que você anotou na Seção 3:

```powershell
$base = "http://localhost:8000/api/v1"   # ajuste a porta

$body = @{
  event = "PAYMENT_CONFIRMED"
  payment = @{
    id           = "pay_teste_001"
    subscription = "sub_COLE_AQUI"   # o sub_ salvo na assinatura
    customer     = "cus_COLE_AQUI"   # o cus_ salvo na assinatura
    value        = 99.90
    billingType  = "PIX"
    dueDate      = "2026-06-22"
    invoiceUrl   = "https://sandbox.asaas.com/i/teste"
  }
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "$base/checkout/webhook/asaas" `
  -ContentType "application/json" `
  -Headers @{ "asaas-access-token" = "SEU_ASAAS_WEBHOOK_TOKEN" } `
  -Body $body
```

**Resultado esperado:** resposta `{"received": true, "handled": true, "event": "PAYMENT_CONFIRMED"}`.

> Se você definiu `ASAAS_WEBHOOK_TOKEN`, o header `asaas-access-token` precisa
> bater. Com token errado/ausente o endpoint responde **401** (proteção correta).

### Verificações após o pagamento (4A ou 4B)
```sql
-- A assinatura deve ter virado 'ativa'
SELECT status, forma_pagamento, data_proxima_cobranca
FROM assinaturas WHERE asaas_subscription_id = 'sub_COLE_AQUI';

-- Deve existir uma fatura paga
SELECT numero, status, valor, valor_pago, asaas_payment_id
FROM faturas ORDER BY id DESC LIMIT 5;
```
- `assinaturas.status` = `ativa`
- `faturas`: uma linha com `status = paga`, `numero = ASAAS-pay_teste_001`.

**Na interface:** em "Minha Assinatura", o selo de status passa para *Ativa* e o
card "Pagar / Ver cobrança" deixa de aparecer (ele só aparece em
trial/pendente/atrasada).

---

## 5. (Opcional) Outros eventos
Repita o 4B trocando o `event`:
- `PAYMENT_OVERDUE`  → `assinaturas.status` deve ir para `atrasada`.
- `PAYMENT_REFUNDED` ou `PAYMENT_DELETED` → deve ir para `pendente`.

---

## 6. Botão "Pagar / Ver cobrança"
Logado, em "Minha Assinatura", clique no botão. Ele chama
`GET /api/v1/checkout/assinatura/link` e abre o link da cobrança em nova aba.
Durante o trial (sem cobrança gerada ainda) ele mostra um aviso amigável — isso
é esperado.

---

## 7. Virar a chave para produção
Depois de validar tudo em sandbox:
1. Gere a chave de **produção** no painel Asaas (começa com `$aact_prod_...`).
2. No ambiente de produção (ex.: Railway), defina:
   - `ASAAS_API_KEY` = chave de produção
   - `ASAAS_ENV` = `production`
   - `ASAAS_WEBHOOK_TOKEN` = (um novo segredo) e configure o mesmo no painel.
3. Cadastre o webhook de produção apontando para
   `https://SEU_BACKEND/api/v1/checkout/webhook/asaas`.

---

## 8. Troubleshooting rápido
- **401 `invalid_access_token_format`**: a chave veio com espaço/caractere a
  mais, ou está usando chave de produção no sandbox (ou vice-versa).
- **Erro de `User-Agent`**: contas Asaas criadas após 13/06/2024 exigem
  `User-Agent` em toda requisição — o serviço já envia `AdaptAI/1.0`.
- **Webhook não chega**: confira se a URL pública (túnel) está ativa e se o
  token do painel é igual ao `ASAAS_WEBHOOK_TOKEN`.
- **Assinatura não vira "ativa"**: confirme que `payment.subscription`/
  `payment.customer` do webhook batem com `asaas_subscription_id`/
  `asaas_customer_id` salvos na tabela `assinaturas`.
- **Checkout sem `link_pagamento`**: normal durante o trial; a cobrança só é
  gerada perto do vencimento. Use o botão "Pagar / Ver cobrança" mais tarde.
