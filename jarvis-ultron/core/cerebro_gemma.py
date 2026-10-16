"""Cérebro Gemma 4 do Jarvis Ultron, rodando no PC do Erton (pelo Ollama).

Liga com JARVIS_CEREBRO="gemma" no .env (o "Instalar Gemma 4" já faz isso). Nesse modo o Jarvis
não usa o Gemini: ouve você, transcreve, pensa no Gemma 4 e fala a resposta. O raciocínio fica no
computador, então pode usar com dados de clientes.

- Transcrição (fala -> texto): Whisper local (faster-whisper), também no PC. Se ele não estiver
  instalado, usa o Whisper do Groq (precisa de GROQ_API_KEY e manda o áudio para a internet).
- Voz: a mesma da reserva (Microsoft Edge, pela internet). Para não mandar nem o texto das
  respostas para fora, ponha JARVIS_VOZ_PRIVADA=1 no .env (usa a voz que vem no Windows).
- Ferramentas: as mesmas do modo reserva (abrir sites, lembretes, automações...).

Ajustes no .env (todos opcionais):
  JARVIS_GEMMA_MODELO   nome do modelo no Ollama (padrão: jarvis-gemma, criado pelo instalador)
  JARVIS_GEMMA_URL      endereço do Ollama (padrão: http://localhost:11434/v1)
  JARVIS_WHISPER_MODELO tamanho do Whisper local: base, small (padrão) ou medium
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import threading
import time
import urllib.request
import wave

from core.reserva_groq import ReservaGroq

URL_PADRAO = "http://localhost:11434/v1"
MODELO_PADRAO = "jarvis-gemma"
WHISPER_PADRAO = "small"

INSTRUCOES_GEMMA = (
    "Você é o Jarvis Ultron, assistente pessoal do Erton. Responda sempre em português do Brasil, "
    "de forma calma, confiante e precisa, em no máximo 3 frases, porque a resposta será falada. "
    "Não use markdown, listas ou emojis. Quando o pedido precisar de uma ação (abrir um site ou app, "
    "ver o clima, lembretes, Metricool, analisar um site, autodiagnóstico, etc.), CHAME a ferramenta "
    "certa em vez de dizer que não consegue. Nunca publique, envie mensagens, compre ou apague nada "
    "sem o 'ok' do Erton na hora. Depois que a ferramenta responder, resuma o resultado em uma ou "
    "duas frases. Se não souber algo, diga que não sabe; não invente."
)


def cerebro_gemma() -> bool:
    """True quando o .env pede o Gemma como cérebro principal."""
    return os.environ.get("JARVIS_CEREBRO", "").strip().lower() in ("gemma", "gemma4", "gemma 4", "local")


import re
import unicodedata

_PRIVADO = re.compile(r"\bmodo (privado|sigiloso|confidencial|seguro)\b")
_NORMAL = re.compile(r"\b(modo normal|modo publico|sair do modo (privado|sigiloso|confidencial|seguro))\b")


def pedido_de_privacidade(fala: str) -> str | None:
    """"modo privado" -> "gemma"; "modo normal" / "sair do modo privado" -> "gemini"; senão None.
    Só frases curtas (um pedido, não uma conversa que cita as palavras)."""
    texto = unicodedata.normalize("NFKD", str(fala or "").lower())
    texto = " ".join("".join(c for c in texto if not unicodedata.combining(c)).replace(",", " ").split())
    if not texto or len(texto.split()) > 7:
        return None
    if _NORMAL.search(texto):
        return "gemini"
    if _PRIVADO.search(texto):
        return "gemma"
    return None


def modelo_instalado(nome: str | None = None) -> bool:
    """O Gemma do Jarvis está baixado no Ollama? (liga o Ollama se precisar)."""
    import json

    nome = nome or os.environ.get("JARVIS_GEMMA_MODELO", "").strip() or MODELO_PADRAO
    if not garantir_ollama(espera_total=10):
        return False
    raiz = _url_base().rstrip("/").removesuffix("/v1")
    try:
        with urllib.request.urlopen(raiz + "/api/tags", timeout=3) as resposta:
            modelos = json.loads(resposta.read().decode("utf-8")).get("models", [])
    except Exception:
        return False
    return any(str(m.get("name", "")).split(":")[0] == nome.split(":")[0] for m in modelos)


def _url_base() -> str:
    return os.environ.get("JARVIS_GEMMA_URL", "").strip() or URL_PADRAO


def ollama_respondendo(url: str | None = None, espera: float = 2.0) -> bool:
    raiz = (url or _url_base()).rstrip("/").removesuffix("/v1")
    try:
        with urllib.request.urlopen(raiz + "/api/tags", timeout=espera) as resposta:
            return resposta.status == 200
    except Exception:
        return False


def garantir_ollama(espera_total: float = 20.0) -> bool:
    """Se o Ollama não estiver rodando, tenta ligá-lo (escondido) e espera ficar pronto."""
    if ollama_respondendo():
        return True
    try:
        extra = {}
        if sys.platform == "win32":
            extra["creationflags"] = subprocess.CREATE_NO_WINDOW
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **extra)
    except Exception as erro:
        print(f"[Gemma] Não consegui ligar o Ollama: {erro}")
        return False
    limite = time.time() + espera_total
    while time.time() < limite:
        if ollama_respondendo():
            return True
        time.sleep(0.5)
    return False


class CerebroGemma(ReservaGroq):
    """Mesmo jeito de conversar e chamar ferramentas da reserva, mas com o Gemma 4 local."""

    NOME = "Gemma 4"

    def __init__(self, cliente=None, ouvido=None, modelo: str | None = None):
        if cliente is None:
            import openai

            # o Ollama fala o mesmo "idioma" da API da OpenAI; a chave não é usada, mas é exigida
            cliente = openai.OpenAI(base_url=_url_base(), api_key="ollama", max_retries=0, timeout=300)
        self.cliente = cliente
        self.modelo = modelo or os.environ.get("JARVIS_GEMMA_MODELO", "").strip() or MODELO_PADRAO
        self.mensagens = [{"role": "system", "content": INSTRUCOES_GEMMA}]
        self._trava_resposta = threading.Lock()
        self._ouvido = ouvido          # quem transcreve (Whisper local ou Groq); escolhido no 1º uso
        self._ouvido_escolhido = ouvido is not None
        self._trava_ouvido = threading.Lock()

    @classmethod
    def da_configuracao(cls) -> "CerebroGemma | None":
        try:
            return cls()
        except Exception as erro:
            print(f"[Gemma] Não consegui preparar o Gemma: {erro}")
            return None

    def _escolher_modelo(self) -> str:
        return self.modelo

    # ---------- aquecer: carrega o modelo na memória antes do primeiro pedido ----------
    def aquecer(self, ferramentas=None) -> bool:
        """Primeiro pedido ao Gemma é lento (carrega o modelo e lê as ferramentas). Fazendo um
        pedido mínimo na abertura, a primeira pergunta de verdade já sai rápida."""
        if not garantir_ollama():
            return False
        extra = {"tools": ferramentas, "tool_choice": "auto"} if ferramentas else {}
        try:
            self.cliente.chat.completions.create(
                model=self.modelo, max_tokens=1,
                messages=[self.mensagens[0], {"role": "user", "content": "oi"}], **extra)
            return True
        except Exception as erro:
            print(f"[Gemma] Aquecimento falhou: {erro}")
            return False

    # ---------- ouvir ----------
    def _preparar_ouvido(self):
        with self._trava_ouvido:
            if self._ouvido_escolhido:
                return self._ouvido
            self._ouvido_escolhido = True
            try:
                from faster_whisper import WhisperModel

                tamanho = os.environ.get("JARVIS_WHISPER_MODELO", "").strip() or WHISPER_PADRAO
                self._ouvido = ("local", WhisperModel(tamanho, device="cpu", compute_type="int8"))
                print(f"[Gemma] Transcrição local (Whisper {tamanho}) pronta.")
            except ImportError:
                chave = os.environ.get("GROQ_API_KEY", "").strip()
                if chave:
                    import groq

                    self._ouvido = ("groq", ReservaGroq(chave, cliente=groq.Groq(api_key=chave, timeout=60)))
                    print("[Gemma] Whisper local não instalado; transcrevendo pelo Groq.")
                else:
                    print("[Gemma] Sem Whisper local e sem chave do Groq: não consigo transcrever a voz.")
            except Exception as erro:
                print(f"[Gemma] Whisper local falhou ao carregar: {erro}")
            return self._ouvido

    def transcrever(self, pcm: bytes, taxa: int = 16000) -> str:
        ouvido = self._preparar_ouvido()
        if ouvido is None:
            return ""
        tipo, motor = ouvido
        if tipo == "groq":
            return motor.transcrever(pcm, taxa)
        try:
            if taxa == 16000:
                import numpy as np

                audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
            else:
                audio = io.BytesIO()
                with wave.open(audio, "wb") as arquivo:
                    arquivo.setnchannels(1)
                    arquivo.setsampwidth(2)
                    arquivo.setframerate(taxa)
                    arquivo.writeframes(pcm)
                audio.seek(0)
            trechos, _info = motor.transcribe(audio, language="pt", beam_size=1)
            return " ".join(t.text.strip() for t in trechos).strip()
        except Exception as erro:
            print(f"[Gemma] Transcrição local falhou: {erro}")
            return ""

    # ---------- erros em português ----------
    def _explicar(self, erro: Exception) -> str:
        nome = type(erro).__name__
        texto = str(erro).lower()
        if nome in ("APIConnectionError", "ConnectError", "ConnectionError", "APITimeoutError") \
                or "connection" in texto or "refused" in texto:
            if not ollama_respondendo():
                threading.Thread(target=garantir_ollama, daemon=True).start()
                return ("O Gemma não está respondendo porque o Ollama está desligado. Já mandei ligar; "
                        "tente de novo em alguns segundos.")
            return "O Gemma demorou demais para responder. Tente de novo."
        if nome == "NotFoundError" or "not found" in texto:
            return (f"Não encontrei o modelo {self.modelo} no Ollama. Rode o 'Instalar Gemma 4' de novo "
                    "na pasta do Jarvis.")
        return f"O Gemma teve um problema: {str(erro)[:120]}"
