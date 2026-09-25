"""Como chamar o Jarvis Ultron: 2 palmas (padrão) ou "Hey Jarvis".

Com palmas (JARVIS_ATIVACAO=palmas, o padrão):
  - bata 2 palmas: o Jarvis começa a ouvir (a "chamada" começa);
  - bata mais 2 palmas: ele para de ouvir (a "chamada" termina).
  Tudo roda no próprio computador; enquanto a chamada está desligada, nenhum áudio vai
  para a internet.

Com a palavra (JARVIS_ATIVACAO=voz): só ouve depois de "Hey Jarvis" (openWakeWord, sem
internet) e volta a dormir após alguns segundos de silêncio.

Dois modos, que também podem ser trocados por voz:
  - modo chamada (padrão): só responde depois das palmas (ou do "Hey Jarvis");
  - modo mãos livres: responde a tudo o que for falado.
  "Jarvis, modo mãos livres" / "Jarvis, modo chamada".

Configuração no .env:
  JARVIS_ATIVACAO=palmas           (palmas ou voz)
  JARVIS_PALAVRA_ATIVACAO=1        (0 = começa no modo mãos livres, sempre ouvindo)
  JARVIS_SENSIBILIDADE=0.5         ("Hey Jarvis": menor = aceita com mais facilidade)
  JARVIS_JANELA_CONVERSA=20        ("Hey Jarvis": segundos ouvindo depois da última fala)
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


class DetectorDePalmas:
    """Reconhece 2 palmas seguidas no áudio do microfone (int16, 16 kHz).

    Uma palma tem três marcas que a fala não tem juntas: começa de repente (bem mais alta que
    o instante anterior), é aguda (som "chiado", cheio de frequências altas) e acaba rápido
    (em poucos centésimos de segundo já quase sumiu). Duas palmas contam se vierem entre
    0,2 e 1,5 segundo uma da outra, sem outros estalos no meio ou logo antes (digitação,
    por exemplo, faz vários estalos seguidos e não conta).
    """

    PASSO = 80  # 5 ms
    ANTES = 10  # 50 ms antes, para medir o "de repente"
    DEPOIS = 24  # até 120 ms depois, para medir o "acaba rápido"
    INTERVALO_MIN = 0.20
    INTERVALO_MAX = 1.5
    SOSSEGO_ANTES = 0.5  # sem estalos neste tempo antes da primeira palma
    SOSSEGO_DEPOIS = 0.4  # nem logo depois da segunda

    def __init__(self):
        self.ruido = 0.002
        self._pendente = np.zeros(0, dtype=np.float32)
        self._forca: list[float] = []  # volume de cada pedaço de 5 ms
        self._agudo: list[float] = []  # quanto do som é agudo, em cada pedaço
        self._inicio = 0  # número do pedaço guardado em _forca[0]
        self._proximo = 0  # próximo pedaço a avaliar
        self._estalos: list[float] = []  # horas (s) dos últimos sons com cara de palma
        self._primeira = None
        self._confirmar = None  # hora da 2ª palma, esperando o silêncio depois dela

    def _analisar(self, k: int) -> bool:
        i = k - self._inicio
        forca = self._forca[i]
        antes = self._forca[max(0, i - self.ANTES):i]
        base = (sum(antes) / len(antes)) if antes else self.ruido
        depois = self._forca[i + 6:i + self.DEPOIS]
        cauda = sum(depois) / len(depois)
        return (forca >= max(0.03, self.ruido * 12.0)
                and forca >= 5.0 * max(base, self.ruido)  # começa de repente
                and max(self._agudo[i], self._agudo[i + 1]) >= 0.25  # é agudo
                and cauda <= 0.3 * forca)  # e acaba rápido

    def processar(self, pedaco) -> bool:
        """True quando acabou de ouvir a segunda palma."""
        audio = np.asarray(pedaco, dtype=np.int16).reshape(-1).astype(np.float32) / 32768.0
        self._pendente = np.concatenate([self._pendente, audio])
        while len(self._pendente) >= self.PASSO:
            bloco, self._pendente = self._pendente[:self.PASSO], self._pendente[self.PASSO:]
            energia = float(np.mean(bloco * bloco))
            forca = energia ** 0.5
            self._forca.append(forca)
            self._agudo.append(float(np.mean(np.diff(bloco) ** 2)) / max(energia, 1e-12))
            if forca < self.ruido * 4.0:  # só o som baixo ensina o nível do ambiente
                self.ruido = max(1e-4, self.ruido * 0.98 + forca * 0.02)

        dupla = False
        ultimo = self._inicio + len(self._forca) - 1
        while self._proximo + self.DEPOIS <= ultimo:
            k = self._proximo
            self._proximo += 1
            agora = k * self.PASSO / TAXA
            if self._confirmar is not None and agora - self._confirmar >= self.SOSSEGO_DEPOIS:
                dupla = True  # 2 palmas e depois silêncio: vale
                self._confirmar = None
            if k - self._inicio < 1 or not self._analisar(k):
                continue
            if self._estalos and agora - self._estalos[-1] < self.INTERVALO_MIN:
                self._estalos[-1] = agora  # a mesma palma (ou o eco dela)
                continue
            if self._confirmar is not None:  # um 3º estalo logo depois: era barulho, não palmas
                self._confirmar = self._primeira = None
            elif self._eh_segunda(agora):
                self._confirmar = agora
                self._primeira = None
            else:
                antes = [t for t in self._estalos if agora - t < self.SOSSEGO_ANTES]
                self._primeira = None if antes else agora
            self._estalos = [t for t in self._estalos if agora - t < 3.0] + [agora]

        sobra = self._proximo - self.ANTES - self._inicio
        if sobra > 400:  # guarda só os últimos ~2 s
            del self._forca[:sobra], self._agudo[:sobra]
            self._inicio += sobra
        return dupla

    def _eh_segunda(self, agora: float) -> bool:
        if self._primeira is None or agora - self._primeira > self.INTERVALO_MAX:
            return False
        no_meio = [t for t in self._estalos if self._primeira < t < agora]
        return not no_meio

    def reiniciar(self) -> None:
        self._primeira = self._confirmar = None
        self._estalos = []


def gatilho_configurado() -> str:
    valor = os.environ.get("JARVIS_ATIVACAO", "palmas").strip().lower()
    return "voz" if valor in {"voz", "hey jarvis", "palavra"} else "palmas"


class PortaoDeVoz:
    def __init__(self, detector=None, *, ativo: bool = True, limiar: float = 0.5,
                 janela: float = 20.0, avisar: Callable[[str], None] | None = None,
                 relogio: Callable[[], float] = time.monotonic, palmas: DetectorDePalmas | None = None):
        self.detector = detector
        self.palmas = palmas
        ativo = ativo and (detector is not None or palmas is not None)
        self.ativo = bool(ativo)
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
    def como_chamar(self) -> str:
        return "bata 2 palmas" if self.palmas is not None else 'diga "Hey Jarvis"'

    @classmethod
    def da_configuracao(cls, avisar: Callable[[str], None] | None = None) -> "PortaoDeVoz":
        chamada = _ligado("JARVIS_PALAVRA_ATIVACAO")
        if gatilho_configurado() == "palmas":
            portao = cls(None, ativo=chamada, avisar=avisar, palmas=DetectorDePalmas())
            portao.avisar("SYS: Bata 2 palmas para falar comigo (e mais 2 para encerrar)." if chamada
                          else "SYS: Modo mãos livres: estou ouvindo tudo.")
            return portao
        # O detector é carregado mesmo começando em mãos livres, para dar para trocar por voz.
        try:
            detector = carregar_detector()
        except Exception as erro:
            print(f"[Ativação] Detector indisponível ({erro}); ouvindo sempre.")
            if avisar:
                avisar("SYS: Palavra de ativação indisponível; o Jarvis vai ouvir sempre.")
            return cls(None, ativo=False, avisar=avisar)
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
            if self.detector is None and self.palmas is None:
                return False
            self.ativo = True
            self.acordado = False  # volta a esperar as palmas / o "Hey Jarvis"
            if self.palmas is not None:
                self.palmas.reiniciar()
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
        if self.palmas is not None:
            return self._processar_palmas(audio)
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

    def _processar_palmas(self, audio) -> bytes | None:
        """2 palmas começam a chamada; mais 2 palmas terminam. Sem tempo limite."""
        with self._trava:
            if not self.palmas.processar(audio):
                return audio.tobytes() if self.acordado else None
            self.acordado = not self.acordado
            if self.acordado:
                self.avisar("SYS: Estou ouvindo. Bata 2 palmas para encerrar.")
            else:
                self.avisar("SYS: Chamada encerrada. Bata 2 palmas para falar comigo.")
            return None  # o som das palmas não vai para a IA

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
