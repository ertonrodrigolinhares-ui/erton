"""Fala (alto-falante) e escuta (microfone) do Jarvis.

Vozes disponíveis:
- Vozes neurais da Microsoft (edge-tts): gratuitas, naturais, várias em português. Precisam de internet.
- ElevenLabs: as mais humanas, com a sua própria chave (plano grátis pequeno ou pago).
- Voz do Windows: funciona sem internet, mas é robótica. Também é a reserva se as outras falharem.

Efeitos (em qualquer voz neural): Ultron (metálico), mais grave e robô.
O reconhecimento de fala usa o serviço gratuito do Google (não precisa de chave).
Todas as bibliotecas de voz são opcionais: sem elas, o Jarvis funciona só com texto.
"""

import asyncio
import queue
import threading

try:
    import pyttsx3
except ImportError:  # pragma: no cover - depende do ambiente
    pyttsx3 = None

try:
    import speech_recognition as sr
except ImportError:  # pragma: no cover - depende do ambiente
    sr = None

try:
    import numpy as np
except ImportError:  # pragma: no cover - depende do ambiente
    np = None

try:
    import edge_tts
    import miniaudio
except ImportError:  # pragma: no cover - depende do ambiente
    edge_tts = miniaudio = None

try:
    import pyaudio
except ImportError:  # pragma: no cover - depende do ambiente
    pyaudio = None

TAXA = 24000  # amostras por segundo das vozes neurais

# chave -> (nome na tela, voz da Microsoft ou None)
VOZES = {
    "antonio": ("Antonio - masculina (Brasil)", "pt-BR-AntonioNeural"),
    "francisca": ("Francisca - feminina (Brasil)", "pt-BR-FranciscaNeural"),
    "thalita": ("Thalita - feminina (Brasil)", "pt-BR-ThalitaMultilingualNeural"),
    "duarte": ("Duarte - masculina (Portugal)", "pt-PT-DuarteNeural"),
    "raquel": ("Raquel - feminina (Portugal)", "pt-PT-RaquelNeural"),
    "andrew": ("Andrew - masculina, sotaque americano", "en-US-AndrewMultilingualNeural"),
    "brian": ("Brian - masculina grave, sotaque americano", "en-US-BrianMultilingualNeural"),
    "ava": ("Ava - feminina, sotaque americano", "en-US-AvaMultilingualNeural"),
    "emma": ("Emma - feminina, sotaque americano", "en-US-EmmaMultilingualNeural"),
    "remy": ("Rémy - masculina, sotaque francês", "fr-FR-RemyMultilingualNeural"),
    "florian": ("Florian - masculina, sotaque alemão", "de-DE-FlorianMultilingualNeural"),
    "giuseppe": ("Giuseppe - masculina, sotaque italiano", "it-IT-GiuseppeMultilingualNeural"),
    "elevenlabs": ("ElevenLabs (precisa de chave)", None),
    "windows": ("Windows (sem internet, robótica)", None),
}

# chave -> (nome na tela, ajuste de tom, ajuste de velocidade)
EFEITOS = {
    "nenhum": ("Sem efeito", "+0Hz", "+0%"),
    "ultron": ("Ultron (metálico)", "-14Hz", "-8%"),
    "grave": ("Mais grave", "-20Hz", "-5%"),
    "robo": ("Robô", "-6Hz", "-3%"),
}

ELEVENLABS_VOZ_PADRAO = "pNInz6obpgDQGcFmaJgB"  # "Adam", voz masculina da biblioteca


def voz_neural_disponivel() -> bool:
    return None not in (edge_tts, miniaudio, np, pyaudio)


def fala_disponivel() -> bool:
    return pyttsx3 is not None or voz_neural_disponivel()


def microfone_disponivel() -> bool:
    if sr is None:
        return False
    try:
        return len(sr.Microphone.list_microphone_names()) > 0
    except Exception:  # PyAudio ausente ou sem dispositivo de áudio
        return False


# ---------- síntese ----------

def sintetizar_microsoft(texto: str, voz: str, tom: str = "+0Hz", velocidade: str = "+0%"):
    """Gera a fala com uma voz neural da Microsoft e devolve as amostras (int16, 24 kHz)."""
    async def baixar() -> bytes:
        comunicacao = edge_tts.Communicate(texto, voz, rate=velocidade, pitch=tom)
        return b"".join([p["data"] async for p in comunicacao.stream() if p["type"] == "audio"])

    mp3 = asyncio.run(baixar())
    audio = miniaudio.decode(mp3, output_format=miniaudio.SampleFormat.SIGNED16,
                             nchannels=1, sample_rate=TAXA)
    return np.array(audio.samples, dtype=np.int16)


def sintetizar_elevenlabs(texto: str, chave: str, voz_id: str):
    """Gera a fala pela API da ElevenLabs e devolve as amostras (int16, 24 kHz)."""
    import httpx

    resposta = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voz_id or ELEVENLABS_VOZ_PADRAO}",
        params={"output_format": "pcm_24000"},
        headers={"xi-api-key": chave},
        json={"text": texto, "model_id": "eleven_multilingual_v2"},
        timeout=60,
    )
    resposta.raise_for_status()
    return np.frombuffer(resposta.content, dtype=np.int16)


# ---------- efeitos ----------

def _atrasar(sinal, amostras: int):
    saida = np.zeros_like(sinal)
    if amostras < len(sinal):
        saida[amostras:] = sinal[:len(sinal) - amostras]
    return saida


def aplicar_efeito(amostras, efeito: str, taxa: int = TAXA):
    """Aplica um efeito de voz às amostras int16 e devolve int16."""
    if efeito not in ("ultron", "robo") or len(amostras) == 0:
        return amostras
    x = amostras.astype(np.float32) / 32768.0
    t = np.arange(len(x), dtype=np.float32) / taxa

    if efeito == "ultron":
        # Modulação em anel suave + ressonância metálica + uma segunda voz levemente atrasada.
        anel = x * np.sin(2 * np.pi * 38 * t)
        y = 0.7 * x + 0.3 * anel
        atraso = int(0.009 * taxa)
        y = y + 0.45 * _atrasar(y, atraso) + 0.2 * _atrasar(y, 2 * atraso) + 0.1 * _atrasar(y, 3 * atraso)
        y = y + 0.3 * _atrasar(y, int(0.028 * taxa))
    else:  # robo: modulação em anel forte, som de máquina
        y = 0.35 * x + 0.65 * x * np.sin(2 * np.pi * 70 * t)
        y = y + 0.4 * _atrasar(y, int(0.006 * taxa))

    pico = float(np.max(np.abs(y))) or 1.0
    return (y / pico * 0.9 * 32767).astype(np.int16)


def tocar(amostras, taxa: int = TAXA) -> None:
    sistema = pyaudio.PyAudio()
    try:
        saida = sistema.open(format=pyaudio.paInt16, channels=1, rate=taxa, output=True)
        saida.write(amostras.tobytes())
        saida.stop_stream()
        saida.close()
    finally:
        sistema.terminate()


# ---------- quem fala ----------

class Falador:
    """Fala em segundo plano, um texto de cada vez, sem travar a janela.

    Os atributos voz/efeito/chave_elevenlabs/voz_elevenlabs podem ser trocados a qualquer momento.
    """

    def __init__(self, voz: str = "antonio", efeito: str = "nenhum",
                 chave_elevenlabs: str = "", voz_elevenlabs: str = ""):
        self.voz = voz if voz in VOZES else "antonio"
        self.efeito = efeito if efeito in EFEITOS else "nenhum"
        self.chave_elevenlabs = chave_elevenlabs
        self.voz_elevenlabs = voz_elevenlabs
        self.ultimo_erro = ""
        self.fila: queue.Queue = queue.Queue()
        if fala_disponivel():
            threading.Thread(target=self._trabalhar, daemon=True).start()

    @classmethod
    def da_config(cls, config) -> "Falador":
        return cls(config.voz, config.efeito_voz, config.chave_elevenlabs, config.voz_elevenlabs)

    def _gerar(self, texto: str):
        _, tom, velocidade = EFEITOS[self.efeito]
        if self.voz == "elevenlabs":
            if not self.chave_elevenlabs:
                raise RuntimeError("falta a chave da ElevenLabs")
            amostras = sintetizar_elevenlabs(texto, self.chave_elevenlabs, self.voz_elevenlabs)
        else:
            amostras = sintetizar_microsoft(texto, VOZES[self.voz][1], tom, velocidade)
        return aplicar_efeito(amostras, self.efeito)

    def _trabalhar(self) -> None:
        motor_windows = None
        while True:
            texto = self.fila.get()
            try:
                falou = False
                if self.voz != "windows" and voz_neural_disponivel():
                    try:
                        tocar(self._gerar(texto))
                        falou = True
                        self.ultimo_erro = ""
                    except Exception as erro:  # sem internet, chave errada... usa a voz do Windows
                        self.ultimo_erro = str(erro)
                if not falou and pyttsx3 is not None:
                    if motor_windows is None:
                        motor_windows = _criar_motor_windows()
                    motor_windows.say(texto)
                    motor_windows.runAndWait()
            except Exception:
                pass
            finally:
                self.fila.task_done()

    def falar(self, texto: str) -> None:
        if fala_disponivel():
            self.fila.put(texto)

    def aguardar(self) -> None:
        """Espera terminar de falar (para o microfone não ouvir o próprio Jarvis)."""
        if fala_disponivel():
            self.fila.join()


def _criar_motor_windows():
    motor = pyttsx3.init()
    for voz in motor.getProperty("voices"):
        identificacao = f"{voz.id} {voz.name}".lower()
        if "pt" in identificacao or "portug" in identificacao or "brazil" in identificacao:
            motor.setProperty("voice", voz.id)
            break
    motor.setProperty("rate", 185)
    return motor


# ---------- ouvir ----------

def ouvir_microfone(idioma: str = "pt-BR") -> str:
    """Escuta uma frase pelo microfone e devolve o texto ("" se não entendeu)."""
    reconhecedor = sr.Recognizer()
    with sr.Microphone() as fonte:
        reconhecedor.adjust_for_ambient_noise(fonte, duration=0.5)
        try:
            audio = reconhecedor.listen(fonte, timeout=8, phrase_time_limit=15)
        except sr.WaitTimeoutError:
            return ""
    try:
        return reconhecedor.recognize_google(audio, language=idioma).strip()
    except (sr.UnknownValueError, sr.RequestError):
        return ""
