"""Como chamar o Jarvis Ultron: 2 palmas (padrão) ou "Hey Jarvis".

Com palmas (JARVIS_ATIVACAO=ambos, o padrão; "palmas" = só palmas):
  - bata 2 palmas ou diga "Hey Jarvis": o Jarvis começa a ouvir (a "chamada" começa);
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
  JARVIS_ATIVACAO=ambos            (ambos, palmas ou voz)
  JARVIS_PALAVRA_ATIVACAO=1        (0 = começa no modo mãos livres, sempre ouvindo)
  JARVIS_SENSIBILIDADE=0.5         ("Hey Jarvis": menor = aceita com mais facilidade)
  JARVIS_JANELA_CONVERSA=20        ("Hey Jarvis": segundos ouvindo depois da última fala)
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from pathlib import Path
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

    def __init__(self, sensibilidade: float | None = None):
        # JARVIS_SENSIBILIDADE_PALMAS: 1 = padrão; maior (ex.: 1.5) aceita palmas mais fracas;
        # menor (ex.: 0.7) é mais rigoroso.
        if sensibilidade is None:
            sensibilidade = _numero("JARVIS_SENSIBILIDADE_PALMAS", 1.0)
        s = max(0.3, min(3.0, float(sensibilidade)))
        self.minimo = 0.02 / s  # volume mínimo de uma palma
        self.subida = max(3.0, 8.0 / s)  # quantas vezes mais alta que o instante anterior
        self.agudo_min = 0.18 / s
        self.cauda_max = min(0.8, 0.5 * s)  # quanto do som pode sobrar logo depois
        self.ruido = 0.002
        self._pendente = np.zeros(0, dtype=np.float32)
        self._forca: list[float] = []  # volume de cada pedaço de 5 ms
        self._agudo: list[float] = []  # quanto do som é agudo, em cada pedaço
        self._inicio = 0  # número do pedaço guardado em _forca[0]
        self._proximo = 0  # próximo pedaço a avaliar
        self._estalos: list[float] = []  # horas (s) dos últimos sons com cara de palma
        self._primeira = None
        self._confirmar = None  # hora da 2ª palma, esperando o silêncio depois dela

    def medir(self, k: int) -> dict:
        """As medidas do pedaço k (também usadas pelo 'Testar Palmas')."""
        i = k - self._inicio
        forca = self._forca[i]
        antes = self._forca[max(0, i - self.ANTES):i]
        base = (sum(antes) / len(antes)) if antes else self.ruido
        depois = self._forca[i + 6:i + self.DEPOIS]
        return {
            "forca": forca,
            "subida": forca / max(base, self.ruido),
            "agudo": max(self._agudo[i], self._agudo[i + 1]),
            "cauda": (sum(depois) / len(depois)) / max(forca, 1e-9),
        }

    def motivo_recusa(self, m: dict) -> str:
        """'' se parece palma; senão, o que faltou."""
        if m["forca"] < max(self.minimo, self.ruido * 8.0):
            return "fraca"
        if m["subida"] < self.subida:
            return "não começou de repente"
        if m["agudo"] < self.agudo_min:
            return "som grave (parece voz)"
        if m["cauda"] > self.cauda_max:
            return "som longo (parece voz)"
        return ""

    def _analisar(self, k: int) -> bool:
        return not self.motivo_recusa(self.medir(k))

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
                print("[Palmas] 3 estalos seguidos: ignorado (bata só 2).")
            elif self._eh_segunda(agora):
                self._confirmar = agora
                self._primeira = None
                print("[Palmas] 2ª palma")
            else:
                antes = [t for t in self._estalos if agora - t < self.SOSSEGO_ANTES]
                self._primeira = None if antes else agora
                if self._primeira is not None:
                    print("[Palmas] 1ª palma")
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


# Sons curtos de aviso (tocados no computador, sem internet): (frequência Hz, duração ms)
SONS_AVISO = {
    "ouvindo": ((660, 90), (990, 140)),            # sobe: chamada aberta
    "aguardando": ((990, 90), (660, 140)),         # desce: chamada encerrada
    "maos_livres": ((660, 70), (830, 70), (990, 120)),
}


def tocar_aviso(estado: str) -> None:
    """Toca o som do estado sem travar o Jarvis (JARVIS_SOM_AVISO=0 desliga)."""
    notas = SONS_AVISO.get(estado.split(":")[0])
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


ARQUIVO_PREFERENCIA = Path.home() / ".jarvis" / "config" / "escuta.json"


def palmas_preferidas() -> bool:
    """Palmas ligadas? A escolha feita por voz fica guardada; senão vale o .env
    (JARVIS_ATIVACAO=ambos/palmas liga; o padrão é só "Hey Jarvis")."""
    try:
        return bool(json.loads(ARQUIVO_PREFERENCIA.read_text(encoding="utf-8"))["palmas"])
    except (OSError, ValueError, KeyError, TypeError):
        return gatilho_configurado() in ("ambos", "palmas")


def guardar_preferencia_palmas(ligadas: bool) -> None:
    try:
        ARQUIVO_PREFERENCIA.parent.mkdir(parents=True, exist_ok=True)
        ARQUIVO_PREFERENCIA.write_text(json.dumps({"palmas": bool(ligadas)}), encoding="utf-8")
    except OSError as erro:
        print(f"[Palmas] Não consegui guardar a escolha: {erro}")


def gatilho_configurado() -> str:
    """'voz' (padrão: só "Hey Jarvis"), 'ambos' (palmas ou "Hey Jarvis") ou 'palmas'."""
    valor = os.environ.get("JARVIS_ATIVACAO", "voz").strip().lower()
    if valor in {"palmas", "palma"}:
        return "palmas"
    if valor in {"ambos", "os dois"}:
        return "ambos"
    return "voz"


class PortaoDeVoz:
    def __init__(self, detector=None, *, ativo: bool = True, limiar: float = 0.5,
                 janela: float = 20.0, avisar: Callable[[str], None] | None = None,
                 relogio: Callable[[], float] = time.monotonic, palmas: DetectorDePalmas | None = None,
                 usar_palmas: bool | None = None):
        self.detector = detector
        self.palmas = palmas
        # Palmas são opcionais: o usuário liga ou desliga ("Jarvis, ligar palmas").
        self.usar_palmas = bool(palmas is not None if usar_palmas is None else usar_palmas and palmas is not None)
        # Chamado com "ouvindo", "aguardando" ou "maos_livres" quando o estado muda
        # (o Jarvis usa para tocar o som e mostrar o selo na tela).
        self.ao_mudar: Callable[[str], None] = lambda estado: None
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
        if not self.usar_palmas:
            return 'diga "Hey Jarvis"'
        return 'bata 2 palmas ou diga "Hey Jarvis"' if self.detector is not None else "bata 2 palmas"

    def ligar_palmas(self, ligar: bool, guardar: bool = True) -> bool:
        """Liga/desliga as palmas. False se não der (sem detector de palmas, ou sem "Hey Jarvis"
        para ficar no lugar delas)."""
        ligar = bool(ligar)
        if (ligar and self.palmas is None) or (not ligar and self.detector is None):
            return False
        with self._trava:
            self.usar_palmas = ligar
            if self.palmas is not None:
                self.palmas.reiniciar()
            if self.acordado:  # a conversa continua; sem palmas, fecha sozinha após o silêncio
                self.acordado_ate = self.relogio() + self.janela
        if guardar:
            guardar_preferencia_palmas(ligar)
        self._avisar_mudanca()
        return True

    @classmethod
    def da_configuracao(cls, avisar: Callable[[str], None] | None = None) -> "PortaoDeVoz":
        chamada = _ligado("JARVIS_PALAVRA_ATIVACAO")
        usar_palmas = palmas_preferidas()
        # O "Hey Jarvis" é carregado sempre (mesmo em mãos livres), para dar para trocar por voz.
        try:
            detector = carregar_detector()
        except Exception as erro:
            print(f"[Ativação] \"Hey Jarvis\" indisponível ({erro}).")
            detector = None
            usar_palmas = True  # sobra só a palma para chamar
        portao = cls(detector, ativo=chamada, limiar=_numero("JARVIS_SENSIBILIDADE", 0.5),
                     janela=_numero("JARVIS_JANELA_CONVERSA", 20.0), avisar=avisar,
                     palmas=DetectorDePalmas(), usar_palmas=usar_palmas)
        print(f"[Ativação] Palmas {'ligadas' if portao.usar_palmas else 'desligadas'}"
              " (\"Jarvis, ligar palmas\" / \"Jarvis, desligar palmas\").")
        portao.avisar(f"SYS: {portao.como_chamar.capitalize()} para falar comigo." if chamada
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
        if self.usar_palmas:
            return self._processar_palmas(audio)
        if self.detector is None:
            return None
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

    def _processar_palmas(self, audio) -> bytes | None:
        """2 palmas começam a chamada; mais 2 palmas terminam. Sem tempo limite."""
        with self._trava:
            if not self.palmas.processar(audio):
                if self.acordado:
                    return audio.tobytes()
                return self._ouvir_hey_jarvis(audio)
            self.acordado = not self.acordado
            if not self.acordado:
                self._reiniciar_detector()
                self._anteriores.clear()
                self._amostras_anteriores = 0
            if self.acordado:
                self.avisar("SYS: Estou ouvindo. Bata 2 palmas para encerrar.")
            else:
                self.avisar("SYS: Chamada encerrada. Bata 2 palmas para falar comigo.")
            self._avisar_mudanca()
            return None  # o som das palmas não vai para a IA

    def _ouvir_hey_jarvis(self, audio) -> bytes | None:
        """Com a chamada fechada: "Hey Jarvis" também abre (e o pedido falado junto vai inteiro)."""
        if self.detector is None:
            return None
        self._guardar(audio)
        self._pendente = np.concatenate([self._pendente, audio])
        disparou = False
        while len(self._pendente) >= QUADRO:
            quadro, self._pendente = self._pendente[:QUADRO], self._pendente[QUADRO:]
            if max(self.detector.predict(quadro).values(), default=0.0) >= self.limiar:
                disparou = True
        if not disparou:
            return None
        self.acordado = True
        dados = np.concatenate(list(self._anteriores)).tobytes()
        self._anteriores.clear()
        self._amostras_anteriores = 0
        self._pendente = np.zeros(0, dtype=np.int16)
        self.avisar("SYS: Estou ouvindo. Bata 2 palmas para encerrar.")
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


_LIGAR_PALMAS = ("ligar palmas", "liga as palmas", "ligar as palmas", "ativar palmas", "ativa as palmas",
                 "ativar as palmas", "ligar a palma", "ativar a palma")
_DESLIGAR_PALMAS = ("desligar palmas", "desliga as palmas", "desligar as palmas", "desativar palmas",
                    "desativa as palmas", "desativar as palmas", "desligar a palma", "desativar a palma")


def palmas_pedido(fala: str) -> bool | None:
    """True = ligar palmas, False = desligar, None = a fala não pediu isso."""
    import unicodedata

    texto = unicodedata.normalize("NFKD", (fala or "").lower())
    texto = " ".join("".join(c for c in texto if not unicodedata.combining(c)).replace(",", " ").split())
    if any(frase in texto for frase in _DESLIGAR_PALMAS):
        return False
    if any(frase in texto for frase in _LIGAR_PALMAS):
        return True
    return None
