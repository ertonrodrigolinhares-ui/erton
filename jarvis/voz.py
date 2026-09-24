"""Fala (alto-falante) e escuta (microfone) do Jarvis.

Vozes disponíveis:
- Vozes neurais da Microsoft (edge-tts): gratuitas, naturais, várias em português. Precisam de internet.
- ElevenLabs: as mais humanas, com a sua própria chave (plano grátis pequeno ou pago).
- Voz do Windows: funciona sem internet, mas é robótica. Também é a reserva se as outras falharem.

Efeitos (em qualquer voz neural): Ultron (metálico), mais grave e robô.
O microfone e o alto-falante usam sounddevice (não precisa do PyAudio, que costuma
falhar na instalação no Windows). O reconhecimento de fala usa o serviço gratuito do Google.
Todas as bibliotecas de voz são opcionais: sem elas, o Jarvis funciona só com texto.
"""

import asyncio
import io
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
except ImportError:  # pragma: no cover - depende do ambiente
    edge_tts = None

try:
    import soundfile
except (ImportError, OSError):  # pragma: no cover - depende do ambiente
    soundfile = None

try:
    import sounddevice
except (ImportError, OSError):  # pragma: no cover - sem PortAudio no sistema
    sounddevice = None

# Componente -> pacote a instalar, para dizer exatamente o que faltou.
COMPONENTES = {
    "edge_tts": ("edge-tts", lambda: edge_tts), "soundfile": ("soundfile", lambda: soundfile),
    "sounddevice": ("sounddevice", lambda: sounddevice), "numpy": ("numpy", lambda: np),
    "speech_recognition": ("SpeechRecognition", lambda: sr), "pyttsx3": ("pyttsx3", lambda: pyttsx3),
}

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


def componentes_faltando() -> list[str]:
    return [pacote for pacote, modulo in COMPONENTES.values() if modulo() is None]


def voz_neural_disponivel() -> bool:
    return None not in (edge_tts, soundfile, sounddevice, np)


def fala_disponivel() -> bool:
    return pyttsx3 is not None or voz_neural_disponivel()


def microfone_disponivel() -> bool:
    return diagnostico_microfone() == ""


def diagnostico_microfone() -> str:
    """"" se o microfone pode ser usado; senão, a explicação do problema."""
    faltando = [p for p in ("SpeechRecognition", "sounddevice", "numpy") if p in componentes_faltando()]
    if faltando:
        return ("Faltam componentes de voz: " + ", ".join(faltando) +
                ". Feche o Jarvis e abra o 'Iniciar Jarvis' de novo para reinstalar.")
    try:
        sounddevice.query_devices(kind="input")
    except Exception:
        return ("Não encontrei um microfone. Verifique se ele está conectado e liberado em "
                "Configurações do Windows > Privacidade e segurança > Microfone "
                "(ative 'Permitir que aplicativos da área de trabalho acessem o microfone').")
    return ""


# ---------- síntese ----------

def sintetizar_microsoft(texto: str, voz: str, tom: str = "+0Hz", velocidade: str = "+0%"):
    """Gera a fala com uma voz neural da Microsoft e devolve as amostras (int16, 24 kHz)."""
    async def baixar() -> bytes:
        comunicacao = edge_tts.Communicate(texto, voz, rate=velocidade, pitch=tom)
        return b"".join([p["data"] async for p in comunicacao.stream() if p["type"] == "audio"])

    mp3 = asyncio.run(baixar())
    amostras, taxa = soundfile.read(io.BytesIO(mp3), dtype="int16")
    if amostras.ndim > 1:
        amostras = amostras[:, 0]
    if taxa != TAXA:  # converte para 24 kHz, a taxa usada pelos efeitos
        tempo = np.arange(int(len(amostras) * TAXA / taxa)) / TAXA
        amostras = np.interp(tempo, np.arange(len(amostras)) / taxa, amostras).astype(np.int16)
    return amostras


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
    sounddevice.play(amostras, taxa)
    sounddevice.wait()


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

TAXA_MICROFONE = 16000
BLOCO = 0.1  # segundos por leitura do microfone


def capturar_frase(ler_bloco, espera_max: float = 8, fala_max: float = 15, silencio_fim: float = 1.0):
    """Lê blocos do microfone e devolve só o trecho com fala (int16), ou None se ninguém falou.

    ler_bloco() devolve um bloco de BLOCO segundos. Os primeiros 0,5 s medem o ruído do ambiente.
    """
    calibracao = [ler_bloco() for _ in range(int(0.5 / BLOCO))]
    ruido = float(np.mean([_volume(b) for b in calibracao])) if calibracao else 0.0
    limiar = max(300.0, ruido * 2.5)

    anteriores = calibracao[-3:]  # guarda um pouquinho antes da fala, para não cortar o começo
    for _ in range(int(espera_max / BLOCO)):
        bloco = ler_bloco()
        if _volume(bloco) > limiar:
            break
        anteriores = (anteriores + [bloco])[-3:]
    else:
        return None

    fala = anteriores + [bloco]
    silencio = 0.0
    while len(fala) * BLOCO < fala_max and silencio < silencio_fim:
        bloco = ler_bloco()
        fala.append(bloco)
        silencio = silencio + BLOCO if _volume(bloco) <= limiar else 0.0
    return np.concatenate(fala).astype(np.int16)


def _volume(bloco) -> float:
    return float(np.sqrt(np.mean(bloco.astype(np.float32) ** 2))) if len(bloco) else 0.0


def ouvir_microfone(idioma: str = "pt-BR") -> str:
    """Escuta uma frase pelo microfone e devolve o texto ("" se não entendeu)."""
    tamanho = int(TAXA_MICROFONE * BLOCO)
    with sounddevice.InputStream(samplerate=TAXA_MICROFONE, channels=1, dtype="int16") as entrada:
        audio = capturar_frase(lambda: entrada.read(tamanho)[0][:, 0])
    if audio is None:
        return ""
    dados = sr.AudioData(audio.tobytes(), TAXA_MICROFONE, 2)
    try:
        return sr.Recognizer().recognize_google(dados, language=idioma).strip()
    except (sr.UnknownValueError, sr.RequestError):
        return ""
