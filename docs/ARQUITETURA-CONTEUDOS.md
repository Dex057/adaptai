# Arquitetura de conteúdos — Materiais, Materiais Adaptados, Redações e Provas

> Documento de referência. Escrito em 2026-08-11 para responder a uma dúvida recorrente:
> **"o que deveria constar na aba *Materiais*, se *Materiais Adaptados* já recupera o
> histórico de produção?"**

---

## 1. O padrão geral: conteúdo × recepção

Todo artefato gerado no AdaptAI se divide em duas tabelas:

```
CONTEÚDO (criado 1×, reutilizável)  ──<  PONTE (1 linha por aluno)  >──  Student
```

| Conteúdo | Ponte | Situação |
|---|---|---|
| `Material` | `MaterialAluno` | ✅ correto |
| `Prova` | `ProvaAluno` | ✅ correto |
| `TemaRedacao` | `RedacaoAluno` | ✅ correto |
| `MaterialAdaptadoGerado` | *(não existe)* | ❌ ver §4 |

**Regra de arquitetura:** nenhum conteúdo gerado por IA deve carregar `student_id`
como *posse*. Posse vive na ponte. Quem carrega `student_id` direto não pode ser
reutilizado, e duplicar a linha para reatribuir custa armazenamento e faz com que
correções no material não propaguem.

A ponte é também onde mora o **estado individual**: `favorito`, `anotacoes_aluno`,
`total_visualizacoes`, `data_primeira_visualizacao`. Isso é o que garante que
reatribuir um material a novos alunos **não afeta quem já o tinha**.

---

## 2. "Materiais" × "Materiais Adaptados" — a diferença

As duas abas existem porque resolvem problemas diferentes. Hoje elas parecem
redundantes porque a de Materiais está quebrada e a de Adaptados virou,
na prática, um histórico.

### 📚 Materiais — *biblioteca do professor*

Modelo: `app/models/material.py` → `Material` + `MaterialAluno`
Rotas: `app/api/routes/materiais.py` (prefixo `/materiais`)

| Característica | Valor |
|---|---|
| Escopo | Do **professor**, não de um aluno |
| Tipos | 6: `visual`, `mapa_mental`, `resumo`, `texto_simplificado`, `roteiro_estudo`, `atividades` |
| Saída | Arquivo **HTML** em `storage/` (`arquivo_path`) |
| Versionamento | ✅ `versao` + `historico_versoes` + `POST /{id}/regenerar` |
| Distribuição | ✅ N:N via `MaterialAluno` |
| Personalização | Genérica — não usa o diagnóstico do aluno |
| Ciclo de vida | Longo: cria uma vez, reatribui em várias turmas, versiona |

**O que a aba deve mostrar:** a biblioteca reutilizável. Um material de "Frações —
5º ano" é criado uma vez e atribuído à turma inteira este ano, e à turma nova no ano
que vem. A tela precisa de: listagem com filtro, contagem de alunos que receberam,
**atribuir a mais alunos**, ver versões, regenerar, excluir.

> É esta a resposta à sua pergunta: **Materiais é o acervo permanente e
> compartilhável**. É a única das duas telas onde faz sentido "reaproveitar o que já
> foi criado para outro aluno" — e o schema já suporta isso hoje.

### 🎨 Materiais Adaptados — *geração sob medida para um aluno*

Modelo: `app/models/material_adaptado_gerado.py` → `MaterialAdaptadoGerado`
Rotas: `app/api/routes/materiais_adaptados.py` (prefixo `/materiais-adaptados`)

| Característica | Valor |
|---|---|
| Escopo | De **um aluno específico** |
| Tipos | 37 (ver `TIPOS_MATERIAIS`), gerados **vários de uma vez** |
| Saída | **JSON** estruturado (`resultado_json`), renderizado por `MaterialViewer` |
| Versionamento | ❌ não tem |
| Distribuição | ❌ 1 material = 1 aluno |
| Personalização | ✅ **usa `student.diagnosis`** (TEA, TDAH, dislexia…) |
| Ciclo de vida | Pontual: gera para um conteúdo, para um aluno, naquele momento |

**O que a aba deve mostrar:** o histórico por aluno + o gerador. É legítimo que seja
um histórico — a personalização é o valor, e ela é intrinsecamente individual.

### Resumindo

| | Materiais | Materiais Adaptados |
|---|---|---|
| Pergunta que responde | "que material eu já tenho pronto?" | "o que gero agora **pro Lucas**?" |
| Reutilizável | ✅ sim, por desenho | ❌ hoje não |
| Usa diagnóstico | ❌ não | ✅ sim |
| Formato | HTML versionado | JSON multi-tipo |

**Não são redundantes.** São acervo × sob medida. O que confunde hoje é que a tela de
Materiais estava quebrada (ver `CORRECOES-2026-08-11.md` §2), então o professor só
via a de Adaptados funcionando e ela virou a única porta de entrada.

---

## 3. Decisão pendente (sua)

Se a intenção de produto for **uma aba só**, o caminho natural é:

- Manter `MaterialAdaptadoGerado` como motor de geração (é o mais rico: 37 tipos +
  diagnóstico).
- Dar a ele a ponte que falta (§4), ganhando reutilização.
- Aposentar `Material`/`MaterialAluno` migrando os registros existentes.

Isso é **refatoração**, não correção — fora do escopo de 2026-08-11. Registrado aqui
para a decisão ser consciente e não por inércia.

Se mantiver as duas, vale renomear na UI para a diferença ficar óbvia:
**"Biblioteca de Materiais"** × **"Gerar Material Adaptado"**.

---

## 4. A ponte que falta em Materiais Adaptados

Hoje:

```python
class MaterialAdaptadoGerado(Base):
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)  # posse
    resultado_json = Column(JSON, nullable=False)                            # conteúdo pesado
    favorito = Column(Integer, default=0)                                    # estado do aluno
    lido = Column(Integer, default=0)                                        # misturado
    anotacoes_aluno = Column(Text)                                           # com o conteúdo
```

Conteúdo e recepção na mesma linha ⇒ reatribuir exige duplicar o `resultado_json`
inteiro, e uma correção não propaga para os outros alunos.

Proposta (migration + backfill detalhados em `CORRECOES-2026-08-11.md` §7):

```
MaterialAdaptadoGerado  ──<  MaterialAdaptadoAluno  >──  Student
   (conteúdo)                  (recepção)
```

`student_id` passa a ser **nullable** e significa apenas *"aluno cujo perfil originou
a adaptação"* (proveniência), nunca posse.

> **Expand → migrate → contract:** as colunas antigas (`favorito`, `lido`, `lido_em`,
> `anotacoes_aluno`) **não** saem na mesma migration. Faça o `drop` uma semana depois,
> com a UI nova estável em produção. Se precisar de rollback, você vai querer os dados
> ainda lá.

---

## 5. Consulta rápida

| Preciso de… | Onde mexer |
|---|---|
| Novo tipo de material adaptado | `TIPOS_MATERIAIS` + método em `ai_materiais_service.py` + viewer em `MaterialViewer.jsx` + `config.js` |
| Liberar/bloquear um tipo | `TIPOS_HABILITADOS` nos **dois** repos |
| Atribuir material a mais alunos | `MaterialAluno` (existe) / `MaterialAdaptadoAluno` (a criar) |
| Conteúdo do aluno no portal | rotas sob `/student/*` com `get_current_student` |
| Estado individual (favorito, notas) | sempre na **ponte**, nunca no conteúdo |
