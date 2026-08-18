"""
Leitura e escrita do CONTEUDO de um material da Biblioteca (model `Material`).

Por que este modulo existe
--------------------------
Ate 18/08/2026 o HTML (ou o JSON do mapa mental) gerado pela IA era gravado
apenas em `backend/storage/materiais/{id}.html`, e a linha no banco guardava
so o nome do arquivo (`Material.arquivo_path`).

O servico web do Railway roda em disco EFEMERO, sem volume persistente: a cada
redeploy o diretorio `storage/` volta ao estado da imagem e todos os arquivos
somem. A linha, porem, continua com `status='disponivel'`. Do ponto de vista do
professor o material "nao persistiu": ele aparece na biblioteca (ou nem isso,
quando a listagem tambem quebra) e, ao abrir, responde 404
"Conteudo do material nao encontrado no storage".

E a mesma causa raiz ja corrigida para `ilustracoes` na migration 011. A
correcao aqui e a mesma: o conteudo mora NA LINHA (`Material.conteudo`,
MEDIUMTEXT). O disco continua sendo LIDO como fallback, para nao perder o que
por acaso ainda exista de materiais antigos na maquina, mas nao e mais escrito
por codigo novo.
"""
import json
from typing import Any, Optional, Union

from app.models.material import Material, TipoMaterial
from app.services.storage_service import storage_service


def e_mapa_mental(material: Material) -> bool:
    """Mapa mental e o unico tipo cujo conteudo e JSON; o resto e HTML."""
    return material.tipo == TipoMaterial.MAPA_MENTAL


def serializar(conteudo: Union[str, dict]) -> str:
    """Normaliza para o texto que vai na coluna (JSON vira string)."""
    if isinstance(conteudo, str):
        return conteudo
    return json.dumps(conteudo, ensure_ascii=False)


def ler(material: Material) -> Optional[Union[str, dict]]:
    """
    Conteudo da versao atual: HTML como str, mapa mental como dict.

    Ordem: coluna `conteudo` (fonte de verdade) -> arquivo em disco (legado).
    Devolve None quando nao ha conteudo em lugar nenhum.
    """
    bruto = material.conteudo
    if bruto:
        if not e_mapa_mental(material):
            return bruto
        try:
            return json.loads(bruto)
        except (json.JSONDecodeError, TypeError):
            # Conteudo corrompido no banco: cai para o disco em vez de estourar
            # 500 na cara do professor.
            pass

    if e_mapa_mental(material):
        return storage_service.ler_json(material.id)
    return storage_service.ler_html(material.id)


def escrever(material: Material, conteudo: Union[str, dict]) -> None:
    """
    Grava o conteudo na propria linha.

    `arquivo_path` continua sendo preenchido (valor logico "{id}.html/json"):
    varias telas e o proprio codigo tratam esse campo como "ja foi gerado".
    Ele deixou de apontar para um arquivo que existe - por isso a leitura passa
    por `ler()`, nunca pelo path direto.
    """
    material.conteudo = serializar(conteudo)
    ext = "json" if e_mapa_mental(material) else "html"
    material.arquivo_path = f"{material.id}.{ext}"


def arquivar_versao(material: Material, versao: int) -> bool:
    """
    Move o conteudo atual para o mapa de versoes arquivadas.

    Retorna True se havia algo para arquivar. O conteudo atual NAO e apagado:
    a regeneracao o sobrescreve quando termina, e ate la o professor continua
    vendo a versao antiga em vez de uma tela vazia.
    """
    atual = material.conteudo
    if not atual:
        # Material antigo, so em disco: tenta preservar o que ainda existir.
        legado = ler(material)
        if legado is None:
            return False
        atual = serializar(legado)

    versoes = dict(material.conteudo_versoes or {})
    versoes[str(versao)] = atual
    material.conteudo_versoes = versoes
    return True


def ler_versao(material: Material, versao: int) -> Optional[Union[str, dict]]:
    """Conteudo de uma versao arquivada (banco -> disco legado)."""
    versoes = material.conteudo_versoes or {}
    bruto: Any = versoes.get(str(versao))
    if bruto:
        if not e_mapa_mental(material):
            return bruto
        try:
            return json.loads(bruto)
        except (json.JSONDecodeError, TypeError):
            pass

    ext = "json" if e_mapa_mental(material) else "html"
    return storage_service.ler_versao(material.id, versao, ext)
