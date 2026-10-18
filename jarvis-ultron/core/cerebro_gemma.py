"""Cérebro Gemma 4 do Jarvis Ultron, rodando no PC do Erton (pelo Ollama).

Liga com JARVIS_CEREBRO="gemma" no .env (o "Instalar Gemma 4" já faz isso). Nesse modo o Jarvis
não usa o Gemini: ouve você, transcreve, pensa no Gemma 4 e fala a resposta. O raciocínio fica no
computador, então pode usar com dados de clientes.

- Transcrição (fala -> texto): Whisper local (faster-whisper), também no PC. A voz NUNCA vai para a
  nuvem neste modo: sem o Whisper local, o Jarvis avisa (tela e voz) e você digita.
- Voz: a mesma da reserva (Microsoft Edge, pela internet). Para não mandar nem o texto das
  respostas para fora, ponha JARVIS_VOZ_PRIVADA=1 no .env (usa a voz que vem no Windows).
- Ferramentas: só as que rodam sem IA na nuvem (abrir sites, lembretes, automações locais...).
  Pesquisa pelo Gemini, Hermes, Claude, imagens e vídeos ficam desligados (main.FERRAMENTAS_NUVEM_IA).

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
# "não quero sair do modo privado", "nada de modo normal": negação nunca tira do modo privado
_NEGACAO = re.compile(r"\b(nao|nunca|nem|jamais|sem)\b|\bnada de\b")
# Sair do modo privado (ir para a nuvem) só com o pedido inteiro, sem mais nada na frase:
# "Jarvis, modo normal", "sair do modo privado", "volta para o modo normal".
_NORMAL_EXATO = re.compile(
    r"^(?:(?:ok|ei|hey|oi) )?(?:jarvis )?(?:por favor )?(?:(?:pode )?(?:volta|voltar|volte) (?:para o|pro|ao) )?"
    r"(?:modo normal|modo publico|sair do modo (?:privado|sigiloso|confidencial|seguro))(?: por favor)?$")


def pedido_de_privacidade(fala: str) -> str | None:
    """"modo privado" -> "gemma"; "modo normal" / "sair do modo privado" -> "gemini"; senão None.
    Só frases curtas (um pedido, não uma conversa que cita as palavras). Sair do modo privado (ir
    para a nuvem) nunca com negação e só com o pedido sozinho: na dúvida, fica no modo privado."""
    texto = unicodedata.normalize("NFKD", str(fala or "").lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = " ".join(re.sub(r"[,.;:!?]", " ", texto).split())
    if not texto or len(texto.split()) > 7:
        return None
    if _NORMAL.search(texto):
        return "gemini" if _NORMAL_EXATO.match(texto) and not _NEGACAO.search(texto) else None
    if _PRIVADO.search(texto):
        return "gemma"
    return None


AVISO_SEM_WHISPER = ("No modo privado não consigo ouvir sua voz: a transcrição local (Whisper) não está "
                     "instalada, e a voz não vai para a internet. Dê dois cliques em 'Instalar voz local' "
                     "na pasta do Jarvis. "
                     "Enquanto isso, digite.")
AVISO_WHISPER_FALHOU = ("Não consegui carregar a transcrição local da voz (Whisper). Na primeira vez ela precisa "
                        "da internet para baixar o modelo; tento de novo em 1 minuto. Enquanto isso, digite.")


def whisper_instalado() -> bool:
    """O Whisper local (faster-whisper) está instalado neste Python? (não carrega o modelo)"""
    import importlib.util

    try:
        return importlib.util.find_spec("faster_whisper") is not None
    except (ImportError, ValueError):
        return False


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
        self._ouvido = ouvido          # quem transcreve (Whisper local, no PC); escolhido no 1º uso
        self._ouvido_escolhido = ouvido is not None
        self._trava_ouvido = threading.Lock()
        self._tentar_ouvido_apos = 0.0  # depois de uma falha ao carregar, espera antes de tentar de novo
        self.erro_ouvido: str | None = None  # por que não dá para ouvir (o Jarvis avisa na tela e na voz)

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
    ESPERA_NOVA_TENTATIVA = 60  # segundos entre tentativas de carregar o Whisper que falhou

    def checar_ouvido(self) -> bool:
        """Na abertura: o Whisper local está instalado? Se não, guarda o aviso em erro_ouvido."""
        if self._ouvido is not None or whisper_instalado():
            return True
        self.erro_ouvido = AVISO_SEM_WHISPER
        return False

    def _preparar_ouvido(self):
        """Só o Whisper local. No modo privado a voz NUNCA vai para a nuvem (nada de Groq): sem ele,
        transcrever devolve "" e erro_ouvido diz o motivo (o Jarvis avisa uma vez)."""
        with self._trava_ouvido:
            if self._ouvido_escolhido or time.monotonic() < self._tentar_ouvido_apos:
                return self._ouvido
            self._ouvido_escolhido = True
            try:
                from faster_whisper import WhisperModel
            except Exception as erro:  # não instalado, ou "DLL load failed" no Windows (ImportError/OSError)
                self.erro_ouvido = AVISO_SEM_WHISPER
                print(f"[Gemma] Whisper local não instalado ({erro}): não transcrevo a voz no modo privado.")
                return None
            tamanho = os.environ.get("JARVIS_WHISPER_MODELO", "").strip() or WHISPER_PADRAO
            try:
                self._ouvido = ("local", WhisperModel(tamanho, device="cpu", compute_type="int8"))
                self.erro_ouvido = None
                print(f"[Gemma] Transcrição local (Whisper {tamanho}) pronta.")
            except Exception as erro:
                # ex.: sem internet no 1º download do modelo: tenta de novo daqui a pouco, nunca pela nuvem
                self._ouvido_escolhido = False
                self._tentar_ouvido_apos = time.monotonic() + self.ESPERA_NOVA_TENTATIVA
                self.erro_ouvido = AVISO_WHISPER_FALHOU
                print(f"[Gemma] Whisper local falhou ao carregar: {erro}")
            return self._ouvido

    def transcrever(self, pcm: bytes, taxa: int = 16000) -> str:
        ouvido = self._preparar_ouvido()
        if ouvido is None:
            return ""
        _tipo, motor = ouvido
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
