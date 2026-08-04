"""Recorder: síncrono + retry + dead-letter.

Regra inegociável: falha ao registrar NUNCA propaga exceção para a feature monitorada.
Com gravação síncrona não existe evento "em voo" — quando a chamada retorna, já está
comitado. É o que faz o requisito de crash de job ser satisfeito por construção.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from .event import UsageEvent

log = logging.getLogger("tokenmeter")


class Recorder:
    def __init__(self, store, deadletter_path: str | os.PathLike | None = None,
                 retries: int = 2, backoff_s: float = 0.05):
        self.store = store
        self.dl = Path(deadletter_path) if deadletter_path else None
        self.retries = max(1, retries)
        self.backoff_s = backoff_s
        self.stats = {"written": 0, "deadlettered": 0, "lost": 0, "replayed": 0}

    def record(self, event: UsageEvent) -> None:
        for attempt in range(1, self.retries + 1):
            try:
                self.store.write([event])
                self.stats["written"] += 1
                self._drenar_oportunista()
                return
            except Exception:
                if attempt == self.retries:
                    log.warning("tokenmeter: falha ao gravar após %d tentativas", attempt,
                                exc_info=True)
                    break
                time.sleep(self.backoff_s)
        self._deadletter(event)

    def _deadletter(self, event: UsageEvent) -> None:
        if self.dl is None:
            self.stats["lost"] += 1
            return
        try:
            self.dl.parent.mkdir(parents=True, exist_ok=True)
            with self.dl.open("a", encoding="utf-8") as f:
                f.write(event.to_json() + "\n")
            self.stats["deadlettered"] += 1
        except Exception:
            self.stats["lost"] += 1
            log.warning("tokenmeter: evento perdido (dead-letter indisponível)", exc_info=True)
        # nunca re-raise. jamais.

    def _drenar_oportunista(self) -> None:
        """Se acabamos de gravar com sucesso e há coisa no dead-letter, drena agora.

        Sem isso, o dead-letter só era reprocessado no startup — o que basta quando o
        banco é local, mas não quando ele é remoto e pode ficar fora por horas: os
        eventos ficariam no disco até o próximo deploy.

        Barato: só toca o disco quando o contador indica que há pendência, e a própria
        escrita que acabou de funcionar é a prova de que o banco voltou. Nunca levanta
        exceção — é oportunista, não obrigatório.
        """
        if self.stats["deadlettered"] <= self.stats["replayed"]:
            return
        try:
            self.drain()
        except Exception:
            log.debug("tokenmeter: drain oportunista falhou", exc_info=True)

    def drain(self) -> int:
        """Reprocessa o dead-letter. Idempotente: o SELECT de existência no store cobre replay."""
        if self.dl is None or not self.dl.exists():
            return 0
        try:
            lines = [l for l in self.dl.read_text(encoding="utf-8").splitlines() if l.strip()]
        except Exception:
            return 0
        pendentes, ok = [], 0
        for line in lines:
            try:
                self.store.write([UsageEvent.from_json(line)])
                ok += 1
            except Exception:
                pendentes.append(line)
        try:
            if pendentes:
                self.dl.write_text("\n".join(pendentes) + "\n", encoding="utf-8")
            else:
                self.dl.unlink(missing_ok=True)
        except Exception:
            log.warning("tokenmeter: não consegui limpar o dead-letter", exc_info=True)
        self.stats["replayed"] += ok
        if ok:
            log.info("tokenmeter: %d evento(s) recuperados do dead-letter", ok)
        return ok

    def deadletter_size(self) -> int:
        if self.dl is None or not self.dl.exists():
            return 0
        try:
            return sum(1 for l in self.dl.read_text(encoding="utf-8").splitlines() if l.strip())
        except Exception:
            return 0
