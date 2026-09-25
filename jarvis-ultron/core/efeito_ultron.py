"""Efeito de voz metálica "Ultron" aplicado ao áudio do Gemini Live enquanto ele chega.

Ligado por padrão. Para desligar, coloque JARVIS_EFEITO_ULTRON=0 no arquivo .env.
Estilos: "leve" (padrão, e também "1"): metálico sem eco; "ultron": metálico com eco (soa
mais "atrasado"); "robo": robô.
"""

from __future__ import annotations

import os

import numpy as np

HISTORICO_SEGUNDOS = 0.06
GANHO = {"ultron": 0.42, "robo": 0.75, "leve": 0.75}


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
    if estilo == "leve":
        # Metálico sem eco: só a modulação em anel (a voz não soa "atrasada").
        return 0.72 * x + 0.28 * x * np.sin(2 * np.pi * 38 * t)
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
    valor = os.environ.get("JARVIS_EFEITO_ULTRON", "leve").strip().lower()
    if valor in {"0", "false", "no", "off", "nao", "não", ""}:
        return None
    if valor in {"robo", "robô"}:
        return EfeitoUltron("robo", taxa)
    if valor in {"ultron", "eco", "forte"}:
        return EfeitoUltron("ultron", taxa)
    return EfeitoUltron("leve", taxa)  # padrão, e também "1"


def nivel_da_voz(pcm: bytes) -> float:
    """Volume de um pedaço de áudio int16 em escala de 0 a 1 (usado para animar a esfera)."""
    if not pcm:
        return 0.0
    x = np.frombuffer(pcm[: len(pcm) - len(pcm) % 2], dtype=np.int16).astype(np.float32)
    if x.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(x * x)))
    if rms < 1.0:
        return 0.0
    decibeis = 20.0 * np.log10(rms)  # fala baixa ~50 dB, fala forte ~80 dB
    return float(min(1.0, max(0.0, (decibeis - 50.0) / 28.0)))
