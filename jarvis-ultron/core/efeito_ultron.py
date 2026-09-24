"""Efeito de voz metálica "Ultron" aplicado ao áudio do Gemini Live enquanto ele chega.

Ligado por padrão. Para desligar, coloque JARVIS_EFEITO_ULTRON=0 no arquivo .env.
Estilos: JARVIS_EFEITO_ULTRON=1 (ou "ultron") para metálico, "robo" para robô.
"""

from __future__ import annotations

import os

import numpy as np

HISTORICO_SEGUNDOS = 0.06
GANHO = {"ultron": 0.42, "robo": 0.75}


def _atrasar(sinal, amostras: int):
    saida = np.zeros_like(sinal)
    if amostras < len(sinal):
        saida[amostras:] = sinal[:len(sinal) - amostras]
    return saida


def _processar(x, t, estilo: str, taxa: int):
    if estilo == "ultron":
        # Modulação em anel suave + ressonância metálica + segunda voz levemente atrasada.
        y = 0.7 * x + 0.3 * x * np.sin(2 * np.pi * 38 * t)
        atraso = int(0.009 * taxa)
        y = y + 0.45 * _atrasar(y, atraso) + 0.2 * _atrasar(y, 2 * atraso) + 0.1 * _atrasar(y, 3 * atraso)
        return y + 0.3 * _atrasar(y, int(0.028 * taxa))
    y = 0.35 * x + 0.65 * x * np.sin(2 * np.pi * 70 * t)  # robô
    return y + 0.4 * _atrasar(y, int(0.006 * taxa))


class EfeitoUltron:
    """Processa pedaços de áudio PCM int16 mono sem cortes entre um pedaço e outro."""

    def __init__(self, estilo: str = "ultron", taxa: int = 24000):
        self.estilo = estilo
        self.taxa = taxa
        self.anterior = np.zeros(int(HISTORICO_SEGUNDOS * taxa), dtype=np.float32)
        self.amostras_passadas = 0

    def processar(self, pcm: bytes) -> bytes:
        if not pcm:
            return pcm
        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        junto = np.concatenate([self.anterior, x])
        inicio = self.amostras_passadas - len(self.anterior)
        t = ((np.arange(len(junto), dtype=np.float64) + inicio) / self.taxa).astype(np.float32)
        y = _processar(junto, t, self.estilo, self.taxa)[len(self.anterior):]
        self.anterior = junto[-len(self.anterior):]
        self.amostras_passadas += len(x)
        y = np.tanh(y * GANHO[self.estilo] * 1.4)
        return (y * 32767).astype(np.int16).tobytes()


def criar_efeito(taxa: int = 24000) -> EfeitoUltron | None:
    """Lê JARVIS_EFEITO_ULTRON do ambiente e devolve o efeito, ou None se estiver desligado."""
    valor = os.environ.get("JARVIS_EFEITO_ULTRON", "1").strip().lower()
    if valor in {"0", "false", "no", "off", "nao", "não", ""}:
        return None
    return EfeitoUltron("robo" if valor == "robo" else "ultron", taxa)
