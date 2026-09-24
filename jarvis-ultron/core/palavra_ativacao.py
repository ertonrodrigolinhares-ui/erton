"""Palavra de ativação do Jarvis Ultron: só ouve depois de "Hey Jarvis".

O detector (openWakeWord, modelo "hey_jarvis") roda no próprio computador, sem internet.
Enquanto não ouve a palavra, nenhum áudio vai para o Google. Depois de ativado, o Jarvis
fica ouvindo durante a conversa e volta a dormir após alguns segundos de silêncio.

Dois modos, que também podem ser trocados por voz:
  - modo chamada (padrão): só responde depois de "Hey Jarvis";
  - modo mãos livres: responde a tudo o que for falado.
  "Hey Jarvis, modo mãos livres" / "Jarvis, modo chamada".

Configuração no .env:
  JARVIS_PALAVRA_ATIVACAO=1        (0 = começa no modo mãos livres, sempre ouvindo)
  JARVIS_SENSIBILIDADE=0.5         (menor = aceita com mais facilidade; maior = mais rigoroso)
  JARVIS_JANELA_CONVERSA=20        (segundos ouvindo depois da última fala)
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Callable

import numpy as np

TAXA = 16000
QUADRO = 1280  # 80 ms, o tamanho que o detector espera
PRE_GRAVACAO = 1.5  # segundos guardados antes da ativação (para não cortar o começo do pedido)


def _ligado(nome: str, padrao: str = "1") -> bool:
    return os.environ.get(nome, padrao).strip().lower() not in {"0", "false", "no", "off", "nao", "não", ""}


def _numero(nome: str, padrao: float) -> float:
    try:
        return float(os.environ.get(nome, "") or padrao)
    except ValueError:
        return padrao


def carregar_detector():
    """Carrega o modelo "hey_jarvis" do openWakeWord (funciona nas versões 0.4 a 0.6)."""
    import openwakeword
    from openwakeword.model import Model

    caminhos = [p for p in openwakeword.get_pretrained_model_paths() if "hey_jarvis" in p]
    if caminhos:
        try:
            return Model(wakeword_model_paths=caminhos)  # versão 0.4
        except TypeError:
            pass
    try:  # versões novas: baixa o modelo na primeira vez
        from openwakeword.utils import download_models

        download_models(model_names=["hey_jarvis"])
    except Exception:
        pass
    return Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")


class PortaoDeVoz:
    def __init__(self, detector=None, *, ativo: bool = True, limiar: float = 0.5,
                 janela: float = 20.0, avisar: Callable[[str], None] | None = None,
                 relogio: Callable[[], float] = time.monotonic):
        self.detector = detector
        self.ativo = bool(ativo and detector is not None)
        self.limiar = limiar
        self.janela = janela
        self.avisar = avisar or (lambda texto: None)
        self.relogio = relogio
        self.acordado_ate = 0.0
        self.acordado = False
        self._pendente = np.zeros(0, dtype=np.int16)
        self._anteriores: deque = deque()
        self._amostras_anteriores = 0
        self._trava = threading.Lock()

    @classmethod
    def da_configuracao(cls, avisar: Callable[[str], None] | None = None) -> "PortaoDeVoz":
        # O detector é carregado mesmo começando em mãos livres, para dar para trocar por voz.
        try:
            detector = carregar_detector()
        except Exception as erro:
            print(f"[Ativação] Detector indisponível ({erro}); ouvindo sempre.")
            if avisar:
                avisar("SYS: Palavra de ativação indisponível; o Jarvis vai ouvir sempre.")
            return cls(None, ativo=False, avisar=avisar)
        chamada = _ligado("JARVIS_PALAVRA_ATIVACAO")
        portao = cls(detector, ativo=chamada, limiar=_numero("JARVIS_SENSIBILIDADE", 0.5),
                     janela=_numero("JARVIS_JANELA_CONVERSA", 20.0), avisar=avisar)
        portao.avisar("SYS: Diga \"Hey Jarvis\" para falar comigo." if chamada
                      else "SYS: Modo mãos livres: estou ouvindo tudo.")
        return portao

    @property
    def modo(self) -> str:
        return "chamada" if self.ativo else "maos_livres"

    def definir_modo(self, modo: str) -> bool:
        """'chamada' (só depois de "Hey Jarvis") ou 'maos_livres' (ouve tudo).
        Devolve False se o modo chamada não estiver disponível (detector não carregou)."""
        with self._trava:
            if modo == "maos_livres":
                self.ativo = False
                return True
            if self.detector is None:
                return False
            self.ativo = True
            self.acordado = False  # volta a esperar o "Hey Jarvis"
            self._pendente = np.zeros(0, dtype=np.int16)
            self._anteriores.clear()
            self._amostras_anteriores = 0
            self._reiniciar_detector()
            return True

    def estender(self) -> None:
        """Mantém o Jarvis ouvindo (chamado quando você fala ou quando ele termina de responder)."""
        if self.acordado:
            self.acordado_ate = max(self.acordado_ate, self.relogio() + self.janela)

    def processar(self, pedaco) -> bytes | None:
        """Recebe áudio do microfone (int16, 16 kHz). Devolve o que deve ir para o Gemini, ou None."""
        audio = np.asarray(pedaco, dtype=np.int16).reshape(-1)
        if not self.ativo:
            return audio.tobytes()
        with self._trava:
            agora = self.relogio()
            if self.acordado and agora < self.acordado_ate:
                return audio.tobytes()
            if self.acordado:  # a janela da conversa acabou: volta a dormir
                self.acordado = False
                self._reiniciar_detector()
                self.avisar("SYS: Aguardando \"Hey Jarvis\".")

            self._guardar(audio)
            self._pendente = np.concatenate([self._pendente, audio])
            disparou = False
            while len(self._pendente) >= QUADRO:
                quadro, self._pendente = self._pendente[:QUADRO], self._pendente[QUADRO:]
                pontuacao = max(self.detector.predict(quadro).values(), default=0.0)
                if pontuacao >= self.limiar:
                    disparou = True
            if not disparou:
                return None

            self.acordado = True
            self.acordado_ate = agora + self.janela
            dados = np.concatenate(list(self._anteriores)).tobytes()
            self._anteriores.clear()
            self._amostras_anteriores = 0
            self._pendente = np.zeros(0, dtype=np.int16)
            self.avisar("SYS: Estou ouvindo.")
            return dados

    def _guardar(self, audio) -> None:
        self._anteriores.append(audio)
        self._amostras_anteriores += len(audio)
        while self._amostras_anteriores > PRE_GRAVACAO * TAXA and len(self._anteriores) > 1:
            self._amostras_anteriores -= len(self._anteriores.popleft())

    def _reiniciar_detector(self) -> None:
        reiniciar = getattr(self.detector, "reset", None)
        if callable(reiniciar):
            reiniciar()


_MAOS_LIVRES = ("modo maos livres", "modo mao livre", "modo de maos livres", "modo maos-livres")
_CHAMADA = ("modo chamada", "modo de chamada", "modo chamado")


def modo_pedido(fala: str) -> str | None:
    """Reconhece "modo mãos livres" / "modo chamada" numa fala (sem depender da IA)."""
    import unicodedata

    texto = unicodedata.normalize("NFKD", (fala or "").lower())
    texto = " ".join("".join(c for c in texto if not unicodedata.combining(c)).replace(",", " ").split())
    if any(frase in texto for frase in _MAOS_LIVRES):
        return "maos_livres"
    if any(frase in texto for frase in _CHAMADA):
        return "chamada"
    return None
