"""
Service para geração de materiais com IA
"""
from app.core.anthropic_client import get_anthropic_client, get_default_model
import json
from app.core.config import settings

# tokenmeter: atribuicao de consumo de IA (ver app/core/features.py)
import tokenmeter as tm
from app.core.features import F


# ----------------------------------------------------------------------------
# 2026-08-18 — TRUNCAMENTO SILENCIOSO
# ----------------------------------------------------------------------------
# Os tres geradores abaixo pegavam `response.content[0].text` e devolviam
# success=True sem olhar `stop_reason`. Quando a resposta batia no teto de
# max_tokens (4000 para um prompt que pede HTML rico com CSS inline — acontecia
# com frequencia em "Material Visual" e "Lista de Atividades"), o material era
# gravado com o HTML CORTADO NO MEIO: o professor abria e via a pagina
# terminando no meio de uma frase, ou com o layout quebrado por uma tag aberta.
# Pior: ficava com status "disponivel", entao nada indicava problema.
#
# `ai_materiais_service._chamar_ia` ja fazia essa checagem desde 11/08 (para os
# materiais adaptados); a Biblioteca tinha ficado de fora.
_ERRO_TRUNCADO = (
    "O conteúdo pedido é longo demais e a resposta da IA foi cortada. "
    "Tente um tema mais específico ou divida em dois materiais."
)


def _extrair_texto(response) -> str:
    """Texto da resposta, sem markdown. Levanta ValueError se veio truncada/vazia."""
    if getattr(response, "stop_reason", None) == "max_tokens":
        raise ValueError(_ERRO_TRUNCADO)

    blocos = getattr(response, "content", None) or []
    if not blocos:
        raise ValueError("A IA devolveu uma resposta vazia. Tente novamente.")

    texto = (getattr(blocos[0], "text", "") or "").strip()
    if not texto:
        raise ValueError("A IA devolveu uma resposta vazia. Tente novamente.")

    return texto.replace("```html", "").replace("```json", "").replace("```", "").strip()


class MaterialGeracaoService:
    """Service para gerar materiais educacionais com IA"""
    
    def __init__(self):
        """Inicializa o cliente da Anthropic (lazy)"""
        self._client = None
        # Era "claude-3-5-sonnet-20241022", introduzido no commit c0b0515 (13/01/2026)
        # - um modelo que a Anthropic ja havia aposentado em 28/10/2025. A linha nunca
        # chegou a executar (a tabela `materiais` so tem 3 registros, todos de nov/2025
        # e todos com status=disponivel), entao NAO houve falha em producao: era um bug
        # latente, que dispararia no proximo uso da feature.
        # get_default_model() resolve settings.CLAUDE_MODEL e nao envelhece sozinho.
        self.model = get_default_model()
    
    @property
    def client(self):
        """Lazy initialization do cliente Anthropic"""
        if self._client is None:
            self._client = get_anthropic_client()
        return self._client
    
    @tm.feature(F.MATERIAL_ADAPTADO)
    def gerar_material_visual(self, titulo: str, conteudo: str, materia: str, serie: str, adaptacoes: list = None) -> dict:
        """
        Gera um material visual rico em HTML
        
        Args:
            titulo: Título do material
            conteudo: Descrição do que deve ser criado
            materia: Matéria (ex: Biologia, Matemática)
            serie: Série/nível (ex: 8º ano)
            adaptacoes: Lista de adaptações necessárias (TEA, TDAH, etc)
        
        Returns:
            dict com 'success', 'html' e 'tokens_used'
        """
        adaptacoes_text = ""
        if adaptacoes:
            adaptacoes_text = f"\n\nIMPORTANTE: Este material será usado por alunos com: {', '.join(adaptacoes)}. Adapte a linguagem e formato para ser mais acessível."
        
        prompt = f"""Crie um material educacional VISUAL e ATRATIVO sobre: {titulo}

MATÉRIA: {materia}
SÉRIE/NÍVEL: {serie}

CONTEÚDO SOLICITADO:
{conteudo}{adaptacoes_text}

IMPORTANTE - FORMATO DE SAÍDA:
- Retorne APENAS o conteúdo HTML (SEM as tags <html>, <head>, <body>)
- Use CSS inline para estilização
- Crie um conteúdo VISUALMENTE RICO e ATRATIVO

ESTRUTURA DO CONTEÚDO:
1. TÍTULO PRINCIPAL (grande, colorido, com gradiente)
2. INTRODUÇÃO VISUAL (box com cor de fundo, texto introdutório)
3. SEÇÕES BEM DEFINIDAS:
   - Cada seção com título colorido
   - Background diferente para cada seção
   - Boxes informativos coloridos
   - Exemplos práticos destacados
4. DIAGRAMAS/FLUXOGRAMAS em texto (use caracteres ▶, ►, →, ↓, •, ◆)
5. RESUMO FINAL em cards coloridos

ESTILO CSS INLINE:
- Use cores vibrantes e gradientes (ex: background: linear-gradient(135deg, #667eea 0%, #764ba2 100%))
- Cards com sombras (box-shadow)
- Use emojis e ícones quando apropriado
- Fonte grande e legível (min 16px)
- Espaçamento generoso (padding, margin)
- Bordas arredondadas (border-radius)
- Tipografia hierárquica (h1, h2, h3 bem definidos)
- Adicione hover effects sutis

EXEMPLO DE ESTRUTURA:
<div style="max-width: 800px; margin: 0 auto; font-family: 'Segoe UI', Arial, sans-serif;">
  <h1 style="font-size: 42px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; text-align: center; margin-bottom: 30px;">
    [TÍTULO]
  </h1>
  
  <div style="background: #f0f4ff; padding: 25px; border-radius: 15px; margin-bottom: 30px; border-left: 5px solid #667eea;">
    <p style="font-size: 18px; line-height: 1.8; color: #333;">
      [INTRODUÇÃO]
    </p>
  </div>
  
  <h2 style="color: #667eea; font-size: 32px; margin-top: 40px; margin-bottom: 20px;">
    📚 [SEÇÃO 1]
  </h2>
  
  <div style="background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 25px;">
    [CONTEÚDO DA SEÇÃO]
  </div>
  
  <!-- Mais seções... -->
</div>

NÃO inclua explicações, apenas o HTML puro e bem formatado."""

        try:
            response = self.client.messages.create(
                model=self.model,
                # 8192: o prompt pede HTML rico com CSS inline em varias secoes;
                # com 4000 a resposta era cortada com frequencia (ver
                # _extrair_texto).
                max_tokens=8192,
                messages=[{"role": "user", "content": prompt}]
            )
            
            html_content = _extrair_texto(response)
            
            return {
                "success": True,
                "html": html_content,
                "tokens_used": response.usage.input_tokens + response.usage.output_tokens
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    @tm.feature(F.MATERIAL_ADAPTADO)
    def gerar_mapa_mental(self, titulo: str, conteudo: str, materia: str, serie: str, adaptacoes: list = None) -> dict:
        """
        Gera um mapa mental estruturado em JSON
        
        Args:
            titulo: Título do mapa mental
            conteudo: Descrição do que deve ser criado
            materia: Matéria
            serie: Série/nível
            adaptacoes: Lista de adaptações
        
        Returns:
            dict com 'success', 'json' e 'tokens_used'
        """
        adaptacoes_text = ""
        if adaptacoes:
            adaptacoes_text = f"\n\nADAPTAÇÕES: Simplifique para alunos com: {', '.join(adaptacoes)}"
        
        prompt = f"""Crie um mapa mental sobre: {titulo}

MATÉRIA: {materia}
SÉRIE: {serie}

CONTEÚDO:
{conteudo}{adaptacoes_text}

RETORNE APENAS UM JSON com esta estrutura exata:
{{
  "titulo": "Conceito Central",
  "cor_central": "#6366F1",
  "nos": [
    {{
      "id": "no1",
      "texto": "Conceito Principal 1",
      "cor": "#EF4444",
      "nivel": 1,
      "filhos": [
        {{
          "id": "no1_1",
          "texto": "Subconceito 1.1",
          "cor": "#FCA5A5",
          "nivel": 2,
          "filhos": []
        }}
      ]
    }}
  ]
}}

REGRAS IMPORTANTES:
1. O conceito central vai no "titulo"
2. Crie 3-5 nós principais (nivel: 1)
3. Cada nó principal pode ter 2-4 subnós (nivel: 2)
4. Máximo 20-25 nós no total
5. Use textos CURTOS (4-5 palavras máximo)
6. Use emojis apropriados nos textos
7. IDs únicos para cada nó (ex: no1, no1_1, no1_2)
8. Cores sugeridas:
   - Central: #6366F1 (azul/roxo)
   - Nível 1: #EF4444 (vermelho), #10B981 (verde), #F59E0B (laranja), #8B5CF6 (roxo), #EC4899 (rosa)
   - Nível 2: versões mais claras (#FCA5A5, #86EFAC, #FCD34D, #C4B5FD, #F9A8D4)

RETORNE APENAS O JSON, sem explicações ou markdown."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            
            json_text = _extrair_texto(response)
            
            # Parse JSON
            try:
                mapa_json = json.loads(json_text)
            except json.JSONDecodeError as je:
                return {
                    "success": False,
                    "error": f"JSON inválido retornado pela IA: {str(je)}",
                    "raw_response": json_text
                }
            
            return {
                "success": True,
                "json": mapa_json,
                "tokens_used": response.usage.input_tokens + response.usage.output_tokens
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    @tm.feature(F.MATERIAL_ADAPTADO)
    def gerar_material_texto(self, formato: str, titulo: str, conteudo: str, materia: str, serie: str, adaptacoes: list = None) -> dict:
        """
        Gera materiais textuais em HTML para os formatos de adaptacao:
        resumo, texto_simplificado, roteiro_estudo, atividades.

        Returns:
            dict com 'success', 'html' e 'tokens_used' (ou 'error').
        """
        formatos = {
            "resumo": {
                "nome": "Resumo de estudo",
                "objetivo": "Resuma o conteudo de forma clara e organizada, destacando os pontos principais.",
                "estrutura": "Use topicos curtos, destaque palavras-chave e finalize com um quadro de 'pontos essenciais'.",
            },
            "texto_simplificado": {
                "nome": "Texto simplificado",
                "objetivo": "Reescreva o conteudo em linguagem simples e acessivel, com frases curtas e diretas.",
                "estrutura": "Paragrafos curtos, vocabulario simples; explique termos dificeis entre parenteses. Evite metaforas e ironia.",
            },
            "roteiro_estudo": {
                "nome": "Roteiro de estudo",
                "objetivo": "Crie um roteiro de estudo passo a passo sobre o conteudo.",
                "estrutura": "Etapas numeradas com o que estudar em cada uma, tempo sugerido e uma checklist final.",
            },
            "atividades": {
                "nome": "Lista de atividades",
                "objetivo": "Crie atividades/exercicios sobre o conteudo, com gabarito ao final.",
                "estrutura": "5 a 8 questoes variadas (objetivas e abertas), seguidas de uma secao 'Gabarito comentado'.",
            },
        }
        cfg = formatos.get(formato, formatos["resumo"])

        adaptacoes_text = ""
        if adaptacoes:
            adaptacoes_text = (
                f"\n\nIMPORTANTE: material para alunos com: {', '.join(adaptacoes)}. "
                "Adapte a linguagem e o formato para maior acessibilidade (frases curtas, sem ambiguidade)."
            )

        prompt = f"""Crie um material do tipo "{cfg['nome']}" sobre: {titulo}

MATERIA: {materia}
SERIE/NIVEL: {serie}

CONTEUDO BASE:
{conteudo}{adaptacoes_text}

OBJETIVO: {cfg['objetivo']}
ESTRUTURA: {cfg['estrutura']}

FORMATO DE SAIDA:
- Retorne APENAS HTML (sem as tags <html>, <head>, <body>), com CSS inline.
- Visual limpo e legivel: fonte minima 16px, bom espacamento, titulos hierarquicos e boxes com bordas arredondadas.
- Use cores suaves e, quando ajudar a compreensao, emojis discretos.
- NAO inclua explicacoes fora do HTML."""

        try:
            response = self.client.messages.create(
                model=self.model,
                # Mesmo motivo do material visual: "atividades" com gabarito
                # comentado nao cabia em 4000 tokens.
                max_tokens=8192,
                messages=[{"role": "user", "content": prompt}]
            )
            html_content = _extrair_texto(response)
            return {
                "success": True,
                "html": html_content,
                "tokens_used": response.usage.input_tokens + response.usage.output_tokens
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


# Instância global do service
material_service = MaterialGeracaoService()
