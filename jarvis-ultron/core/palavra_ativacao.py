"""Como chamar o Jarvis Ultron: "Hey Jarvis" ou os modos chamada / mãos livres.

- Modo chamada (padrão): só responde depois de "Hey Jarvis" (openWakeWord, roda no computador,
  sem internet) e volta a esperar após alguns segundos de silêncio. Enquanto espera, nenhum
  áudio vai para a internet.
- Modo mãos livres: responde a tudo o que for falado.

Troca de modo: pelos botões da tela ou falando "Jarvis, modo chamada" / "Jarvis, modo mãos livres".

Configuração no .env:
  JARVIS_PALAVRA_ATIVACAO=1        (0 = começa no modo mãos livres, sempre ouvindo)
  JARVIS_SENSIBILIDADE=0.5         (menor = aceita com mais facilidade; maior = mais rigoroso)
  JARVIS_JANELA_CONVERSA=20        (segundos ouvindo depois da última fala)
  JARVIS_SOM_AVISO=1               (0 = sem o som curto quando o modo muda)
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


# Sons curtos de aviso (tocados no computador, sem internet): (frequência Hz, duração ms)
SONS_AVISO = {
    "ouvindo": ((660, 90), (990, 140)),            # sobe: ouvindo
    "aguardando": ((990, 90), (660, 140)),         # desce: voltou a esperar o "Hey Jarvis"
    "maos_livres": ((660, 70), (830, 70), (990, 120)),
}


def tocar_aviso(estado: str) -> None:
    """Toca o som do estado sem travar o Jarvis (JARVIS_SOM_AVISO=0 desliga)."""
    notas = SONS_AVISO.get(estado)
    if not notas or not _ligado("JARVIS_SOM_AVISO"):
        return

    def tocar():
        try:
            import winsound  # Windows
            for freq, ms in notas:
                winsound.Beep(freq, ms)
            return
        except ImportError:
            pass
        except Exception as erro:  # pragma: no cover - depende do som do computador
            print(f"[Aviso] Som indisponível: {erro}")
            return
        try:
            import sounddevice as sd
            taxa = 22050
            partes = [0.25 * np.sin(2 * np.pi * f * np.arange(int(taxa * ms / 1000)) / taxa) for f, ms in notas]
            sd.play(np.concatenate(partes).astype(np.float32), taxa)
        except Exception as erro:  # pragma: no cover
            print(f"[Aviso] Som indisponível: {erro}")

    threading.Thread(target=tocar, daemon=True, name="SomAviso").start()


class PortaoDeVoz:
    def __init__(self, detector=None, *, ativo: bool = True, limiar: float = 0.5,
                 janela: float = 20.0, avisar: Callable[[str], None] | None = None,
                 relogio: Callable[[], float] = time.monotonic):
        self.detector = detector
        # Chamado com "ouvindo", "aguardando" ou "maos_livres" quando o estado muda
        # (o Jarvis usa para tocar o som e mostrar o selo na tela).
        self.ao_mudar: Callable[[str], None] = lambda estado: None
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

    @property
    def estado(self) -> str:
        if not self.ativo:
            return "maos_livres"
        return "ouvindo" if self.acordado else "aguardando"

    def _avisar_mudanca(self) -> None:
        try:
            self.ao_mudar(self.estado)
        except Exception as erro:  # o aviso nunca pode derrubar o microfone
            print(f"[Ativação] Aviso falhou: {erro}")

    @property
    def como_chamar(self) -> str:
        return 'diga "Hey Jarvis"'

    @classmethod
    def da_configuracao(cls, avisar: Callable[[str], None] | None = None) -> "PortaoDeVoz":
        # O detector é carregado mesmo começando em mãos livres, para dar para trocar depois.
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
                self._avisar_mudanca()
                return True
            if self.detector is None:
                return False
            self.ativo = True
            self.acordado = False  # volta a esperar o "Hey Jarvis"
            self._pendente = np.zeros(0, dtype=np.int16)
            self._anteriores.clear()
            self._amostras_anteriores = 0
            self._reiniciar_detector()
            self._avisar_mudanca()
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
                self._avisar_mudanca()

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
            self._avisar_mudanca()
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
