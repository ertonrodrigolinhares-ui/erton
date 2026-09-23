"""Fala (alto-falante) e escuta (microfone) do Jarvis.

As bibliotecas de voz são opcionais: sem elas, o Jarvis funciona só com texto.
O reconhecimento de fala usa o serviço gratuito do Google (não precisa de chave).
"""

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


def fala_disponivel() -> bool:
    return pyttsx3 is not None


def microfone_disponivel() -> bool:
    if sr is None:
        return False
    try:
        return len(sr.Microphone.list_microphone_names()) > 0
    except Exception:  # PyAudio ausente ou sem dispositivo de áudio
        return False


class Falador:
    """Fala em segundo plano, um texto de cada vez, sem travar a janela."""

    def __init__(self):
        self.fila: queue.Queue = queue.Queue()
        if fala_disponivel():
            threading.Thread(target=self._trabalhar, daemon=True).start()

    def _trabalhar(self) -> None:
        # O motor precisa ser criado na mesma thread em que fala.
        try:
            motor = pyttsx3.init()
        except Exception:
            motor = None
        else:
            for voz in motor.getProperty("voices"):
                identificacao = f"{voz.id} {voz.name}".lower()
                if "pt" in identificacao or "portug" in identificacao or "brazil" in identificacao:
                    motor.setProperty("voice", voz.id)
                    break
            motor.setProperty("rate", 185)
        while True:
            texto = self.fila.get()
            try:
                if motor is not None:
                    motor.say(texto)
                    motor.runAndWait()
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
