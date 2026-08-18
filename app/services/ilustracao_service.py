"""
Servico de ilustracao de conteudo por IA.

Orquestra a parte "inteligente" da geracao de imagem:
  1) o Claude escreve um PROMPT visual em pt-BR a partir do conteudo (material,
     questao ou tema de redacao), num estilo consistente e apropriado a criancas;
  2) o provedor de imagem (image_providers) transforma o prompt em bytes;
  3) a ROTA grava os bytes em Ilustracao.imagem_bytes (banco, nao disco - o
     servico web do Railway nao tem volume persistente; um arquivo em
     storage/ilustracoes/ sumia no proximo deploy).

Publico do AdaptAI: alunos com TEA/TDAH/dislexia, muitos menores de idade. Por
isso o prompt de estilo forca ilustracao limpa, acolhedora, SEM texto embutido
(texto gerado por IA costuma sair errado e polui), e o prompt de conteudo passa
por uma instrucao de seguranca explicita. O provedor ainda roda o proprio filtro.

A imagem pertence ao CONTEUDO (ver model Ilustracao) - gerada uma vez, reusada
por toda a turma.
"""
import time
from typing import Optional

import tokenmeter as tm

from app.core.anthropic_client import get_anthropic_client, get_fast_model
from app.core.features import F
from app.core.logging_config import get_logger
from app.services.image_providers import (ErroGeracaoImagem,
                                           ProvedorImagemIndisponivel,
                                           get_image_provider)

logger = get_logger(__name__)

# Rotulo humano de cada contexto, so para orientar o Claude na hora do prompt.
_CONTEXTO_LABEL = {
    "material": "um material didatico",
    "questao": "uma questao de prova",
    "redacao_tema": "um tema de redacao",
}

# Estilo visual fixo do AdaptAI - garante que as ilustracoes conversem entre si.
_ESTILO = (
    "flat vector illustration, soft rounded shapes, warm friendly palette, "
    "clean simple background, child-friendly, inclusive, high clarity, "
    "no text, no words, no letters, educational, calm"
)


@tm.feature(F.ILUSTRACAO_IA)
def gerar_prompt_ilustracao(
    contexto_tipo: str,
    texto_conteudo: str,
    descricao: Optional[str] = None,
) -> str:
    """Pede ao Claude um prompt de imagem em ingles (os modelos rendem melhor em
    ingles) a partir do conteudo em portugues. Retorna o prompt final ja com o
    estilo do AdaptAI anexado.

    Usa o modelo rapido/barato: e uma tarefa curta de reescrita.
    """
    label = _CONTEXTO_LABEL.get((contexto_tipo or "").lower(), "um conteudo escolar")
    foco = ("\nFoco pedido pelo professor: %s" % descricao) if descricao else ""

    instrucao = (
        "Voce cria descricoes curtas para gerar uma ILUSTRACAO que ajude alunos "
        "(muitos com TEA, TDAH ou dislexia, incluindo criancas) a entender "
        + label + ".\n"
        "A partir do conteudo abaixo, escreva UMA descricao visual, concreta e "
        "literal, do que a ilustracao deve mostrar. Em INGLES, no maximo 40 "
        "palavras. Descreva apenas a cena/objetos - NAO inclua texto, palavras "
        "ou letras na imagem. Nada assustador, violento, adulto ou sensivel: "
        "conteudo 100% apropriado para criancas.\n"
        "Responda SOMENTE com a descricao, sem aspas e sem explicacao.\n\n"
        "CONTEUDO:\n" + (texto_conteudo or "").strip()[:1500] + foco
    )

    client = get_anthropic_client(timeout=60.0, max_retries=2)
    message = client.messages.create(
        model=get_fast_model(),
        max_tokens=200,
        messages=[{"role": "user", "content": instrucao}],
    )
    base = (message.content[0].text if message.content else "").strip()
    base = base.replace("\n", " ").strip().strip('"').strip()
    if not base:
        # Fallback minimo: usa a descricao/termo do professor ou um generico.
        base = (descricao or "a friendly educational illustration").strip()

    return "%s. Style: %s" % (base, _ESTILO)


def gerar_ilustracao_ia(
    prompt: str, tamanho: str = "quadrado", formato: str = "png"
) -> bytes:
    """Gera a imagem pelo provedor configurado. Repassa as excecoes tipadas do
    image_providers (ProvedorImagemIndisponivel / ErroGeracaoImagem) para a rota
    decidir o status HTTP.

    Ponto UNICO de geracao de imagem no repo (ver ai_materiais_service.py, que
    chama esta mesma funcao para hq_tirinha/album_figurinhas) - por isso o
    tracking de custo entra aqui, e nao em cada chamador. Mesmo principio do
    tm.wrap() no client Anthropic: instrumentar o gargalo, nao cada uso.

    feature=F.ILUSTRACAO_IA e explicito (nao herdado do contexto de quem
    chamou) para casar com gerar_prompt_ilustracao() acima: as duas metades do
    pipeline de ilustracao (prompt por Claude + imagem por IA) ficam sob a
    mesma feature, mesmo quando disparadas de dentro de material_adaptado.
    """
    provedor = get_image_provider()
    t0 = time.perf_counter()
    try:
        imagem = provedor.gerar(prompt, tamanho=tamanho, formato=formato)
    except (ProvedorImagemIndisponivel, ErroGeracaoImagem) as exc:
        tm.record(
            model=provedor.model_id, provider=provedor.provider,
            operation="image_generation", feature=F.ILUSTRACAO_IA,
            tags={"tamanho": tamanho, "formato": formato},
            status="error", error_type=type(exc).__name__,
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        raise
    tm.record(
        model=provedor.model_id, provider=provedor.provider,
        operation="image_generation", feature=F.ILUSTRACAO_IA,
        tags={"tamanho": tamanho, "formato": formato}, calls=1,
        duration_ms=int((time.perf_counter() - t0) * 1000),
    )
    return imagem
