"""Client falso com o MESMO formato de resposta do SDK anthropic.

Existe só para a demo rodar sem chave de API. O código do tokenmeter não sabe que é falso —
lê `response.usage.input_tokens` etc. exatamente como leria do SDK real.
"""
from __future__ import annotations

import random
import uuid


class _Usage:
    def __init__(self, i, o, cw=0, cr=0):
        self.input_tokens = i                     # na Anthropic, JÁ exclui os cacheados
        self.output_tokens = o
        self.cache_creation_input_tokens = cw
        self.cache_read_input_tokens = cr


class _Message:
    def __init__(self, model, usage):
        self.id = f"msg_{uuid.uuid4().hex[:16]}"
        self.model = model
        self.usage = usage
        self.content = [type("B", (), {"type": "text", "text": "..."})()]


class _Stream:
    def __init__(self, model, i, o, abortar_em=None):
        self._model, self._i, self._o, self._abortar = model, i, o, abortar_em
        self._msg = _Message(model, _Usage(i, o))

    def __enter__(self): return self
    def __exit__(self, *e): return False

    def __iter__(self):
        # Como no SDK real: message_start já traz input_tokens; o usage final só no fim.
        parcial = _Message(self._model, _Usage(self._i, 0))
        parcial.id = self._msg.id
        for n in range(10):
            if self._abortar is not None and n >= self._abortar:
                return
            if n == 0:
                yield type("Chunk", (), {"message": parcial})()
            elif n == 9:
                yield type("Chunk", (), {"message": self._msg})()
            else:
                parcial.usage.output_tokens += self._o // 8   # acumula como o stream real
                yield type("Chunk", (), {"message": None})()

    def get_final_message(self): return self._msg


class _Messages:
    def __init__(self, rng): self._rng = rng

    def create(self, *, model, max_tokens=1024, messages=None, cache=False, falhar=False, **kw):
        if falhar:
            raise RuntimeError("overloaded_error: provedor indisponível")
        i = self._rng.randint(800, 3000)
        o = self._rng.randint(150, 900)
        cw = self._rng.randint(1000, 4000) if cache else 0
        cr = self._rng.randint(2000, 8000) if cache else 0
        return _Message(model, _Usage(i, o, cw, cr))

    def stream(self, *, model, abortar_em=None, **kw):
        return _Stream(model, self._rng.randint(900, 2000), self._rng.randint(200, 600),
                       abortar_em)


class Anthropic:
    """Assinatura equivalente à do SDK real."""

    def __init__(self, api_key: str | None = None, seed: int = 7, **opts):
        self.api_key = api_key or "sk-fake"
        self.options = opts
        self.messages = _Messages(random.Random(seed))

    def with_options(self, **opts):
        """Como no SDK real: devolve um client DERIVADO, não muta o original."""
        novo = Anthropic(self.api_key)
        novo.options = {**self.options, **opts}
        return novo
