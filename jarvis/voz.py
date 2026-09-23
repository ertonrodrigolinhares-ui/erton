"""Entrada e saída do Jarvis: fala (microfone/alto-falante) ou texto (terminal).

As bibliotecas de voz são opcionais. Se não estiverem instaladas, ou se não houver
microfone, o Jarvis funciona normalmente em modo texto.
"""

try:
    import pyttsx3
except ImportError:  # pragma: no cover - depende do ambiente
    pyttsx3 = None

try:
    import speech_recognition as sr
except ImportError:  # pragma: no cover - depende do ambiente
    sr = None


class Interface:
    def __init__(self, usar_voz: bool, idioma: str = "pt-BR"):
        self.idioma = idioma
        self.motor_fala = None
        self.reconhecedor = None
        self.usar_voz = usar_voz and pyttsx3 is not None and sr is not None

        if usar_voz and not self.usar_voz:
            print("[Jarvis] Bibliotecas de voz não encontradas; usando modo texto.")
            print("         Instale com: pip install pyttsx3 SpeechRecognition pyaudio")

        if self.usar_voz:
            try:
                self.motor_fala = pyttsx3.init()
                self._escolher_voz_portugues()
                self.reconhecedor = sr.Recognizer()
            except Exception as erro:  # sem driver de áudio, por exemplo
                print(f"[Jarvis] Não foi possível iniciar o áudio ({erro}); usando modo texto.")
                self.usar_voz = False

    def _escolher_voz_portugues(self) -> None:
        for voz in self.motor_fala.getProperty("voices"):
            identificacao = f"{voz.id} {voz.name}".lower()
            if "pt" in identificacao or "portug" in identificacao or "brazil" in identificacao:
                self.motor_fala.setProperty("voice", voz.id)
                break
        self.motor_fala.setProperty("rate", 185)

    def falar(self, texto: str) -> None:
        print(f"Jarvis: {texto}")
        if self.usar_voz:
            self.motor_fala.say(texto)
            self.motor_fala.runAndWait()

    def ouvir(self) -> str:
        """Retorna o que o usuário disse/digitou, em minúsculas. String vazia se nada foi entendido."""
        if not self.usar_voz:
            try:
                return input("Você: ").strip()
            except EOFError:
                return "sair"

        with sr.Microphone() as fonte:
            print("Ouvindo...")
            self.reconhecedor.adjust_for_ambient_noise(fonte, duration=0.5)
            try:
                audio = self.reconhecedor.listen(fonte, timeout=8, phrase_time_limit=12)
            except sr.WaitTimeoutError:
                return ""
        try:
            texto = self.reconhecedor.recognize_google(audio, language=self.idioma)
        except (sr.UnknownValueError, sr.RequestError):
            return ""
        print(f"Você: {texto}")
        return texto.strip()
