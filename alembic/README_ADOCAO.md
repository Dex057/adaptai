# Alembic no AdaptAI — guia de adoção

Este projeto passou a versionar o schema do banco com **Alembic**. Antes, o
schema era criado por `Base.metadata.create_all` (dev) + arquivos SQL avulsos
(`migrations/*.sql`) + scripts Python ad-hoc — sem histórico reproduzível.
A partir de agora, **toda alteração de schema vira uma migration versionada**.

> ⚠️ **O banco de produção já existe.** NÃO se pode rodar `create_all` nem um
> baseline que recrie tabelas sobre ele. O procedimento abaixo adota o Alembic
> sem tocar nos dados, usando o padrão *baseline + stamp*.

---

## O que já está pronto (commitado)

- `backend/alembic.ini` — config; a URL do banco vem das `settings` do app (sem segredo aqui).
- `backend/alembic/env.py` — ligado ao `app.core.config.settings.db_url` e ao `Base.metadata` (importa todos os models).
- `backend/alembic/script.py.mako` — template das migrations.
- `backend/alembic/versions/` — onde as migrations vão morar (vazia ainda).
- `alembic==1.13.1` adicionado ao `requirements.txt`.

---

## Passo a passo da adoção (rodar UMA vez)

Tudo a partir de `backend/` com o venv ativo.

### 1. Instalar
```bash
cd backend
pip install -r requirements.txt
```

### 2. Gerar o baseline a partir de um banco VAZIO
O baseline precisa conter o `CREATE TABLE` de tudo, para que instalações novas
(dev de um colega, staging) consigam subir o schema do zero com `alembic upgrade head`.
Por isso ele é gerado contra um banco **vazio**, não contra o de produção.

```bash
# 2a. Crie um banco MySQL vazio só para gerar o baseline. Ex.:
#     CREATE DATABASE adaptai_baseline CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

# 2b. Aponte temporariamente para ele (NÃO use o banco real aqui):
set DATABASE_URL=mysql+pymysql://USER:SENHA@HOST:3306/adaptai_baseline?charset=utf8mb4   # Windows (cmd)
# $env:DATABASE_URL="mysql+pymysql://..."   # PowerShell

# 2c. Gere o baseline (autogenerate compara os models com o banco vazio):
alembic revision --autogenerate -m "baseline_schema"
```
Isso cria um arquivo em `alembic/versions/`. **Abra e revise.** O autogenerate
é um rascunho: confira se todas as tabelas e colunas estão lá, e remova
qualquer ruído (ex.: defaults/índices que o MySQL nomeia diferente).

### 3. Marcar os bancos REAIS como já estando no baseline
Os bancos que já têm as tabelas (produção e seu dev real) **não** devem rodar o
baseline — eles só precisam ser "carimbados" como já aplicados:

```bash
# Aponte para o banco REAL (prod ou dev) via DATABASE_URL e:
alembic stamp head
```
Pronto. O Alembic agora sabe que aquele banco está na revisão baseline, sem ter
recriado nada.

### 4. Fim do baseline
Pode dropar o `adaptai_baseline`. A partir daqui o fluxo é o normal abaixo.

---

## Fluxo normal (toda alteração de schema, daqui pra frente)

```bash
cd backend
# 1. Altere o model (ex.: novo campo em app/models/student.py)
# 2. Gere a migration comparando models vs banco atual:
alembic revision --autogenerate -m "add campo X em student"
# 3. ABRA a migration gerada em alembic/versions/ e revise.
# 4. Aplique:
alembic upgrade head          # em dev
# em prod: rode 'alembic upgrade head' no deploy (ver nota abaixo)
```

Comandos úteis:
```bash
alembic current          # em que revisão o banco está
alembic history          # histórico de migrations
alembic downgrade -1     # desfaz a última (se a migration tiver downgrade)
```

---

## Detectar drift (bônus de auditoria)

Depois de adotar, rode no banco real:
```bash
alembic revision --autogenerate -m "check_drift"
```
Se a migration sair **vazia**, models e banco estão em sincronia. Se sair com
alterações, isso revela onde o schema vivo divergiu dos models (legado dos
SQLs avulsos). Revise: ou ajuste o model, ou aplique a correção. Apague o
arquivo se for só inspeção.

---

## Pendências de integração (não bloqueiam a adoção)

- **`main.py` em dev** ainda roda `Base.metadata.create_all`. Pode manter por
  ora. Quando o time estiver confortável, troque o setup de dev para
  `alembic upgrade head` e remova o `create_all`, deixando o Alembic como
  fonte única do schema.
- **Deploy (Railway)**: adicionar `alembic upgrade head` ao passo de release
  (ex.: no `Procfile`/comando de start, antes de subir o uvicorn) para que
  produção aplique migrations automaticamente. Fazer isso só **depois** do
  passo 3 (stamp) em produção, senão o primeiro upgrade tentaria recriar tudo.
- **`migrations/*.sql` legados**: manter como referência histórica; não são
  mais o mecanismo. Migrar o conteúdo relevante para revisions quando tocar
  nas tabelas correspondentes.
