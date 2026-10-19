import asyncio
import contextlib
import os
import re
import threading
import json
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace

import sounddevice as sd
from google import genai
from google.genai import types
from api import status as jarvis_status
from core.jarvis_client import JarvisClient
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
)
import hashlib
import importlib
import time

from core.live_model import pick_live_model


def _lazy_action(module_name: str, attribute: str):
    """Keep desktop-only dependencies out of headless API process startup."""

    def invoke(*args, **kwargs):
        action = getattr(importlib.import_module(module_name), attribute)
        return action(*args, **kwargs)

    invoke.__name__ = attribute
    return invoke


# Preserve the historical module-level action surface for patches/plugins while
# deferring platform-specific imports until a declared action actually runs.
file_processor = _lazy_action("actions.file_processor", "file_processor")
flight_finder = _lazy_action("actions.flight_finder", "flight_finder")
open_app = _lazy_action("actions.open_app", "open_app")
weather_action = _lazy_action("actions.weather_report", "weather_action")
email_control = _lazy_action("actions.email_control", "email_control")
reminder = _lazy_action("actions.reminder", "reminder")
computer_settings = _lazy_action("actions.computer_settings", "computer_settings")
screen_process = _lazy_action("actions.screen_processor", "screen_process")
youtube_video = _lazy_action("actions.youtube_video", "youtube_video")
media_control = _lazy_action("actions.media_control", "media_control")
desktop_control = _lazy_action("actions.desktop", "desktop_control")
browser_control = _lazy_action("actions.browser_control", "browser_control")
file_controller = _lazy_action("actions.file_controller", "file_controller")
web_search_action = _lazy_action("actions.web_search", "web_search")
request_presentation = _lazy_action("actions.presentation_maker", "request_presentation")
request_deep_research = _lazy_action("actions.deep_research", "request_deep_research")


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _load_dotenv():
    """Load .env file if it exists. Silently skip if not found."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        # python-dotenv not installed — rely on already-set env vars
        return
    # Jarvis Ultron: o iniciador do Windows grava o .env na página de código do console (ex.: a cidade
    # "João Pessoa"); o Bloco de Notas grava em UTF-8. Aceita os dois em vez de travar na abertura
    # (a mesma leitura do testador de chave e de quem grava no .env: core/env_arquivo.py).
    import io

    from core.env_arquivo import ler_texto_env

    try:
        texto = ler_texto_env(BASE_DIR / ".env")
    except OSError:
        return
    load_dotenv(stream=io.StringIO(texto))


BASE_DIR        = get_base_dir()
_load_dotenv()
# Jarvis Ultron: caminho do Gemini (normal ou Vertex AI, para as chaves "AQ."); vale para tudo
from core.gemini_acesso import aplicar_via as _aplicar_via_gemini
_aplicar_via_gemini()

# Jarvis Ultron: escolhe sozinho os modelos do Gemini disponíveis para a chave
from core.modelos import instalar as _instalar_central_de_modelos
_instalar_central_de_modelos()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
SUPPORTED_VOICE_NAMES = {
    "puck", "charon", "kore", "fenrir", "aoede",
    "leda", "orus", "schedar", "zubenelgenubi"
}
DEFAULT_VOICE_NAME   = "puck"

RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024
LIVE_VAD_SILENCE_MS = 200
# Jarvis Ultron: fala sempre em português do Brasil (as instruções e as ferramentas estão em
# inglês, e o "Hey Jarvis" também puxa o modelo para o inglês).
REGRA_IDIOMA = (
    "[IDIOMA — REGRA MAIS IMPORTANTE]\n"
    "Fale SEMPRE em português do Brasil, com sotaque brasileiro, em todas as respostas. "
    "Mesmo que o usuário diga \"Hey Jarvis\", use palavras em inglês, ou que as instruções e os "
    "resultados das ferramentas estejam em inglês, responda em português do Brasil. "
    "Só use outro idioma se o usuário pedir claramente (ex.: \"responda em inglês\").\n"
)

# Jarvis Ultron: a troca de modo já é avisada por um som e pelo selo na tela.
QUIET_MODE_RESULT = ("Done. The user already heard a chime and sees the mode on screen: do not announce "
                     "or explain the listening mode. Say nothing at all.")
# Jarvis Ultron: o selo 🔒 só existe na tela azul (a cena do orbe); na tela antiga (F2, JARVIS_VISUAL=classico,
# JARVIS_CENA=0) o sinal é a linha "🔒 Modo privado ligado" que a ponte escreve no registro ao trocar.
ESPERE_O_MODO_PRIVADO = "espere o aviso \"🔒 Modo privado ligado\" (na tela azul, o selo 🔒 MODO PRIVADO)"
STARTUP_CLAPS_REQUIRED = 2
STARTUP_CLAP_MAX_GAP_SECONDS = 4.0
STARTUP_CLAP_COOLDOWN_SECONDS = 0.22
SELF_QUIT_GOODBYE = (
    "Certamente, senhor. Foi um privilégio. O Jarvis está saindo do ar agora. "
    "Até a próxima."
)

_SELF_QUIT_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"\b(?:quit|close|exit)\s+(?:jarvis|yourself)\b",
    r"\b(?:shut|turn)\s+(?:jarvis|yourself)\s+(?:down|off)\b",
    r"\b(?:shut\s+down|turn\s+off|power\s+down)\s+(?:jarvis|yourself)\b",
    r"\bjarvis\b.{0,36}\b(?:quit|close|exit|shut\s+down|turn\s+off|go\s+offline)\b",
    r"\b(?:go|take\s+yourself)\s+offline(?:\s+jarvis)?\b",
    # Jarvis Ultron: em português ("desliga o Jarvis", "Jarvis, saia do ar")
    r"\b(?:desligue|desliga|desligar|feche|fecha|fechar|encerre|encerra|encerrar)\s+(?:o\s+)?jarvis\b",
    r"\bjarvis\b.{0,36}\b(?:desligue-se|se\s+desligue|saia\s+do\s+ar|sair\s+do\s+ar)\b",
))


def _exception_leaves(exc: BaseException):
    nested = getattr(exc, "exceptions", None)
    if nested:
        for child in nested:
            yield from _exception_leaves(child)
    else:
        yield exc


def _is_normal_live_close_error(exc: BaseException) -> bool:
    for leaf in _exception_leaves(exc):
        name = leaf.__class__.__name__.lower()
        message = str(leaf).lower()
        if name == "connectionclosedok" or "1000 (ok)" in message:
            return True
        if isinstance(leaf, genai.errors.APIError) and "1000" in message:
            return True
    return False


def _is_transient_live_connection_error(exc: BaseException) -> bool:
    transient_markers = (
        "connection reset", "connection aborted", "temporarily unavailable",
        "timed out", "timeout", "network is unreachable", "broken pipe",
    )
    return any(
        isinstance(leaf, (ConnectionResetError, ConnectionAbortedError, TimeoutError))
        or any(marker in str(leaf).lower() for marker in transient_markers)
        for leaf in _exception_leaves(exc)
    )


def _live_reconnect_delay(attempt: int) -> float:
    return min(30.0, float(2 ** max(0, int(attempt) - 1)))


def _live_response_audio_bytes(response) -> bytes | None:
    server_content = getattr(response, "server_content", None)
    model_turn = getattr(server_content, "model_turn", None)
    for part in getattr(model_turn, "parts", None) or []:
        inline_data = getattr(part, "inline_data", None)
        data = getattr(inline_data, "data", None)
        mime_type = str(getattr(inline_data, "mime_type", "") or "").lower()
        if data and mime_type.startswith("audio/"):
            return bytes(data)
    return None


def wait_for_startup_claps(
    required: int = STARTUP_CLAPS_REQUIRED,
    *,
    timeout: float | None = None,
    stream_factory=None,
) -> bool:
    """Hold startup until two distinct claps are heard by the default microphone."""
    if os.environ.get("JARVIS_SKIP_CLAP_GATE", "").strip().lower() in {"1", "true", "yes", "on"}:
        print("[JARVIS] 👏 Startup clap gate bypassed (JARVIS_SKIP_CLAP_GATE).")
        return True
    # Some macOS/AUHAL configurations expose a nominal input device but reject
    # every PortAudio operation (PaErrorCode -9986). Avoid repeatedly starting
    # a failing Core Audio stream; users with a working mic can opt in.
    if sys.platform == "darwin" and stream_factory is None and os.environ.get("JARVIS_ENABLE_CLAP_GATE", "").strip().lower() not in {"1", "true", "yes", "on"}:
        print("[JARVIS] ⚠️ macOS microphone gate disabled for this audio configuration.")
        print("[JARVIS] Continuing without clap startup. Set JARVIS_ENABLE_CLAP_GATE=1 to force it.")
        return True

    required = max(1, int(required))
    stream_factory = stream_factory or sd.InputStream
    try:
        import numpy as np
    except ImportError:
        print("[JARVIS] ❌ Startup clap gate needs numpy. Set JARVIS_SKIP_CLAP_GATE=1 to bypass.")
        return False

    clap_times: list[float] = []
    last_clap_at = 0.0
    # Microphone input levels vary considerably between Mac models.  The old
    # fixed 0.12 RMS / 0.32 peak gates rejected quiet real claps, while laptop
    # fan noise could sometimes trip them.  Track the room floor and use both
    # transient shape (crest factor) and energy to identify a clap.
    noise_floor = 0.008
    finished = threading.Event()
    started_at = time.monotonic()

    def callback(indata, frames, time_info, status):
        nonlocal last_clap_at, noise_floor, clap_times
        if status:
            print(f"[JARVIS] ⚠️ Clap mic: {status}")
        samples = np.asarray(indata, dtype=np.float32).reshape(-1)
        if samples.size == 0:
            return
        magnitude = np.abs(samples)
        rms = float(np.sqrt(np.mean(samples * samples)))
        peak = float(np.max(magnitude))
        # Only let low-energy frames teach the noise floor; otherwise a clap
        # would raise the threshold immediately and make the second clap hard
        # to detect.
        if rms < max(0.08, noise_floor * 6.0):
            noise_floor = (noise_floor * 0.96) + (rms * 0.04)
        threshold = max(0.100, noise_floor * 6.5)
        peak_threshold = max(0.35, noise_floor * 15.0)
        crest_factor = peak / max(rms, 1e-6)
        now = time.monotonic()
        # A valid clap must be either a sharp transient with meaningful energy
        # or a genuinely loud impact. This rejects speech, fan noise, and most
        # desk/keyboard taps that only have a brief peak.
        is_transient = crest_factor >= 2.20 and rms >= threshold
        is_loud = rms >= max(0.28, noise_floor * 15.0)
        if (
            peak < peak_threshold
            or not (is_transient or is_loud)
            or now - last_clap_at < STARTUP_CLAP_COOLDOWN_SECONDS
        ):
            return
        if clap_times and now - clap_times[-1] > STARTUP_CLAP_MAX_GAP_SECONDS:
            clap_times = []
        clap_times.append(now)
        last_clap_at = now
        print(f"[JARVIS] 👏 Clap {len(clap_times)}/{required} detected")
        if len(clap_times) >= required:
            finished.set()

    print(f"[JARVIS] 👏 Waiting for {required} claps to power up...")
    # PortAudio on macOS commonly rejects 16 kHz even when the microphone is
    # available (PaErrorCode -9986). Prefer the device's native rate, then
    # retry standard rates before reporting that the microphone is unavailable.
    sample_rates = [SEND_SAMPLE_RATE, 44100, 48000]
    input_device = None
    try:
        if stream_factory is sd.InputStream:
            try:
                default_device = sd.default.device
                try:
                    input_index = int(default_device[0])
                except (TypeError, IndexError, ValueError):
                    input_index = -1
                if input_index < 0:
                    print("[JARVIS] ⚠️ macOS reports no default microphone device.")
                    if os.environ.get("JARVIS_REQUIRE_CLAP_GATE", "").strip().lower() not in {"1", "true", "yes", "on"}:
                        print("[JARVIS] ⚠️ Continuing without the clap gate; microphone input is unavailable.")
                        return True
                    raise RuntimeError("no default microphone device")
                input_device = input_index
                device = sd.query_devices(input_device if input_device is not None else None, "input")
                if int(device.get("max_input_channels", 0)) < 1:
                    raise RuntimeError("no input channels are available")
                native_rate = int(float(device.get("default_samplerate", 0)))
                if native_rate > 0:
                    sample_rates.insert(0, native_rate)
            except Exception:
                pass
        sample_rates = list(dict.fromkeys(sample_rates))
        last_error = None
        for sample_rate in sample_rates:
            try:
                if stream_factory is sd.InputStream:
                    # Validate the format before constructing a live AUHAL
                    # stream; macOS can report a device but reject it with
                    # PaErrorCode -9986 during stream startup.
                    sd.check_input_settings(
                        device=input_device,
                        samplerate=sample_rate,
                        channels=CHANNELS,
                        dtype="float32",
                    )
                with stream_factory(
                    samplerate=sample_rate,
                    device=input_device,
                    channels=CHANNELS,
                    dtype="float32",
                    blocksize=0,
                    latency="high",
                    callback=callback,
                ):
                    while not finished.wait(0.05):
                        if timeout is not None and time.monotonic() - started_at >= timeout:
                            print("[JARVIS] ⏱️ Startup clap gate timed out.")
                            return False
                break
            except Exception as exc:
                last_error = exc
                if finished.is_set():
                    break
        else:
            raise last_error or RuntimeError("no compatible microphone sample rate")
    except KeyboardInterrupt:
        print("\n[JARVIS] Startup cancelled.")
        return False
    except Exception as exc:
        print(f"[JARVIS] ❌ Startup clap microphone unavailable: {exc}")
        if os.environ.get("JARVIS_REQUIRE_CLAP_GATE", "").strip().lower() not in {"1", "true", "yes", "on"}:
            print("[JARVIS] ⚠️ Continuing without the clap gate; microphone input is unavailable.")
            print("[JARVIS] Restore microphone access to use voice input.")
            return True
        print("[JARVIS] Clap gate required. Set JARVIS_SKIP_CLAP_GATE=1 to bypass it.")
        return False

    print("[JARVIS] ⚡ Two claps detected. Powering up...")
    return True

def _latencia_audio() -> str:
    """Jarvis Ultron: 'low' (padrão) deixa a voz sair e entrar mais rápido. Se o som ficar
    picotado neste computador, coloque JARVIS_LATENCIA_AUDIO=high no .env."""
    valor = os.environ.get("JARVIS_LATENCIA_AUDIO", "low").strip().lower()
    return valor if valor in {"low", "high"} else "low"


def _get_api_key() -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set. Please set it to your Gemini API key.")
    return api_key


def _normalize_voice_name(voice_name: str | None) -> str:
    if not voice_name:
        return DEFAULT_VOICE_NAME
    candidate = voice_name.strip().lower()
    return candidate if candidate in SUPPORTED_VOICE_NAMES else DEFAULT_VOICE_NAME


def _is_unsupported_voice_error(exc: Exception) -> bool:
    if not isinstance(exc, genai.errors.APIError):
        return False
    code = getattr(exc, "code", None)
    msg = str(exc).lower()
    if code == 1007:
        return "requested voice api_name" in msg and "not available for model" in msg
    return "requested voice api_name" in msg and "not available for model" in msg


def _load_voice_name() -> str:
    voice = os.environ.get("GEMINI_VOICE_NAME")
    if voice:
        return _normalize_voice_name(voice)
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            return _normalize_voice_name(json.load(f).get("voice_name"))
    except Exception:
        return DEFAULT_VOICE_NAME


def _load_system_prompt() -> str:
    try:
        prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()
        return (
            prompt
            + "\n\nAlways address the user respectfully as 'Sir' or 'Madam' where appropriate, while remaining efficient and direct."
        )
    except Exception:
        return (
            "You are JARVIS, Tony Stark's AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool. "
            "Always address the user respectfully as 'Sir' or 'Madam' where appropriate, while remaining efficient and direct."
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()

TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": (
            "Opens any application on the computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for any information.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search (default) or compare"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "listening_mode",
        "description": (
            "Switches how JARVIS listens. 'maos_livres' (hands-free): answers everything the user says, "
            "no wake word needed. 'chamada' (call mode): answers only after the user says 'Hey Jarvis'. "
            "Use when the user says 'modo mãos livres' or 'modo chamada'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "mode": {"type": "STRING", "enum": ["maos_livres", "chamada"], "description": "The listening mode"}
            },
            "required": ["mode"]
        }
    },
    {
        "name": "school_tasks",
        "description": (
            "Lists the student's pending school activities and deadlines from Geekie One (read-only, via "
            "Hermes). Use when the user asks what is pending/due on Geekie or at school. Never answer, submit "
            "or mark school activities as done."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "refresh": {"type": "BOOLEAN", "description": "true to read Geekie One again now instead of the saved list"}
            }
        }
    },
    {
        "name": "self_diagnosis",
        "description": (
            "Runs JARVIS's self-diagnosis: checks internet, the Gemini key and models, the Groq backup, "
            "Hermes (agents), microphone, speakers, computer memory/disk, the automation browser and the "
            "wake word. Use when the user asks what is wrong, to check/diagnose the system, or why something "
            "is not working. Afterwards, tell the user in Portuguese only the problems found and how to fix them."
        ),
        "parameters": {"type": "OBJECT", "properties": {}}
    },
    {
        "name": "hermes_agent",
        "description": (
            "Sends a task to Hermes, JARVIS's autonomous orchestrator with sub-agents. Use for: social media "
            "posts of the user's athlete profile (daily post proposals, Metricool, best time to post, "
            "performance), Meta/Facebook/Instagram ads reports, opening and reading web panels/dashboards "
            "by itself. Examples: 'what are today's posts?', 'how are my ads doing?', 'publish the approved "
            "posts'. For research, analysis, reports and other long multi-step tasks prefer claude_task "
            "(when available). Never use it to publish without approval."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "request": {"type": "STRING", "description": "The full task for Hermes, in Portuguese"}
            },
            "required": ["request"]
        }
    },
    {
        "name": "approve_publication",
        "description": (
            "Tells Hermes to publish/schedule posts (kind='redes') or apply an ad change (kind='anuncios'), "
            "always with the user's explicit approval, in two calls: first call with confirm=false records the "
            "proposal; then tell the user in Portuguese exactly what will be published/changed and ask for an "
            "explicit ok. Only after the user clearly approves in their own words, call again with confirm=true "
            "(same kind and details). Never assume approval."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "kind": {"type": "STRING", "enum": ["redes", "anuncios"], "description": "redes = posts; anuncios = Meta ads"},
                "details": {"type": "STRING", "description": "Exactly what will be done, e.g. 'posts 1 e 3, agendar no horario sugerido'"},
                "confirm": {"type": "BOOLEAN", "description": "true ONLY after the user approved the proposal told to them"}
            },
            "required": ["kind", "details"]
        }
    },
    {
        "name": "suspend_listening",
        "description": (
            "Suspends JARVIS for a number of minutes: the microphone is muted and JARVIS stops listening, "
            "then it unmutes automatically and announces it is back. Use when the user asks JARVIS to be "
            "suspended, pause, stay quiet, sleep or stop listening for some time (default 10 minutes)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "minutes": {"type": "NUMBER", "description": "How many minutes to stay suspended (1 to 240)"}
            },
            "required": ["minutes"]
        }
    },
    {
        "name": "generate_image",
        "description": (
            "Creates an image from a text description using Gemini's image model (Nano Banana), "
            "saves it as PNG and opens it. Use when the user asks to create, draw or generate an image."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "prompt": {"type": "STRING", "description": "Detailed description of the image, in English"}
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "email_control",
        "description": (
            "Connects Gmail through Google OAuth, checks connection status, reads/searches Gmail, and prepares email. "
            "Gmail is the default provider; Apple Mail remains an optional macOS fallback. "
            "For Gmail, prepare opens a visible compose window and types To, Cc/Bcc, Subject, and Body in sequence. "
            "Every outgoing email is approval-gated: first call action=prepare, then call action=approve "
            "only after the user explicitly confirms the exact pending recipient, subject, and body."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "enum": ["connect", "status", "disconnect", "inbox", "unread", "search", "read", "prepare", "approve", "cancel"],
                    "description": "Email operation."
                },
                "provider": {
                    "type": "STRING",
                    "enum": ["gmail", "apple_mail", "default"],
                    "description": "Email provider. Default: gmail."
                },
                "browser": {
                    "type": "STRING",
                    "description": "Browser for the visible Gmail compose window. Default: chrome."
                },
                "credentials_path": {
                    "type": "STRING",
                    "description": "Path to a Google Desktop OAuth client JSON file, used only for connect."
                },
                "limit": {"type": "INTEGER", "description": "Maximum inbox/search results, 1-30."},
                "query": {"type": "STRING", "description": "Sender or subject text for search."},
                "message_id": {"type": "STRING", "description": "Message ID returned by inbox/search, required for read."},
                "to": {"type": "STRING", "description": "Recipient email address or comma-separated addresses."},
                "cc": {"type": "STRING", "description": "Optional Cc addresses."},
                "bcc": {"type": "STRING", "description": "Optional Bcc addresses."},
                "subject": {"type": "STRING", "description": "Exact email subject for prepare."},
                "body": {"type": "STRING", "description": "Exact email body for prepare."}
            },
            "required": ["action"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "media_control",
        "description": (
            "Controls music playback, primarily Spotify. Use when the user asks to play, resume, pause, "
            "stop, toggle, skip, or go back in Spotify, Apple Music, YouTube Music, or the active media player. "
            "Spotify is the default platform. Pass a song, artist, album, playlist, or Spotify link in query."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "enum": ["play", "pause", "stop", "toggle", "next", "previous", "play_query"],
                    "description": "Playback command. Use play_query to find a specific song or other item."
                },
                "platform": {
                    "type": "STRING",
                    "enum": ["spotify", "apple_music", "youtube_music", "system"],
                    "description": "Music platform. Default: spotify."
                },
                "query": {
                    "type": "STRING",
                    "description": "Song, artist, album, playlist, or Spotify link for play/play_query."
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc. "
            "You have NO visual ability without this tool. "
            "After calling this tool, stay SILENT — the vision module speaks directly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls any web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
            "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
            "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                "browser":     {"type": "STRING", "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser."},
                "url":         {"type": "STRING", "description": "URL for go_to / new_tab action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "engine":      {"type": "STRING", "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up | down for scroll"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
                "key":         {"type": "STRING", "description": "Key name for press action (e.g. Enter, Escape, F5)"},
                "path":        {"type": "STRING", "description": "Save path for screenshot"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages and opens local files and folders: open, list, create, delete, move, copy, rename, read, write, find, disk usage. Use action=open for a file path; do not use open_app for files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "open | list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "graphics_quality",
        "description": "Changes JARVIS rendering quality between low, medium, and high.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "quality": {
                    "type": "STRING",
                    "enum": ["low", "medium", "high"],
                    "description": "Rendering quality preset."
                }
            },
            "required": ["quality"]
        }
    },
    {
        "name": "jarvis_ui_control",
        "description": (
            "Changes JARVIS's own interface. Use when the user asks to open or close the Command Center, "
            "change the theme or graphics quality, open settings, enter compact mode, toggle fullscreen, or show shortcuts."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "enum": ["open_command_center", "close_command_center", "change_theme", "change_graphics_quality", "open_settings", "compact_mode", "fullscreen", "show_shortcuts"],
                    "description": "The interface action to perform."
                },
                "theme": {
                    "type": "STRING",
                    "enum": ["arc_reactor", "stealth_red", "vibranium_purple", "nanotech_gold", "platinum"],
                    "description": "Required for change_theme."
                },
                "graphics_quality": {
                    "type": "STRING",
                    "enum": ["low", "medium", "high"],
                    "description": "Required for change_graphics_quality. Low favors performance, medium is balanced, and high enables full visual detail."
                },
            },
            "required": ["action"]
        }
    },
    {
        "name": "deep_research",
        "description": (
            "Runs rigorous, multi-query web research and keeps the report in volatile memory unless the user asks to save it. "
            "Use when the user explicitly asks for deep, thorough, comprehensive, or source-backed research. "
            "On the first call, ask whether the user wants a background status bar or visible browser research. "
            "After completion, use this tool again to save the latest report or read it aloud."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "question": {
                    "type": "STRING",
                    "description": "The research question. Required on the initial ask call; optional when confirming a pending request."
                },
                "execution_mode": {
                    "type": "STRING",
                    "enum": ["ask", "background", "visible"],
                    "description": "Always use ask initially. Background shows a labeled status bar; visible opens a controlled browser and visits sources."
                },
                "result_action": {
                    "type": "STRING",
                    "enum": ["none", "save_files", "save_desktop", "read_report"],
                    "description": "Action for the latest completed in-memory report. Use only after the user chooses one of these options."
                },
                "depth": {
                    "type": "STRING",
                    "enum": ["quick", "standard", "deep"],
                    "description": "Research breadth. Default: standard."
                },
                "focus_areas": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Optional angles, constraints, or subtopics to prioritize."
                },
                "max_sources": {
                    "type": "INTEGER",
                    "description": "Maximum verified source links to retain, from 5 to 50."
                },
                "output_path": {
                    "type": "STRING",
                    "description": "Optional explicit path used only with save_files or save_desktop. Research never saves automatically."
                },
            },
            "required": []
        }
    },
    {
        "name": "create_presentation",
        "description": (
            "Creates, edits, redesigns, or extends an editable Microsoft PowerPoint (.pptx) presentation. "
            "Use this directly whenever the user asks to make a PowerPoint, presentation, "
            "slide deck, pitch deck, briefing deck, or slideshow. Do not use "
            "file_processor. First ask whether the user wants "
            "a native 3D model, then ask whether they want to see the task or keep it in the background."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "topic": {
                    "type": "STRING",
                    "description": "Subject, goal, and important content instructions. Required on the initial ask; optional when confirming the pending run mode."
                },
                "execution_mode": {
                    "type": "STRING",
                    "enum": ["ask", "background", "visible"],
                    "description": "Always use ask initially. Visible shows real build phases; background keeps a compact status indicator."
                },
                "mode": {
                    "type": "STRING",
                    "description": "auto | create | edit | redesign | extend. Default: auto."
                },
                "title": {
                    "type": "STRING",
                    "description": "Optional presentation title."
                },
                "audience": {
                    "type": "STRING",
                    "description": "Who will view the presentation, such as executives, investors, clients, or students."
                },
                "slide_count": {
                    "type": "INTEGER",
                    "description": "Final slide count from 3 to 50. Default: inferred or 8."
                },
                "tone": {
                    "type": "STRING",
                    "description": "Desired writing and visual tone, such as executive, persuasive, technical, or educational."
                },
                "theme": {
                    "type": "STRING",
                    "description": "Visual theme: jarvis_minimal | editorial | arc_reactor | executive | platinum. Default: jarvis_minimal."
                },
                "appearance": {
                    "type": "STRING",
                    "enum": ["auto", "light", "dark"],
                    "description": "Overall slide appearance. Honor light or dark when requested; auto uses the restrained dark JARVIS style."
                },
                "transition": {
                    "type": "STRING",
                    "enum": ["morph", "fade", "none"],
                    "description": "Native PowerPoint slide transition. Default: morph, with a fade fallback for older PowerPoint versions."
                },
                "source_file": {
                    "type": "STRING",
                    "description": "Backward-compatible single source path. Leave empty to use the uploaded file."
                },
                "source_files": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Source paths: PDF, Office files, data, text, images, audio, video, or PowerPoint."
                },
                "source_urls": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Specific source URLs supplied by the user."
                },
                "template_file": {
                    "type": "STRING",
                    "description": "Existing PPTX template or deck to preserve for edit/extend operations."
                },
                "model_source_file": {
                    "type": "STRING",
                    "description": "A PPTX used only as a native 3D model library. Its slides and text are not copied into the new presentation."
                },
                "use_native_3d": {
                    "type": "BOOLEAN",
                    "description": "The user's answer to the 3D-model question. Omit on the initial call unless the user already explicitly answered."
                },
                "three_d_mode": {
                    "type": "STRING",
                    "enum": ["ask", "yes", "no"],
                    "description": "Use ask on the initial call unless the user already explicitly requested or rejected 3D."
                },
                "quality": {
                    "type": "STRING",
                    "description": "fast | quality | premium. Default: quality."
                },
                "language": {
                    "type": "STRING",
                    "description": "Optional output language; otherwise infer from the request."
                },
                "allow_web_research": {
                    "type": "BOOLEAN",
                    "description": "Use broader web research. Set true only after the user explicitly permits web search."
                },
                "export_pdf": {
                    "type": "BOOLEAN",
                    "description": "Also export a PDF when Microsoft PowerPoint is available. Default: true."
                },
                "include_speaker_notes": {
                    "type": "BOOLEAN",
                    "description": "Generate editable speaker notes. Default: false."
                },
                "output_path": {
                    "type": "STRING",
                    "description": "Optional .pptx output path or destination folder."
                },
                "open_after_create": {
                    "type": "BOOLEAN",
                    "description": "Open the finished PowerPoint after creation. Default: false."
                },
            },
            "required": []
        }
    },
    {
        "name": "task_status",
        "description": "Checks or cancels background jobs, including presentation and deep-research jobs.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "get | all | cancel. Default: get."
                },
                "task_id": {
                    "type": "STRING",
                    "description": "Background task ID for get or cancel."
                },
            },
            "required": []
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
        "required": []
    }
},
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Fatih, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
]

# Tool names exposed by hosted clients. The names here are Gemini function
# declaration names (which differ from a few implementation module names).
CLOUD_SAFE_ACTIONS = frozenset({
    "web_search",
    "deep_research",
    "create_presentation",
    "flight_finder",
    "email_control",
    "youtube_video",
})

LOCAL_MACHINE_ONLY_ACTIONS = frozenset({
    "computer_control",
    "open_app",
    "file_controller",
    "media_control",
    "desktop_control",
    "computer_settings",
})

# Jarvis Ultron: no modo privado (JARVIS_CEREBRO=gemma) nada vai para IA na nuvem. Estas ferramentas
# mandam o pedido (ou a tela) para o Gemini, o Hermes (modelos grátis da Nous) ou outra IA na nuvem:
# não são oferecidas ao Gemma e são recusadas em _execute_tool. As automações da pasta marcam isso
# com USA_IA_NUVEM = True (ex.: claude_task, generate_video).
FERRAMENTAS_NUVEM_IA = frozenset({
    "web_search", "deep_research", "agent_task", "generate_image", "hermes_agent", "approve_publication",
    "create_presentation", "code_helper", "dev_agent", "file_processor", "screen_process", "flight_finder",
    "computer_control", "desktop_control", "computer_settings",
})

AVISO_MODO_PRIVADO = ("No modo privado isso não é usado, porque mandaria o pedido para uma IA na nuvem. "
                      "Para usar, diga 'modo normal'.")


def bloqueio_do_modo_privado(nome: str, args: dict | None = None) -> str | None:
    """Jarvis Ultron: no modo privado, a recusa (em português) para uma ferramenta que usa IA na nuvem;
    None quando pode rodar. Vale para o Gemma, o painel Ultron e qualquer outra chamada."""
    from core.cerebro_gemma import cerebro_gemma

    if not cerebro_gemma():
        return None
    args = args or {}
    if nome in FERRAMENTAS_NUVEM_IA:
        return AVISO_MODO_PRIVADO
    if nome == "youtube_video" and str(args.get("action", "")).strip().lower() == "summarize":
        return AVISO_MODO_PRIVADO  # o resumo do vídeo é feito pelo Gemini
    if nome == "school_tasks" and args.get("refresh"):
        return AVISO_MODO_PRIVADO  # ler o Geekie de novo é trabalho do Hermes
    automacao = carregar_automacoes().ferramentas.get(nome)
    if automacao is not None and getattr(automacao, "usa_ia_nuvem", False):
        return AVISO_MODO_PRIVADO
    return None


# Jarvis Ultron: ferramentas herdadas DESLIGADAS de propósito (Etapa 3 do docs/PLANO-REORGANIZACAO.md,
# decisão do Erton): agiam sem o "ok" dele conferido no código, ou ele não usa. Saíram da lista que o
# Gemini vê, da reserva e do prompt; os arquivos ficam no lugar até a Etapa 18. Se alguém chamar mesmo
# assim (um nome antigo, o modelo inventando), o _execute_tool responde isto e não chama nada.
# Nome -> o que ela fazia (vai na resposta ao modelo, em inglês como as outras).
FERRAMENTAS_DESLIGADAS = {
    "send_message": "sending messages on WhatsApp, Telegram, Discord, Instagram or iMessage",
    "prepare_message_reply": "drafting and sending message replies",
    "check_messages": "reading messages and contacts",
    "agent_task": "multi-step tasks that write and run AI-generated code",
    "code_helper": "writing, running and building code",
    "dev_agent": "building projects, installing packages and running code",
    "computer_control": "clicking, typing and moving the mouse anywhere on the screen",
    "game_updater": "installing and updating Steam and Epic games, which could shut down the computer",
}


def resposta_de_desligada(nome: str) -> str:
    """O que volta para o modelo quando ele chama uma ferramenta desligada (nada é chamado)."""
    return (f"Tool '{nome}' ({FERRAMENTAS_DESLIGADAS[nome]}) is turned off in Jarvis Ultron. "
            "Do not try to do this with another tool. Tell the user, in one short sentence in Portuguese, "
            "that you do not do this.")


_AUTOMACOES = None


def carregar_automacoes(recarregar: bool = False):
    """Jarvis Ultron: ferramentas da pasta 'automacoes' (um arquivo .py por automação)."""
    global _AUTOMACOES
    if _AUTOMACOES is None or recarregar:
        from core.automacoes import carregar_ferramentas

        # as desligadas também ficam reservadas: uma automação com o nome delas não carrega
        _AUTOMACOES = carregar_ferramentas(reservados={d.get("name") for d in TOOL_DECLARATIONS}
                                           | set(FERRAMENTAS_DESLIGADAS))
    return _AUTOMACOES


def get_tool_declarations(*, cloud_safe: bool = False) -> list[dict]:
    """Return the Gemini tools available for the requested runtime."""
    if not cloud_safe:
        extras = [a.declaracao for a in carregar_automacoes().ferramentas.values()]
        return list(TOOL_DECLARATIONS) + extras
    return [
        declaration
        for declaration in TOOL_DECLARATIONS
        if declaration.get("name") in CLOUD_SAFE_ACTIONS
    ]


class JarvisLive:

    def __init__(
        self,
        client: JarvisClient,
        voice_name: str = "Puck",
        *,
        cloud_safe: bool = False,
        api_key: str | None = None,
        external_audio: bool = False,
    ):
        # Keep ``ui`` as a compatibility alias for desktop integrations that
        # already inspect JarvisLive.ui. The engine contract is JarvisClient.
        self.client         = client
        self.ui             = client
        self.cloud_safe     = bool(cloud_safe)
        self.external_audio = bool(external_audio)
        self._api_key       = api_key.strip() if isinstance(api_key, str) else None
        self.tool_declarations = get_tool_declarations(cloud_safe=self.cloud_safe)
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self._falando_no_pc = 0  # Jarvis Ultron: a voz do Windows falando (trava própria do microfone)
        self._voz_externa_pendente = 0  # respostas que a voz externa (ElevenLabs...) ainda vai falar
        self.voice_name     = voice_name
        # optional runtime limit in seconds (set by main)
        self.runtime_limit_seconds: int | None = None
        # optional path that must exist (e.g. a mounted encrypted volume)
        self.required_unlock_path: str | None = None
        self.required_unlock_secret: str | None = None
        self._textos_trava = threading.Lock()  # texto digitado antes de o Gemini conectar
        self._textos_esperando = []
        self.ui.on_text_command = self._on_text_command
        self._voice_changed  = threading.Event()
        self._turn_done_event: asyncio.Event | None = None
        self._tts_engine = None
        self._ext_tts_provider = ""
        self._ext_tts_voice_id = ""
        self._ext_tts_api_key = ""
        self._current_input_transcript = ""
        self._last_input_transcript = ""
        self._last_input_transcript_at = 0.0
        # Jarvis Ultron: número e texto da fala atual do Erton (o "ok" das aprovações: core/aprovacao.py)
        self._fala_n = 0
        self._fala_texto = ""
        self._ouviu_depois_do_turno = True  # o microfone mandou áudio depois do último turno do Jarvis
        self._pending_self_quit = False
        self._pending_self_quit_farewell_received = False
        self._self_quit_timer = None
        self._shutdown_requested = threading.Event()
        self._tour_active = False
        # Jarvis Ultron: palavra de ativação ("Hey Jarvis") e IA reserva (Groq)
        from core.palavra_ativacao import PortaoDeVoz
        if self.external_audio or self.cloud_safe:
            self._portao = PortaoDeVoz(None, ativo=False)
        else:
            self._portao = PortaoDeVoz.da_configuracao(avisar=self.ui.write_log)
            self._portao.ao_mudar = self._aviso_de_escuta
            self._mostrar_selo(self._portao.estado)  # selo na tela desde a abertura, sem som
        from core.cerebro_gemma import CerebroGemma, cerebro_gemma

        if self.cloud_safe:
            self._reserva = None
        elif cerebro_gemma():  # Jarvis Ultron: Gemma 4 no PC como cérebro principal
            self._reserva = CerebroGemma.da_configuracao()
        else:  # Groq e/ou outra empresa (JARVIS_RESERVA), em fila: quando o limite de uma acaba, vai a outra
            from core.reserva_outra import reserva_da_configuracao

            self._reserva = reserva_da_configuracao()
        # modo privado mesmo se o Gemma não subiu (assim "modo normal" digitado ainda troca)
        self._cerebro_nome = "gemma" if (not self.cloud_safe and cerebro_gemma()) else "gemini"
        self._trocando_cerebro = False  # indo para o modo privado: nada do microfone/texto vai para a nuvem
        self._modo_reserva = False
        self._falhas_seguidas = 0
        self._avisos_trava = threading.Lock()  # avisos guardados no modo chamada
        self._avisos_guardados = []
        self._avisos_ao_falar = []  # quem quer saber quando o aviso guardado foi falado
        if not self.cloud_safe:
            self._iniciar_lembretes_geekie()
            threading.Thread(target=self._preparar_automacoes, daemon=True, name="Automacoes").start()

    def _on_text_command(self, text: str):
        # Jarvis Ultron: "modo chamada" / "modo mãos livres" (botões ou digitado) trocam na hora,
        # aqui mesmo, sem passar pela IA.
        from core.palavra_ativacao import modo_pedido

        modo = modo_pedido(text)
        if modo and len(str(text).split()) <= 6:
            self._definir_modo_escuta(modo)  # o som e o selo confirmam
            return
        # Jarvis Ultron: "modo privado" (Gemma no PC) / "modo normal" (Gemini) trocam o cérebro.
        if self._pedido_de_cerebro(text):
            return
        # Jarvis Ultron: "modo ultron" abre o painel de automações; "modo jarvis" fecha.
        if self._pedido_de_ultron(text):
            return
        # Autodiagnóstico sem depender do Gemini (é justamente quando ele falha que mais precisa)
        from core.autodiagnostico import pediu_diagnostico
        if pediu_diagnostico(text) and (not self.session or getattr(self, "_modo_reserva", False)):
            threading.Thread(target=self._autodiagnostico, daemon=True).start()
            return
        if getattr(self, "_trocando_cerebro", False):  # indo para o modo privado: não manda para a nuvem
            self.ui.write_log(f"SYS: 🔒 Trocando para o modo privado: {ESPERE_O_MODO_PRIVADO} e mande de novo.")
            return
        # no modo reserva vai para a reserva mesmo que sobre uma sessão do Gemini (o "ok" digitado também)
        if not self._loop or not self.session or getattr(self, "_modo_reserva", False):
            texto = str(text or "").strip()
            if getattr(self, "_reserva", None) is not None and texto:
                if not texto.startswith("["):  # [UI EVENT], [FILE_UPLOADED]: não são falas do Erton
                    # o "ok" digitado também é a fala atual do Erton (como no send_text e no _escutar_reserva)
                    self._current_input_transcript = self._last_input_transcript = texto
                    self._last_input_transcript_at = time.monotonic()
                    self._nova_fala(texto)
                threading.Thread(target=self._responder_pela_reserva, args=(text,), daemon=True).start()
                return
            if not str(text or "").strip() or self._guardar_ate_conectar(text):
                return
        envio = asyncio.run_coroutine_threadsafe(self.send_text(text), self._loop)
        envio.add_done_callback(lambda feito: self._avisar_se_nao_enviou(feito, text))

    def _avisar_se_nao_enviou(self, envio, text: str) -> None:
        """Jarvis Ultron: a conexão caiu bem na hora de mandar o texto digitado. Avisa na tela em vez
        de o texto sumir calado."""
        try:
            enviado = not envio.cancelled() and envio.exception() is None and envio.result() is not False
        except Exception:
            enviado = False
        if not enviado and str(text or "").strip():
            self.ui.write_log("ERR: Não consegui mandar o seu texto: a conexão com o Gemini caiu. "
                              "Mande de novo daqui a pouco.")

    def _nova_fala(self, texto: str, em_pedacos: bool = False) -> int:
        """Jarvis Ultron: uma fala NOVA do Erton (falada ou digitada). As aprovações só aceitam o
        "ok" numa fala com número maior que o da proposta (core/aprovacao.py). em_pedacos: fala do
        Gemini ao vivo, que ainda cresce até o fim do turno."""
        from core.aprovacao import nova_fala

        return nova_fala(self, texto, em_pedacos)

    def _trava_da_fala(self):
        if not hasattr(self, "_speaking_lock"):
            self._speaking_lock = threading.Lock()
        return self._speaking_lock

    def _trava_textos(self):
        if not hasattr(self, "_textos_trava"):
            self._textos_trava = threading.Lock()
            self._textos_esperando = []
        return self._textos_trava

    def _guardar_ate_conectar(self, text: str) -> bool:
        """Jarvis Ultron: texto que chegou antes de o Gemini conectar e sem reserva (o cérebro acabou
        de abrir, ou a tela entregou o que ficou guardado enquanto ele religava). Guarda (até 20) e
        run() manda assim que a sessão abrir: nada some calado. False se a sessão abriu agora mesmo."""
        from core.cerebro_gemma import cerebro_gemma

        if cerebro_gemma():  # modo privado sem o Gemma pronto: o pedido não vai para a nuvem depois
            self.ui.write_log("SYS: O Gemma 4 ainda não está pronto; no modo privado o seu pedido não vai "
                              "para a nuvem. Repita daqui a pouco.")
            return True
        with self._trava_textos():
            if self._loop and self.session:
                return False
            if len(self._textos_esperando) >= 20:
                return True
            self._textos_esperando.append(str(text))
            primeiro = len(self._textos_esperando) == 1
            if not str(text).strip().startswith("["):  # [UI EVENT], [FILE_UPLOADED] não contam
                # conta a fala agora, quando ele digitou (e não quando for mandada): um "ok" digitado
                # antes de ouvir uma proposta não pode valer como resposta a ela
                self._nova_fala(str(text).strip())
        if primeiro:
            self.ui.write_log("SYS: Ainda estou conectando ao Gemini; respondo assim que conectar.")
        return True

    async def _mandar_textos_esperando(self, textos) -> None:
        """Jarvis Ultron: manda ao Gemini, na ordem, o que foi digitado antes de ele conectar."""
        for texto in textos:
            try:
                await self.send_text(texto, contar=False)  # já contou quando ele digitou
            except Exception as erro:
                print(f"[JARVIS] ⚠️ Texto guardado não foi enviado: {erro}")

    async def send_text(self, text: str, contar: bool = True) -> bool:
        """Send a text turn from either the desktop callback or a web client.
        contar=False: texto guardado até conectar, já contado como fala quando foi digitado."""
        if not self.session:
            return False
        self._current_input_transcript = str(text or "").strip()
        if not self._current_input_transcript:
            return False
        self._last_input_transcript = self._current_input_transcript
        self._last_input_transcript_at = time.monotonic()
        if contar and not self._current_input_transcript.startswith("["):  # [UI EVENT], [FILE_UPLOADED] não contam
            self._nova_fala(self._current_input_transcript)
        if not self._current_input_transcript.startswith("["):  # digitou: a resposta sai em voz
            self._resposta_digitada_ate = time.monotonic() + self.RESPOSTA_DIGITADA_FALA
        self._checar_pedido_de_modo(self._current_input_transcript)
        outgoing_text = self._current_input_transcript
        if (
            not getattr(self, "_pending_self_quit", False)
            and self._is_explicit_self_quit_transcript(self._current_input_transcript)
        ):
            self._queue_self_quit_after_farewell()
            outgoing_text = (
                "[VERIFIED LOCAL SELF-SHUTDOWN] The user explicitly asked JARVIS to quit. "
                f'Say exactly: "{SELF_QUIT_GOODBYE}" Do not call a tool and say nothing else.'
            )
        await self.session.send_client_content(
            turns={"parts": [{"text": outgoing_text}]},
            turn_complete=True,
        )
        return True

    async def send_audio_chunk(
        self,
        data: bytes,
        mime_type: str = "audio/pcm;rate=16000",
    ) -> bool:
        """Queue browser-captured PCM for the active Gemini Live session."""
        if not data or self.out_queue is None or self._shutdown_requested.is_set() \
                or getattr(self, "_trocando_cerebro", False):
            return False
        await self.out_queue.put({"data": data, "mime_type": mime_type})
        self._microfone_mandou_audio()
        return True

    def _microfone_mandou_audio(self) -> None:
        """Jarvis Ultron: o microfone mandou áudio ao Gemini com o Jarvis calado. Só depois disso a
        transcrição que chegar pode ser uma fala NOVA do Erton (core/aprovacao.py): enquanto o Jarvis
        fala, o microfone fica fechado. Com voz externa, o som de antes de ela terminar a resposta
        (a síntese demora, e só quando ela começa o microfone fecha) também não conta."""
        with self._trava_da_fala():
            if not getattr(self, "_is_speaking", False) and not getattr(self, "_voz_externa_pendente", 0):
                self._ouviu_depois_do_turno = True

    def set_speaking(self, value: bool):
        with self._trava_da_fala():
            # Jarvis Ultron: enquanto a voz do PC fala (avisos sigilosos, _falar_no_pc), o fim da fala do
            # Gemini ou da voz reserva não reabre o microfone: senão o resto do texto sigiloso ia para a nuvem
            value = bool(value) or getattr(self, "_falando_no_pc", 0) > 0
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")
        if not value and getattr(self, "_portao", None) is not None:
            self._portao.estender()

    def speak(self, text: str) -> bool:
        if not self._loop or not self.session:
            return False
        try:
            asyncio.run_coroutine_threadsafe(
                self.session.send_client_content(
                    turns={"parts": [{"text": text}]},
                    turn_complete=True
                ),
                self._loop
            )
            return True
        except Exception:
            return False

    def _speak_vision_result(self, text: str) -> bool:
        """Send finished vision text through JARVIS's active voice session."""
        result = " ".join(str(text or "").split())
        if not result:
            return False
        directive = (
            "[INTERNAL VISION OUTPUT] Read the following vision result to the user "
            "verbatim. Do not add an introduction, commentary, or a tool call. "
            f"Vision result: {json.dumps(result, ensure_ascii=False)}"
        )
        return self.speak(directive)

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    @staticmethod
    def _is_explicit_self_quit_transcript(text: str) -> bool:
        """Only match commands that clearly target JARVIS, never the computer."""
        normalized = " ".join(str(text or "").lower().split())
        if not normalized:
            return False
        if re.search(r"\b(?:computer|mac|pc|system|machine)\b", normalized):
            return False
        if re.search(r"\b(?:stop talking|be quiet|cancel|never mind)\b", normalized):
            return False
        if normalized in {
            "quit", "exit", "shutdown", "shut down", "turn off", "power down",
            "go offline", "goodbye jarvis", "goodbye jarvis please",
        }:
            return True
        return any(pattern.search(normalized) for pattern in _SELF_QUIT_PATTERNS)

    def _queue_self_quit_after_farewell(self) -> None:
        """Arm shutdown without closing until the response audio is fully drained."""
        self._pending_self_quit = True
        self._pending_self_quit_farewell_received = False
        try:
            self.ui.write_log("SYS: Shutdown queued; waiting for JARVIS's farewell.")
        except Exception:
            pass
        # A voice model can occasionally omit audio/turn_complete. Do not
        # leave the user with a permanently armed shutdown in that case.
        try:
            if self._self_quit_timer is not None:
                self._self_quit_timer.cancel()
            self._self_quit_timer = threading.Timer(8.0, self._force_complete_self_quit)
            self._self_quit_timer.daemon = True
            self._self_quit_timer.start()
        except Exception:
            pass

    def _force_complete_self_quit(self) -> None:
        if not getattr(self, "_pending_self_quit", False):
            return
        self._pending_self_quit_farewell_received = True
        self._complete_self_quit_after_audio()

    def _mark_self_quit_farewell_received(self) -> None:
        if getattr(self, "_pending_self_quit", False):
            self._pending_self_quit_farewell_received = True

    def _complete_self_quit_after_audio(self) -> bool:
        """Close through the UI only after a farewell turn has actually completed."""
        if not (
            getattr(self, "_pending_self_quit", False)
            and getattr(self, "_pending_self_quit_farewell_received", False)
        ):
            return False
        self._pending_self_quit = False
        self._pending_self_quit_farewell_received = False
        if getattr(self, "_self_quit_timer", None) is not None:
            self._self_quit_timer.cancel()
            self._self_quit_timer = None
        self.request_shutdown()
        self.ui.handle_ui_command("Quit JARVIS")
        return True

    def _encerrar_fim_do_teste(self) -> None:
        """Acabou o tempo de teste (JARVIS_TRIAL_KEYWORD): fecha o Jarvis."""
        print(f"[JARVIS] ⏱️ Runtime limit reached ({self.runtime_limit_seconds}s). Exiting.")
        try:
            jarvis_status.write_status({"state": "expired"})
        except Exception:
            pass
        from core.ponte import SAIDA_FIM_DO_TESTE

        # Cérebro em programa próprio: o código diz à tela para fechar tudo (e não religar o
        # cérebro com um tempo novo). Num programa só, sai com 0 (o .bat não acusa erro).
        os._exit(SAIDA_FIM_DO_TESTE if getattr(self.ui, "remota", False) else 0)

    def request_shutdown(self) -> None:
        """Stop live tasks and make the process exit after the UI closes."""
        shutdown_requested = getattr(self, "_shutdown_requested", None)
        if shutdown_requested is None:
            self._shutdown_requested = threading.Event()
            shutdown_requested = self._shutdown_requested
        if shutdown_requested.is_set():
            return
        shutdown_requested.set()
        try:
            session = getattr(self, "session", None)
            loop = getattr(self, "_loop", None)
            if session is not None and loop is not None:
                asyncio.run_coroutine_threadsafe(session.close(), loop)
            out_queue = getattr(self, "out_queue", None)
            if out_queue is not None:
                out_queue.put_nowait(None)
        except Exception as exc:
            print(f"[JARVIS] ⚠️ Shutdown session close failed: {exc}")

    def set_tour_active(self, active: bool) -> None:
        """Track whether the desktop introduction temporarily owns the UI."""
        self._tour_active = bool(active)

    async def _wait_before_reconnect(self, delay: float) -> None:
        deadline = time.monotonic() + max(0.0, float(delay))
        while not self._shutdown_requested.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            await asyncio.sleep(min(0.1, remaining))

    def _intercept_ui_tool_call(self, name: str, args: dict) -> str | None:
        """Safety net for stale models that attempt the removed quit tool action."""
        action = str(args.get("action") or "").strip().lower()
        if name != "shutdown_jarvis" and not (
            name == "jarvis_ui_control" and action == "quit_jarvis"
        ):
            return None

        transcript = str(getattr(self, "_current_input_transcript", "") or "")
        if not transcript:
            age = time.monotonic() - float(getattr(self, "_last_input_transcript_at", 0.0) or 0.0)
            if age <= 5.0:
                transcript = str(getattr(self, "_last_input_transcript", "") or "")

        if not self._is_explicit_self_quit_transcript(transcript):
            return "Ignored an unverified shutdown request. JARVIS remains online."

        self._queue_self_quit_after_farewell()
        return f'Shutdown queued. Say exactly: "{SELF_QUIT_GOODBYE}"'

    def update_voice(self, voice_name: str):
        self.voice_name = _normalize_voice_name(voice_name)
        self.ui.write_log(f"SYS: Voice change requested: {self.voice_name}")
        try:
            self.ui.sync_voice_display(self.voice_name)
        except Exception:
            pass
        if self.session and self._loop:
            try:
                asyncio.run_coroutine_threadsafe(self.session.close(), self._loop)
            except Exception as e:
                print(f"[JARVIS] ⚠️ Could not close session after voice change: {e}")

    def _get_current_voice(self) -> str:
        if getattr(self, "voice_name", None):
            return _normalize_voice_name(self.voice_name)
        voice_combo = getattr(self.ui, "_voice_combo", None)
        if voice_combo is not None:
            idx = voice_combo.currentIndex()
            if idx >= 0:
                voice = voice_combo.itemData(idx)
                if isinstance(voice, str) and voice:
                    return _normalize_voice_name(voice)
            voice = voice_combo.currentText().strip().lower()
            if voice in SUPPORTED_VOICE_NAMES:
                return voice
        return _load_voice_name()

    def _autodiagnostico(self, falar: bool = True, so_resumo: bool = False) -> str:
        """Jarvis Ultron: confere as próprias peças; mostra na tela, salva em Documentos e (se falar) diz.
        so_resumo=True devolve só a frase curta feita para a voz (botão do painel Ultron)."""
        from core import autodiagnostico

        self.ui.write_log("SYS: Fazendo o autodiagnóstico...")
        itens = autodiagnostico.diagnosticar(getattr(self, "_portao", None))
        texto = autodiagnostico.relatorio(itens)
        try:
            arquivo = autodiagnostico.salvar(texto)
            self.ui.write_log(f"SYS: Relatório salvo em {arquivo}")
        except OSError:
            pass
        for linha in texto.splitlines()[2:]:
            self.ui.write_log(f"SYS: {linha.strip()}")
        print(texto)
        if falar:
            self._falar_reserva(autodiagnostico.resumo_falado(itens))
        if so_resumo:
            return autodiagnostico.resumo_falado(itens)
        return texto + "\n\nSummarize for the user in Portuguese: only the problems (DEFEITO/ATENÇÃO) and how to fix them."

    async def _geekie_pendencias(self, atualizar: bool = False) -> str:
        """Jarvis Ultron: pendências do Geekie One (lista salva pelo Hermes; lê de novo se velha)."""
        from core import geekie, hermes_ponte
        from core.cerebro_gemma import cerebro_gemma

        atividades, atualizado = geekie.ler()
        # no modo privado o Hermes (IA na nuvem) não é chamado: fica a lista salva
        if (atualizar or geekie.desatualizada(atualizado)) and hermes_ponte.configurado() and not cerebro_gemma():
            return await self._hermes_sem_travar(
                "Use a skill geekie-pendencias agora: leia (somente leitura) as atividades pendentes do "
                "Geekie One, salve a lista e responda o resumo falado.")
        if not atividades and atualizado is None:
            return ("There is no Geekie list yet. Tell the user in Portuguese that Hermes reads Geekie One at 7h "
                    "and 18h, and that he must log in once on Geekie One in Hermes' browser.")
        return geekie.resumo(atividades) + " (Say this to the user in Portuguese.)"

    def _verificar_lembretes_geekie(self) -> list[str]:
        """Uma passada: lembra (uma vez por dia) das atividades que vencem em até 2 dias."""
        from core import geekie

        atividades, _ = geekie.ler()
        devidas = geekie.lembretes_do_dia(atividades, geekie.carregar_avisados())
        if not devidas:
            return []
        frases = [geekie.frase_lembrete(a) for a in devidas]
        self.anunciar(" ".join(frases), titulo="Geekie")
        geekie.marcar_avisados(devidas)
        return frases

    # ---------- Jarvis Ultron: avisos falados (lembretes, Geekie, automações) ----------

    AVISO_ESPERA_AO_CHAMAR = 4.0  # segundos depois do "Hey Jarvis" para falar os avisos guardados

    def anunciar(self, texto: str, titulo: str = "Lembrete", sigiloso: bool = False, ao_falar=None) -> str:
        """Fala um aviso em voz alta respeitando o modo de escuta. Qualquer fio pode chamar.

        - conversa aberta (mãos livres ou depois do "Hey Jarvis"): o Jarvis fala agora;
        - modo chamada esperando o "Hey Jarvis": toca um som, mostra na tela e guarda o aviso
          para falar assim que você chamar (JARVIS_AVISO_FALA_SEMPRE=1 fala mesmo assim);
        - sem o Gemini (modo reserva): fala com a voz reserva;
        - sigiloso=True (ex.: resultado do Claude, que lê arquivos de clientes): fala só com a voz do
          Windows, no PC; o texto nunca vai para o Gemini.
        Devolve "falado", "guardado" ou "na_tela". Se ficou "guardado", ao_falar (opcional) é
        chamado quando o aviso for falado de verdade (o plano do Claude só vale depois disso).
        """
        texto = " ".join(str(texto or "").split())
        if not texto:
            return "na_tela"
        self.ui.write_log(f"SYS: 🔔 {titulo}: {texto}")
        self._notificar_na_tela(titulo, texto)
        try:
            from core.palavra_ativacao import tocar_aviso

            tocar_aviso("lembrete")
        except Exception:
            pass
        fala_sempre = os.environ.get("JARVIS_AVISO_FALA_SEMPRE", "0").strip().lower() in {"1", "true", "sim", "yes"}
        if self._chamada_fechada() and not fala_sempre:
            with self._trava_avisos():
                self._avisos_guardados.append((texto, sigiloso))
                if ao_falar is not None:
                    self._avisos_ao_falar.append(ao_falar)
            return "guardado"
        return self._falar_aviso(texto, sigiloso=sigiloso)

    def _trava_avisos(self):
        if not hasattr(self, "_avisos_trava"):
            self._avisos_trava = threading.Lock()
            self._avisos_guardados = []
        if not hasattr(self, "_avisos_ao_falar"):
            self._avisos_ao_falar = []
        return self._avisos_trava

    def _falar_aviso(self, texto: str, sigiloso: bool = False) -> str:
        if sigiloso:  # nunca vai para a IA na nuvem nem para a voz da internet
            if getattr(self, "ui", None) is not None and not getattr(self.ui, "muted", False):
                threading.Thread(target=self._falar_no_pc, args=(texto,), daemon=True, name="Aviso").start()
                return "falado"
            return "na_tela"
        session, loop = getattr(self, "session", None), getattr(self, "_loop", None)
        if session is not None and loop is not None and not getattr(self, "_modo_reserva", False):
            aviso = (f"[Aviso do Jarvis] {texto}\n"
                     "Diga isso ao usuário agora, em português do Brasil, em uma ou duas frases curtas. "
                     "Não chame ferramentas.")
            asyncio.run_coroutine_threadsafe(
                session.send_client_content(turns={"parts": [{"text": aviso}]}, turn_complete=True), loop)
            return "falado"
        if getattr(self, "ui", None) is not None and not getattr(self.ui, "muted", False):
            threading.Thread(target=self._falar_reserva, args=(texto,), daemon=True, name="Aviso").start()
            return "falado"
        return "na_tela"

    VOZ_DO_PC_ESPERA = 30.0  # no máximo isso esperando a outra voz terminar antes de ler o aviso sigiloso

    def _falar_no_pc(self, texto: str, esperar: bool = True) -> None:
        """Voz do próprio Windows: o texto não sai do PC (avisos sigilosos).

        Enquanto ela fala, o microfone fica fechado por uma trava só dela (_falando_no_pc): o fim da
        fala do Gemini ou da voz reserva não o reabre no meio da leitura (sem isso, o resto do texto
        ia pelo microfone para o Gemini ou para o Groq). esperar: antes de começar, espera a outra voz
        terminar, para as duas não falarem juntas."""
        from actions.tts_engine import falar_com_voz_do_windows

        if esperar:
            limite = time.monotonic() + self.VOZ_DO_PC_ESPERA
            while getattr(self, "_is_speaking", False) and time.monotonic() < limite:
                time.sleep(0.1)
        with self._trava_da_fala():
            self._falando_no_pc = getattr(self, "_falando_no_pc", 0) + 1
        self.set_speaking(True)
        try:
            falar_com_voz_do_windows(texto)
        finally:
            with self._trava_da_fala():
                self._falando_no_pc = max(0, getattr(self, "_falando_no_pc", 1) - 1)
            self.set_speaking(False)

    def _falar_avisos_guardados(self) -> None:
        """Chamado quando a conversa abre ("Hey Jarvis" ou mãos livres): fala o que ficou guardado."""
        with self._trava_avisos():
            if not self._avisos_guardados:
                return
        def depois():
            time.sleep(self.AVISO_ESPERA_AO_CHAMAR)
            if self._chamada_fechada():
                return  # a conversa fechou de novo; continuam guardados
            with self._trava_avisos():
                guardados, self._avisos_guardados = self._avisos_guardados, []
                ao_falar, self._avisos_ao_falar = self._avisos_ao_falar, []
            sigilosos = [t for t, sigiloso in guardados if sigiloso]
            comuns = [t for t, sigiloso in guardados if not sigiloso]
            if sigilosos:  # primeiro os sigilosos, pela voz do PC (nunca juntos num pedido ao Gemini)
                self._falar_no_pc("Enquanto você estava fora: " + " ".join(sigilosos))
            if comuns:
                self._falar_aviso(("Enquanto você estava fora: " if not sigilosos else "") + " ".join(comuns))
            for avisar in ao_falar:  # só agora o Erton ouviu (ex.: o plano do Claude passa a valer)
                try:
                    avisar()
                except Exception as erro:
                    print(f"[Aviso] {erro}")
        threading.Thread(target=depois, daemon=True, name="AvisosGuardados").start()

    def _notificar_na_tela(self, titulo: str, texto: str) -> None:
        """Balão do Windows (perto do relógio) e aviso dentro da janela do Jarvis."""
        if getattr(self.ui, "remota", False):  # tela em outro programa: ela mesma mostra
            self.ui.notificar(titulo, texto)
            return
        janela = getattr(getattr(self, "ui", None), "_win", None)
        if janela is None:
            return
        try:
            from core.na_tela import executar

            def mostrar():
                bandeja = getattr(janela, "_tray", None)
                if bandeja is not None and bandeja.isVisible():
                    from PyQt6.QtWidgets import QSystemTrayIcon

                    bandeja.showMessage(f"Jarvis · {titulo}", texto, QSystemTrayIcon.MessageIcon.Information, 10000)
                mostrar_aviso = getattr(janela, "_show_toast", None)
                if callable(mostrar_aviso):
                    mostrar_aviso(f"{titulo}: {texto}", "warning")

            executar(mostrar)
        except Exception as erro:
            print(f"[Aviso] Tela: {erro}")

    def _preparar_automacoes(self) -> None:
        """Mostra as automações da pasta 'automacoes' e copia as do Hermes (.md) para o perfil dele."""
        from core.automacoes import sincronizar_habilidades

        carga = carregar_automacoes()
        habilidades = sincronizar_habilidades()
        com_ferramenta = {a.arquivo.name for a in carga.ferramentas.values()}
        nomes = list(carga.ferramentas) + [a.rsplit(".", 1)[0] for a, _ in carga.inicios if a not in com_ferramenta]
        nomes += [f"{n} (Hermes)" for n in habilidades.habilidades]
        if nomes:
            self.ui.write_log("SYS: Automações: " + ", ".join(nomes))
        for arquivo, motivo in carga.erros + habilidades.erros:
            self.ui.write_log(f"SYS: Automação com problema: {arquivo}: {motivo}")
            print(f"[Automações] {arquivo}: {motivo}")
        tela_em_outro_programa = bool(getattr(self.ui, "remota", False))
        for arquivo, iniciar in carga.inicios:
            if tela_em_outro_programa and arquivo in carga.na_tela:
                continue  # roda no programa da tela (core/ponte.py)
            try:
                iniciar(self)
            except Exception as erro:
                self.ui.write_log(f"SYS: Automação com problema: {arquivo}: {erro}")
                print(f"[Automações] {arquivo}: {erro}")

    def _iniciar_lembretes_geekie(self) -> None:
        def laco():
            time.sleep(90)  # deixa o Jarvis conectar primeiro
            while not self._shutdown_requested.is_set():
                try:
                    self._verificar_lembretes_geekie()
                except Exception as erro:
                    print(f"[Geekie] Lembretes: {erro}")
                self._shutdown_requested.wait(30 * 60)

        threading.Thread(target=laco, daemon=True, name="LembretesGeekie").start()

    HERMES_ESPERA = 25  # segundos que a conversa espera o Hermes; depois ele termina em segundo plano

    async def _hermes_sem_travar(self, pedido: str) -> str:
        """Jarvis Ultron: tarefas do Hermes podem levar minutos. Espera um pouco; se demorar, a
        conversa segue e o resultado é entregue quando ficar pronto (antes o Jarvis travava)."""
        from core import hermes_ponte
        from core.cerebro_gemma import cerebro_gemma

        if cerebro_gemma():  # modo privado: o Hermes roda em IA na nuvem
            return AVISO_MODO_PRIVADO

        tarefa = asyncio.ensure_future(asyncio.to_thread(hermes_ponte.perguntar, pedido))
        try:
            return await asyncio.wait_for(asyncio.shield(tarefa), timeout=self.HERMES_ESPERA)
        except asyncio.TimeoutError:
            tarefa.add_done_callback(lambda t: self._entregar_resultado_hermes(pedido, t))
            self.ui.write_log("SYS: Hermes trabalhando em segundo plano...")
            return ("Hermes is still working on this long task in the background. Tell the user, in one short "
                    "sentence in Portuguese, that you will bring the answer as soon as it is ready. Do not wait.")

    def _entregar_resultado_hermes(self, pedido: str, tarefa) -> None:
        """Mostra o resultado na tela e, se a conversa estiver aberta, pede para o Jarvis resumir em voz."""
        try:
            texto = tarefa.result()
        except Exception as erro:
            texto = f"O Hermes falhou: {erro}"
        self.ui.write_log(f"Hermes: {texto[:500]}")
        session, loop = getattr(self, "session", None), getattr(self, "_loop", None)
        if session is None or loop is None or self._chamada_fechada():
            return  # modo chamada esperando o "Hey Jarvis": fica só na tela
        aviso = (f"[Resultado do Hermes para o pedido: {pedido}]\n{texto}\n"
                 "Resuma isso para o usuário agora, em português do Brasil, em poucas frases. "
                 "Não chame ferramentas.")
        asyncio.run_coroutine_threadsafe(
            session.send_client_content(turns={"parts": [{"text": aviso}]}, turn_complete=True), loop)

    def _chamada_fechada(self) -> bool:
        """Jarvis Ultron: True no modo chamada enquanto ninguém disse "Hey Jarvis"."""
        portao = getattr(self, "_portao", None)
        return portao is not None and portao.estado == "aguardando"

    RESPOSTA_DIGITADA_FALA = 90.0  # segundos em que a resposta a um texto digitado sai em voz

    def _pode_falar_agora(self) -> bool:
        """Jarvis Ultron: fala em voz alta com a conversa aberta, e também a resposta ao que o Erton
        acabou de DIGITAR (no modo chamada digitar é chamar o Jarvis). O microfone continua fechado:
        digitar não manda o som do ambiente para a nuvem."""
        if not self._chamada_fechada():
            return True
        return time.monotonic() < float(getattr(self, "_resposta_digitada_ate", 0.0) or 0.0)

    async def _announce_startup(self):
        # Jarvis Ultron: cumprimenta uma vez só (não a cada reconexão) e nunca com a chamada fechada.
        if getattr(self, "_ja_cumprimentou", False) or self._chamada_fechada():
            return
        self._ja_cumprimentou = True
        try:
            memory = load_memory()
            name_entry = memory.get("identity", {}).get("name")
            name = None
            if isinstance(name_entry, dict):
                name = name_entry.get("value")
            elif isinstance(name_entry, str):
                name = name_entry
            # Jarvis Ultron: saudação em português
            greeting = (
                f"(Sistema iniciado. Cumprimente {name or 'o Erton'} em português do Brasil, "
                "em uma frase curta e marcante, como o Jarvis Ultron, e pergunte como pode ajudar.)"
            )
            await self.session.send_client_content(
                turns={"parts": [{"text": greeting}]},
                turn_complete=True,
            )
        except Exception as e:
            print(f"[JARVIS] ⚠️ Greeting failed: {e}")

    def _build_config(self, modelo: str = "") -> types.LiveConnectConfig:
        from datetime import datetime

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        parts = [REGRA_IDIOMA, time_ctx]
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)
        parts.append(REGRA_IDIOMA)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{
                "function_declarations": getattr(
                    self,
                    "tool_declarations",
                    TOOL_DECLARATIONS,
                )
            }],
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
                    end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                    silence_duration_ms=LIVE_VAD_SILENCE_MS,
                )
            ),
            thinking_config=_pensamento_da_voz(modelo),
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self._get_current_voice()
                    )
                ),
                **({"language_code": self._idioma_voz()} if self._idioma_voz() else {}),
            ),
        )

    def _idioma_voz(self) -> str:
        """Jarvis Ultron: idioma da voz (JARVIS_IDIOMA, padrão pt-BR). Vazio se o modelo recusou."""
        if getattr(self, "_idioma_recusado", False):
            return ""
        return os.environ.get("JARVIS_IDIOMA", "pt-BR").strip()

    def _definir_modo_escuta(self, modo: str) -> str:
        """Jarvis Ultron: 'maos_livres' (ouve tudo) ou 'chamada' (só depois de "Hey Jarvis")."""
        portao = getattr(self, "_portao", None)
        if modo not in ("maos_livres", "chamada") or portao is None:
            return "Invalid mode. Use 'maos_livres' or 'chamada'."
        if portao.modo == modo:
            self._aviso_de_escuta(portao.estado)  # confirma com o som e o selo
            return QUIET_MODE_RESULT
        if not portao.definir_modo(modo):
            return ("Call mode is unavailable because the activation detector did not load. "
                    "Tell the user, in Portuguese, that you will keep listening to everything.")
        if modo == "maos_livres":
            self.ui.write_log("SYS: Modo mãos livres: estou ouvindo tudo.")
        else:
            self.ui.write_log(f"SYS: Modo chamada: {portao.como_chamar} para falar comigo.")
        return QUIET_MODE_RESULT

    def _aviso_de_escuta(self, estado: str) -> None:
        """Jarvis Ultron: som curto + selo na tela quando ele começa/para de ouvir ou o modo muda."""
        from core.palavra_ativacao import tocar_aviso

        print(f"[Ativação] {estado}")
        tocar_aviso(estado)
        self._mostrar_selo(estado)
        if estado in ("ouvindo", "maos_livres"):
            self._falar_avisos_guardados()

    def _mostrar_selo(self, estado: str) -> None:
        mostrar = getattr(self.ui, "set_listening_status", None)
        if callable(mostrar):
            mostrar(estado)

    def _pedido_de_cerebro(self, fala: str) -> bool:
        """Jarvis Ultron: "modo privado" -> Gemma 4 no PC; "modo normal" -> Gemini. True se era isso."""
        from core.cerebro_gemma import pedido_de_privacidade

        destino = pedido_de_privacidade(fala)
        if destino is None:
            return False
        if destino == "gemma" and getattr(self, "_cerebro_nome", "gemini") != "gemma":
            # Até o cérebro novo subir (a checagem do Ollama pode levar segundos), nada do microfone
            # nem do texto vai para a nuvem. Se a troca não acontecer, _trocar_cerebro libera.
            self._trocando_cerebro = True
            self.ui.write_log(f"SYS: 🔒 Preparando o modo privado: {ESPERE_O_MODO_PRIVADO} antes de falar de clientes.")
        threading.Thread(target=self._trocar_cerebro, args=(destino,), daemon=True, name="TrocarCerebro").start()
        return True

    def _pedido_de_ultron(self, fala: str) -> bool:
        """Jarvis Ultron: "modo ultron" abre o painel de automações; "modo jarvis" (ou "sair do modo
        ultron") fecha. Vale digitado e falado (Gemini ao vivo e reserva). True se era isso."""
        import unicodedata

        texto = unicodedata.normalize("NFKD", str(fala or "").lower())
        texto = "".join(c for c in texto if not unicodedata.combining(c))
        texto = " ".join(re.sub(r"[^\w\s]", " ", texto).split())  # tira vírgula, ponto, "!" da transcrição
        if not texto or len(texto.split()) > 6:  # só frases curtas (um pedido, não uma conversa)
            return False
        if not ("modo ultron" in texto or "modo jarvis" in texto or texto == "ultron"):
            return False
        # "Jarvis, modo Ultron" tem "jarvis" no começo: quem decide fechar é "modo jarvis", não o nome
        fechar = "modo jarvis" in texto or bool(re.search(
            r"\b(sai|sair|saia|fecha|fechar|feche|desliga|desligar|desligue|desativa|desativar|desative"
            r"|encerra|encerrar|encerre|tira|tirar|tire)( do| o)? modo ultron\b", texto))
        # o painel Ultron registra _abrir_ultron; com a tela em outro programa, vai pela ponte
        abrir = getattr(self, "_abrir_ultron", None) or getattr(self.ui, "abrir_ultron", None)
        if callable(abrir):
            abrir(fechar=fechar)
        return True

    def _trocar_cerebro(self, destino: str) -> None:
        from core.cerebro_gemma import modelo_instalado, whisper_instalado

        atual = "gemma" if getattr(self, "_cerebro_nome", "gemini") == "gemma" else "gemini"
        if destino == atual:
            self._trocando_cerebro = False
            texto = "Já estou no modo privado." if destino == "gemma" else "Já estou no modo normal."
            self.ui.write_log(f"SYS: {texto}")
            self._falar_aviso(texto)
            return
        from core.claude_chefe import aplicando

        if aplicando():
            # religar o cérebro agora mataria a mudança do Claude no meio (sem testes e sem desfazer)
            self._recusar_troca(destino, "O Claude está mudando o meu código agora. Espere ele terminar para "
                                         "trocar de modo; eu aviso quando acabar.")
            return
        trocar = getattr(self.ui, "trocar_cerebro", None)
        if not callable(trocar):
            self._trocando_cerebro = False
            self._troca_pela_voz_indisponivel(destino)
            return
        if destino == "gemma" and not whisper_instalado():
            # sem ouvir no PC, a voz não pode ir para a nuvem: não liga
            self._recusar_troca(destino, "O modo privado não foi ligado: falta a transcrição local da sua voz. "
                                         "Dê dois cliques em Instalar voz local, na pasta do Jarvis.")
            return
        if destino == "gemma" and not modelo_instalado():
            self._recusar_troca(destino, "Para o modo privado, primeiro rode o Instalar Gemma 4 na pasta do Jarvis.")
            return
        if destino == "gemma":
            self.ui.write_log("SYS: 🔒 Entrando no modo privado: o cérebro passa a ser o Gemma 4, no seu PC...")
        else:
            self.ui.write_log("SYS: Voltando ao modo normal (Gemini)...")
        self._avisar_o_que_para(destino)
        trocar(destino)  # a tela religa o programa do cérebro já com o cérebro novo

    # Trabalhos em segundo plano (pelo nome do fio) que morrem quando o cérebro é religado
    TRABALHOS_QUE_PARAM = {"VideoVeo": "video", "ClaudeTarefa": "claude", "ClaudePlano": "plano",
                           "HermesPublicar": "hermes"}

    def _avisar_o_que_para(self, destino: str) -> None:
        """Religar o cérebro mata o que roda em segundo plano: o Erton fica sabendo ANTES (tela e voz do
        PC; o texto não leva dados dele). A troca não é recusada: o modo privado sempre vem primeiro."""
        rodando = {self.TRABALHOS_QUE_PARAM[t.name] for t in threading.enumerate()
                   if t.name in self.TRABALHOS_QUE_PARAM and t.is_alive()}
        partes = []
        if "video" in rodando:  # automacoes/videos.py anotou o pedido: o cérebro novo busca o vídeo
            partes.append("Um vídeo pago ainda está sendo feito. Ele não se perde: anotei o pedido e busco o vídeo "
                          + ("quando você voltar ao modo normal." if destino == "gemma" else "assim que eu religar."))
        if "claude" in rodando:
            partes.append("A tarefa do Claude que estava rodando vai parar; peça de novo depois.")
        if "plano" in rodando:
            partes.append("O plano do Claude que estava sendo feito vai parar; peça de novo depois.")
        if "hermes" in rodando:
            partes.append("O Hermes está publicando o que você aprovou e eu não vou conseguir contar o resultado; "
                          "confira antes de pedir de novo.")
        if not partes:
            return
        aviso = " ".join(partes)
        self.ui.write_log(f"SYS: ⚠️ {aviso}")
        if not getattr(self.ui, "muted", False):
            try:  # antes de religar (depois não dá mais); a nuvem já está calada para o modo privado
                self._falar_no_pc(aviso)
            except Exception as erro:
                print(f"[Cérebro] Não consegui avisar em voz alta: {erro}")

    def _recusar_troca(self, destino: str, texto: str) -> None:
        """A troca de cérebro não vai acontecer: libera o microfone e o texto (não vai trocar) e avisa na
        tela e em voz alta. Na tela sempre: com o microfone desligado e sem o Gemini, a voz não sai, e
        sem isso ficava só o "espere o selo" (e o próximo texto ia para a nuvem sem ele saber)."""
        self._trocando_cerebro = False
        if destino == "gemma":
            self.ui.write_log(f"SYS: 🔒 Modo privado NÃO ligado: {texto}")
        else:
            self.ui.write_log(f"SYS: Modo normal NÃO ligado: {texto}")
        self._falar_aviso(texto)

    def _troca_pela_voz_indisponivel(self, destino: str) -> None:
        """Tela e cérebro no mesmo programa (JARVIS_UM_PROCESSO, app empacotado ou a volta automática para
        um programa só): aqui não dá para religar o cérebro. Diz em voz alta que NÃO trocou."""
        como = " (tire JARVIS_UM_PROCESSO do .env)" if os.environ.get("JARVIS_UM_PROCESSO", "").strip() else ""
        if destino != "gemma":
            self.ui.write_log("SYS: Modo normal NÃO ligado: com o Jarvis em um programa só, a troca pela voz não "
                              f"funciona{como}. Use o 'Voltar para o Gemini' e abra o Jarvis de novo.")
            self._falar_aviso("Não consegui voltar ao modo normal por aqui. Use o Voltar para o Gemini e abra "
                              "o Jarvis de novo.")
            return
        self.ui.write_log("SYS: 🔒 Modo privado NÃO ligado: com o Jarvis em um programa só, a troca pela voz não "
                          f"funciona{como}. Feche o Jarvis, rode o 'Instalar Gemma 4' e abra de novo.")
        self._falar_aviso("Atenção: o modo privado NÃO foi ligado; continuo usando a nuvem. Desliguei o microfone "
                          "por segurança: não fale dados de clientes agora.")
        mutar = getattr(self.ui, "set_muted_threadsafe", None)
        if callable(mutar):  # depois do aviso (a voz reserva não fala com o microfone desligado)
            mutar(True)

    def _checar_pedido_de_modo(self, fala: str) -> None:
        """Troca o modo pela frase falada, mesmo que a IA não chame a ferramenta."""
        from core.palavra_ativacao import modo_pedido

        portao = getattr(self, "_portao", None)
        modo = modo_pedido(fala)
        if modo and portao is not None and portao.modo != modo:
            self._definir_modo_escuta(modo)

    def _mostrar_volume(self, pcm: bytes) -> None:
        """Jarvis Ultron: manda o volume da voz para a esfera pulsar enquanto ele fala."""
        definir = getattr(self.ui, "set_voice_level", None)
        if callable(definir):
            from core.efeito_ultron import nivel_da_voz
            definir(nivel_da_voz(pcm))

    def _falar_com_voz_externa(self, texto: str) -> None:
        """Jarvis Ultron: com ElevenLabs/OpenAI/Edge escolhida, fala a resposta por ela."""
        motor = getattr(self, "_tts_engine", None)
        if motor is None or self._ext_tts_provider in ("", "gemini") or not self._pode_falar_agora():
            return
        motor.on_speaking_start = lambda: self.set_speaking(True)
        motor.on_speaking_stop = lambda: self.set_speaking(False)
        motor.on_level = self._mostrar_volume
        # Até ela terminar, o áudio do microfone não conta como ele ter voltado a falar: senão o som do
        # ambiente enquanto ela sintetiza fazia o resto atrasado do pedido (", pode fazer", chegando
        # durante o preço) virar uma fala nova depois da proposta (_microfone_mandou_audio).
        with self._trava_da_fala():
            self._voz_externa_pendente = getattr(self, "_voz_externa_pendente", 0) + 1

        def falar():
            try:
                if not motor.speak_sync(texto):
                    # ElevenLabs/OpenAI recusou (créditos, chave, internet): fala pela voz reserva
                    print("[Voz] A voz escolhida falhou; usando a voz normal.")
                    self._falar_reserva(texto)
            except Exception as erro:
                print(f"[Voz] A voz escolhida falhou ({erro}); usando a voz normal.")
                self._falar_reserva(texto)
            finally:
                with self._trava_da_fala():
                    self._voz_externa_pendente = max(0, getattr(self, "_voz_externa_pendente", 1) - 1)

        threading.Thread(target=falar, daemon=True, name="VozExterna").start()

    # ---------- Jarvis Ultron: modo reserva (Groq) ----------

    def _ativar_modo_reserva(self) -> None:
        if self._modo_reserva:
            return
        from core.cerebro_gemma import CerebroGemma

        if isinstance(getattr(self, "_reserva", None), CerebroGemma):
            self._ligar_cerebro_gemma()
            return
        self._modo_reserva = True
        com_ferramentas = not getattr(self, "cloud_safe", False)
        self.ui.write_log(f"SYS: Gemini indisponível. Modo reserva ({getattr(self._reserva, 'nome', 'Groq')}) ligado: "
                          + ("converso e executo as tarefas." if com_ferramentas else "converso, mas sem ferramentas."))
        threading.Thread(target=self._escutar_reserva, daemon=True).start()
        aviso = ("A conexão principal caiu. Estou no modo reserva, mas continuo executando suas tarefas."
                 if com_ferramentas else
                 "A conexão principal caiu. Estou no modo reserva: posso conversar, mas sem as ferramentas até ela voltar.")
        threading.Thread(target=self._falar_reserva, daemon=True, args=(aviso,)).start()

    def _ligar_cerebro_gemma(self) -> None:
        """Jarvis Ultron: o Gemma 4 do PC é o cérebro. Aquece o modelo e já começa a ouvir."""
        self._modo_reserva = True
        self.ui.write_log("SYS: Cérebro: Gemma 4 no seu PC. Preparando (a primeira vez pode levar 1 minuto)...")

        def preparar():
            ferramentas, _ = self._ferramentas_da_reserva()
            pronto = self._reserva.aquecer(ferramentas)
            if pronto:
                self.ui.write_log("SYS: Gemma 4 pronto. Converso e executo as tarefas.")
                self._falar_reserva("Jarvis online. Estou rodando no Gemma 4, no seu computador.")
            else:
                self.ui.write_log("SYS: O Gemma 4 não respondeu. Confira se o Ollama está instalado "
                                  "(rode o 'Instalar Gemma 4').")
                self._falar_reserva("Não consegui ligar o Gemma. Rode o Instalar Gemma 4 na pasta do Jarvis.")
            checar = getattr(self._reserva, "checar_ouvido", None)
            if callable(checar) and not checar():  # sem o Whisper local: avisa já na abertura
                self._avisar_sem_ouvido()

        threading.Thread(target=preparar, daemon=True, name="GemmaAquecer").start()
        threading.Thread(target=self._escutar_reserva, daemon=True).start()

    def _desativar_modo_reserva(self) -> None:
        self._modo_reserva = False
        self.ui.write_log("SYS: Conexão principal de volta. Modo reserva desligado.")

    def _responder_pela_reserva(self, texto: str) -> None:
        ferramentas, executar = self._ferramentas_da_reserva()
        resposta = self._reserva.responder(texto, ferramentas=ferramentas, executar=executar)
        self.ui.write_log(f"Jarvis: {resposta}")
        self._falar_reserva(resposta)

    def _avisar_sem_ouvido(self) -> None:
        """Modo privado sem a transcrição local da voz: avisa uma vez (tela e voz) por motivo.
        A voz nunca vai para a nuvem; dá para digitar."""
        erro = getattr(getattr(self, "_reserva", None), "erro_ouvido", None)
        if not erro or erro == getattr(self, "_erro_ouvido_avisado", None):
            return
        self._erro_ouvido_avisado = erro
        self.ui.write_log(f"SYS: 🔒 {erro}")
        self._falar_reserva(erro)

    # Ferramentas essenciais no modo reserva. Mandar TODAS ao Groq gasta muito do limite grátis, então
    # só as mais usadas por voz vão para a reserva (as automações da pasta entram sempre).
    RESERVA_FERRAMENTAS_ESSENCIAIS = {
        "open_app", "browser_control", "weather_report", "reminder", "media_control", "youtube_video",
        "web_search", "email_control", "hermes_agent", "school_tasks",
        "self_diagnosis", "save_memory", "generate_image", "listening_mode",
    }

    def _ferramentas_da_reserva(self):
        """Ferramentas do Jarvis no formato do Groq + a função que as executa (modo reserva).
        No modo nuvem (cloud_safe) a reserva fica só na conversa, sem ferramentas.
        JARVIS_RESERVA_FERRAMENTAS=0 no .env desliga as ferramentas (fica só conversa, mais leve).
        No modo privado (Gemma) só vão as que não usam IA na nuvem, e sem gravar memória."""
        if getattr(self, "cloud_safe", False):
            return None, None
        if os.environ.get("JARVIS_RESERVA_FERRAMENTAS", "1").strip() in ("0", "nao", "não", "false"):
            return None, None
        if getattr(self, "_reserva_ferramentas", None) is None:
            from core.cerebro_gemma import cerebro_gemma
            from core.reserva_groq import gemini_para_groq
            plugins = set(carregar_automacoes().ferramentas)  # as automações da pasta entram sempre
            escolhidas = [d for d in get_tool_declarations()
                          if d.get("name") in self.RESERVA_FERRAMENTAS_ESSENCIAIS or d.get("name") in plugins]
            if cerebro_gemma():
                # a memória de longo prazo vai no prompt do Gemini depois, no modo normal
                escolhidas = [d for d in escolhidas if d.get("name") != "save_memory"
                              and bloqueio_do_modo_privado(d.get("name", "")) is None]
            self._reserva_ferramentas = gemini_para_groq(escolhidas)
        return self._reserva_ferramentas, self._executar_ferramenta_reserva

    def _garantir_loop_reserva(self):
        """Um event loop que fica SEMPRE rodando num fio próprio, para o modo reserva. Assim as
        tarefas longas (Hermes em segundo plano) terminam e entregam o resultado depois, em vez de
        ficarem paradas (antes o loop só vivia durante uma chamada)."""
        laco = getattr(self, "_loop_reserva", None)
        if laco is not None and not laco.is_closed():
            return laco
        laco = asyncio.new_event_loop()
        self._loop_reserva = laco
        threading.Thread(target=laco.run_forever, daemon=True, name="LoopReserva").start()
        return laco

    def rodar_automacao_ultron(self, nome: str, args: dict | None = None) -> None:
        """Painel Ultron: roda uma automação DIRETO (sem passar pela IA) e fala/mostra o resultado.
        Funciona mesmo sem Gemini/Groq, porque chama a ferramenta na hora."""
        def trabalhar():
            self.ui.write_log(f"SYS: ⚙ Ultron: {nome}...")
            try:
                if nome == "self_diagnosis":
                    # o relatório inteiro já vai para a tela (linhas SYS) e para Documentos;
                    # a voz diz só o resumo curto (antes lia o relatório todo e a instrução em inglês)
                    bruto = self._autodiagnostico(falar=False, so_resumo=True)
                else:
                    bruto = self._executar_ferramenta_reserva(nome, dict(args or {}))
            except Exception as erro:
                bruto = f"Não consegui rodar {nome}: {str(erro)[:150]}"
            texto = _limpar_para_falar(bruto)
            self.ui.write_log(f"Jarvis: {texto}")
            self._falar_resultado_ultron(texto)
        threading.Thread(target=trabalhar, daemon=True, name=f"Ultron-{nome}").start()

    def _falar_resultado_ultron(self, texto: str) -> None:
        """Fala o resultado pela voz que estiver disponível (Gemini ao vivo ou reserva)."""
        if not texto:
            return
        session, loop = getattr(self, "session", None), getattr(self, "_loop", None)
        if session is not None and loop is not None and not getattr(self, "_modo_reserva", False) \
                and not self._chamada_fechada():
            directiva = (f"[Resultado de automação] {texto}\nLeia isso ao usuário em português, "
                         "sem acrescentar nada. Não chame ferramentas.")
            # o resultado já está escrito no canal: a leitura do Gemini não entra de novo (ficava duplicado)
            with self._trava_da_fala():
                self._leituras_sem_registro = getattr(self, "_leituras_sem_registro", 0) + 1
                self._leituras_sem_registro_ate = time.monotonic() + 30  # se o Gemini não ler, expira
            asyncio.run_coroutine_threadsafe(
                session.send_client_content(turns={"parts": [{"text": directiva}]}, turn_complete=True), loop)
        else:
            self._falar_reserva(texto)

    def _executar_ferramenta_reserva(self, nome: str, args: dict) -> str:
        """Roda uma ferramenta do Jarvis (a mesma _execute_tool do Gemini) e devolve só o texto."""
        laco = self._garantir_loop_reserva()
        chamada = SimpleNamespace(name=nome, args=dict(args or {}), id="reserva")
        try:
            futuro = asyncio.run_coroutine_threadsafe(self._execute_tool(chamada), laco)
            resposta = futuro.result(timeout=self.HERMES_ESPERA + 30)
        except Exception as erro:
            return f"A ferramenta {nome} falhou: {str(erro)[:150]}"
        dados = getattr(resposta, "response", None) or {}
        return str(dados.get("result", "")) if isinstance(dados, dict) else str(dados)

    def _falar_reserva(self, texto: str) -> None:
        from actions.tts_engine import TTSEngine

        if os.environ.get("JARVIS_VOZ_PRIVADA", "").strip() in ("1", "sim", "true"):
            # Jarvis Ultron: voz do próprio Windows; o texto da resposta não sai do PC.
            self._falar_no_pc(texto, esperar=False)
            return
        motor = TTSEngine(
            provider="edge",
            voice_id=os.environ.get("JARVIS_VOZ_RESERVA", "pt-BR-AntonioNeural"),
            on_speaking_start=lambda: self.set_speaking(True),
            on_speaking_stop=lambda: self.set_speaking(False),
        )
        motor.on_level = self._mostrar_volume
        if motor.speak_sync(texto):
            return
        # Jarvis Ultron: a voz da internet (Microsoft Edge) falhou; usa a voz que vem no Windows.
        print("[Reserva] Voz da internet falhou; usando a voz do Windows.")
        self._falar_no_pc(texto, esperar=False)

    def _escutar_reserva(self) -> None:
        """No modo reserva: ouve (depois do "Hey Jarvis"), transcreve e responde pelo Groq."""
        from core.reserva_groq import capturar_falas

        try:
            for pcm in capturar_falas(
                continuar=lambda: self._modo_reserva and not self._shutdown_requested.is_set(),
                pode_ouvir=lambda: (not self._is_speaking and not self.ui.muted
                                    and not getattr(self, "_trocando_cerebro", False)),
                portao=self._portao,
            ):
                texto = self._reserva.transcrever(pcm)
                if texto:
                    self.ui.write_log(f"You: {texto}")
                    # o "ok" das aprovações é conferido nesta fala (e não numa antiga do Gemini)
                    self._current_input_transcript = self._last_input_transcript = texto
                    self._last_input_transcript_at = time.monotonic()
                    self._nova_fala(texto)
                    self._checar_pedido_de_modo(texto)
                    if self._pedido_de_cerebro(texto):
                        continue
                    self._portao.estender()
                    if self._pedido_de_ultron(texto):  # "modo Ultron" abre o painel, sem ir para a IA
                        continue
                    from core.autodiagnostico import pediu_diagnostico
                    if pediu_diagnostico(texto):
                        self._autodiagnostico()
                        continue
                    self._responder_pela_reserva(texto)
                else:
                    self._avisar_sem_ouvido()  # modo privado sem o Whisper local: avisa uma vez
        except Exception as erro:
            print(f"[Reserva] Microfone do modo reserva parou: {erro}")

    def _suspender(self, minutos) -> str:
        """Jarvis Ultron: silencia o microfone por alguns minutos e volta sozinho."""
        try:
            minutos = max(1, min(int(round(float(minutos))), 240))
        except (TypeError, ValueError):
            minutos = 10
        anterior = getattr(self, "_suspensao", None)
        if anterior is not None:
            anterior.cancel()
        self.ui.set_muted_threadsafe(True)
        loop = asyncio.get_running_loop()
        self._suspensao = loop.call_later(
            minutos * 60, lambda: asyncio.ensure_future(self._voltar_da_suspensao()))
        self.ui.write_log(f"SYS: Jarvis suspenso por {minutos} minuto(s).")
        return (f"Microphone muted for {minutos} minute(s). Tell the user, in one short sentence in "
                f"Portuguese, that you are suspended and will be back in {minutos} minute(s).")

    async def _voltar_da_suspensao(self):
        self._suspensao = None
        if not self.ui.muted:  # o usuário já religou o microfone antes do tempo
            return
        self.ui.set_muted_threadsafe(False)
        self.ui.write_log("SYS: Fim da suspensão. Microfone ativo.")
        try:
            await self.session.send_client_content(
                turns={"parts": [{"text": "(A suspensão terminou. Diga ao usuário, em uma frase curta "
                                          "em português, que você está de volta.)"}]},
                turn_complete=True,
            )
        except Exception as erro:
            print(f"[JARVIS] Aviso de volta da suspensão falhou: {erro}")

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        if getattr(self, "cloud_safe", False) and name not in CLOUD_SAFE_ACTIONS:
            return types.FunctionResponse(
                id=fc.id,
                name=name,
                response={
                    "result": (
                        f"Tool '{name}' is unavailable in cloud-safe mode."
                    )
                },
            )

        # Jarvis Ultron: modo privado. Trava no código (não só no prompt do Gemma): vale também para o
        # painel Ultron e para chamadas que o modelo inventar. No modo nuvem (cloud_safe) a conversa já é
        # o Gemini e o Gemma não é usado (igual ao __init__), então não há modo privado para travar.
        bloqueio = None if getattr(self, "cloud_safe", False) else bloqueio_do_modo_privado(name, args)
        if bloqueio is not None:
            self.ui.write_log(f"SYS: 🔒 {name} não é usado no modo privado (usa IA na nuvem).")
            return types.FunctionResponse(id=fc.id, name=name, response={"result": bloqueio})

        if getattr(self.ui, "operational_ready", True) is False:
            return types.FunctionResponse(
                id=fc.id,
                name=name,
                response={"result": "Startup sequence active. Try this action again when JARVIS is ready."},
            )

        from core.qa_mode import guard_tool_call, qa_block_message

        qa_decision = guard_tool_call(name, args)
        if not qa_decision.allowed:
            return types.FunctionResponse(
                id=fc.id,
                name=name,
                response={"result": qa_block_message(qa_decision)},
            )

        print(f"[JARVIS] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")

        intercepted = self._intercept_ui_tool_call(name, args)
        if intercepted is not None:
            return types.FunctionResponse(
                id=fc.id, name=name, response={"result": intercepted}
            )

        if name == "save_memory":
            from core.cerebro_gemma import cerebro_gemma

            if cerebro_gemma():
                # modo privado: não grava (a memória de longo prazo vai no prompt do Gemini depois)
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
                return types.FunctionResponse(
                    id=fc.id, name=name,
                    response={"result": "Memória não é gravada no modo privado.", "silent": True}
                )
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        result = "Done."

        try:
            if name == "open_app":
                r = await asyncio.to_thread(lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Opened {args.get('app_name')}."

            elif name == "listening_mode":
                result = self._definir_modo_escuta(args.get("mode", ""))

            elif name == "hermes_agent":
                result = await self._hermes_sem_travar(args.get("request", ""))

            elif name == "school_tasks":
                result = await self._geekie_pendencias(bool(args.get("refresh", False)))

            elif name == "self_diagnosis":
                result = await asyncio.to_thread(self._autodiagnostico, False)

            elif name == "approve_publication":
                from core import hermes_ponte
                # o "ok" é conferido no código: numa fala NOVA do Erton depois da proposta (core/aprovacao.py)
                result = await asyncio.to_thread(
                    hermes_ponte.aprovar_e_executar,
                    args.get("kind", ""), args.get("details", ""), self, bool(args.get("confirm")),
                )

            elif name == "suspend_listening":
                result = self._suspender(args.get("minutes", 10))

            elif name == "generate_image":
                from core.modelos import gerar_imagem
                result = await asyncio.to_thread(gerar_imagem, args.get("prompt", ""))

            elif name == "weather_report":
                r = await asyncio.to_thread(lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = await asyncio.to_thread(lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_controller":
                if (
                    args.get("action", "").lower() == "open"
                    and not args.get("path")
                    and not args.get("name")
                ):
                    current_file = getattr(self.ui, "current_file", None)
                    if current_file:
                        args["path"] = current_file
                r = await asyncio.to_thread(lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name in FERRAMENTAS_DESLIGADAS:
                # desligada de propósito (Etapa 3): responde e não chama nada
                self.ui.write_log(f"SYS: ⛔ {name} está desligada no Jarvis.")
                result = resposta_de_desligada(name)

            elif name == "email_control":
                if args.get("action", "").lower() == "connect" and not args.get("credentials_path"):
                    current_file = getattr(self.ui, "current_file", None)
                    if current_file and Path(str(current_file)).suffix.lower() == ".json":
                        args["credentials_path"] = current_file
                r = await asyncio.to_thread(lambda: email_control(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or "Email action completed."

            elif name == "reminder":
                r = await asyncio.to_thread(lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await asyncio.to_thread(lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "media_control":
                r = await asyncio.to_thread(lambda: media_control(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "screen_process":
                threading.Thread(
                    target=screen_process,
                    kwargs={"parameters": args, "response": None,
                            "player": self.ui, "session_memory": None,
                            "speak": self._speak_vision_result},
                    daemon=True
                ).start()
                result = "Vision module activated. Stay completely silent — vision module will speak directly."

            elif name == "computer_settings":
                # desligar, reiniciar, digitar e apertar teclas só com o "ok" do Erton, conferido na ação
                # (core/aprovacao.py)
                r = await asyncio.to_thread(lambda: computer_settings(parameters=args, response=None, player=self.ui,
                                                                      jarvis=self))
                result = r or "Done."

            elif name == "desktop_control":
                r = await asyncio.to_thread(lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "web_search":
                r = await asyncio.to_thread(lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."
            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await asyncio.to_thread(
                    lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "flight_finder":
                r = await asyncio.to_thread(lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "graphics_quality":
                quality = str(args.get("quality") or "").strip().lower()
                if quality not in {"low", "medium", "high"}:
                    raise ValueError("Graphics quality must be low, medium, or high.")
                self.ui.set_graphics_quality(quality)
                result = f"JARVIS graphics quality changed to {quality}."

            elif name == "jarvis_ui_control":
                action = str(args.get("action") or "").strip().lower()
                if action == "change_theme":
                    theme = str(args.get("theme") or "").strip().lower()
                    allowed = {"arc_reactor", "stealth_red", "vibranium_purple", "nanotech_gold", "platinum"}
                    if theme not in allowed:
                        raise ValueError(f"Unknown JARVIS theme: {theme or 'missing'}")
                    self.ui.set_theme(theme)
                    result = f"JARVIS theme changed to {theme.replace('_', ' ')}."
                elif action == "change_graphics_quality":
                    quality = str(args.get("graphics_quality") or "").strip().lower()
                    if quality not in {"low", "medium", "high"}:
                        raise ValueError(f"Unknown graphics quality: {quality or 'missing'}")
                    self.ui.set_graphics_quality(quality)
                    result = f"JARVIS graphics quality changed to {quality}."
                else:
                    self.ui.handle_ui_command(action)
                    result = f"JARVIS interface action completed: {action.replace('_', ' ')}."

            elif name == "deep_research":
                r = request_deep_research(parameters=args, player=self.ui, speak=self.speak)
                result = r or "Deep research preference requested."

            elif name == "create_presentation":
                current_file = getattr(self.ui, "current_file", None)
                supported_sources = {
                    ".txt", ".md", ".rst", ".csv", ".json", ".jsonl", ".docx", ".pptx",
                    ".pdf", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".webp",
                    ".wav", ".mp3", ".m4a", ".mp4", ".mov", ".avi", ".webm",
                }
                if (
                    not args.get("source_file")
                    and not args.get("source_files")
                    and current_file
                    and Path(str(current_file)).suffix.lower() in supported_sources
                ):
                    args["source_files"] = [current_file]
                r = request_presentation(parameters=args, player=self.ui, speak=self.speak)
                result = r or "Presentation preference requested."

            elif name == "task_status":
                from agent.task_queue import get_queue

                queue = get_queue()
                action = str(args.get("action") or "get").lower()
                task_id = str(args.get("task_id") or "").strip()
                if action == "all" or not task_id:
                    result = json.dumps(queue.get_all_statuses(), ensure_ascii=False)
                elif action == "cancel":
                    result = f"Task {task_id} cancelled." if queue.cancel(task_id) else f"Task {task_id} could not be cancelled."
                else:
                    status = queue.get_status(task_id)
                    result = json.dumps(status, ensure_ascii=False) if status else f"Task {task_id} was not found."

            elif name in carregar_automacoes().ferramentas:
                automacao = carregar_automacoes().ferramentas[name]
                result = str(await asyncio.to_thread(automacao.executar, args, self))

            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _execute_tool_batch(self, calls):
        """Run read-only calls concurrently while preserving mutation order."""
        mutating = {
            "send_message", "prepare_message_reply", "email_control", "reminder",
            "computer_settings", "computer_control", "desktop_control", "file_controller",
            "file_processor", "code_helper", "dev_agent", "game_updater",
            "create_presentation", "save_memory", "jarvis_ui_control", "graphics_quality",
        }
        call_list = list(calls or [])
        if any(getattr(call, "name", "") in mutating for call in call_list):
            return [await self._execute_tool(call) for call in call_list]
        return list(await asyncio.gather(*(self._execute_tool(call) for call in call_list)))

    async def _send_realtime(self):
        while True:
            if self._shutdown_requested.is_set():
                return
            msg = await self.out_queue.get()
            if msg is None or self._shutdown_requested.is_set():
                return
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                jarvis_speaking = self._is_speaking
            # indo para o modo privado: o microfone já para de ir para o Gemini
            if not jarvis_speaking and not self.ui.muted and not getattr(self, "_trocando_cerebro", False):
                data = self._portao.processar(indata)
                if data:
                    loop.call_soon_threadsafe(
                        self.out_queue.put_nowait,
                        {"data": data, "mime_type": "audio/pcm"}
                    )
                    self._microfone_mandou_audio()

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
                latency=_latencia_audio(),
            ):
                print("[JARVIS] 🎤 Mic stream open")
                while not self._shutdown_requested.is_set():
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[JARVIS] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv started")
        from core.aprovacao import fechar_fala, mais_um_pedaco, marca

        out_buf, in_buf = [], []
        _new_turn = True
        turn_had_audio = False
        # Jarvis Ultron: contagem das falas do Erton para o "ok" das aprovações (core/aprovacao.py)
        ferramenta_no_turno = False  # já rodou ferramenta neste turno do modelo
        fala_do_buf = None  # número da fala que está em in_buf (None: não contou como fala nova)
        resto_atrasado, texto_antes = False, ""  # in_buf é o resto atrasado da fala anterior (e o texto dela)

        try:
            while True:
                if self._shutdown_requested.is_set():
                    return
                async for response in self.session.receive():

                    response_audio = _live_response_audio_bytes(response)
                    if response_audio:
                        # Jarvis Ultron: quanto tempo levou da sua fala até a voz dele começar
                        falou_em = getattr(self, "_ultima_fala_em", None)
                        if falou_em is not None and not turn_had_audio:
                            print(f"[Tempo] Resposta começou {time.monotonic() - falou_em:.1f}s depois da sua fala")
                            self._ultima_fala_em = None
                        turn_had_audio = True
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        self.audio_in_queue.put_nowait(response_audio)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)
                                self._interrupted_text = " ".join(out_buf)
                                if not self.ui.muted:
                                    if _new_turn:
                                        self.ui.clear_subtitle()
                                        _new_turn = False
                                    self.ui.show_subtitle(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            self._portao.estender()
                            self._ultima_fala_em = time.monotonic()
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                # o microfone fica fechado enquanto o Jarvis fala: sem áudio mandado
                                # depois do fim do último turno dele, isto não pode ser uma fala nova
                                ouviu = getattr(self, "_ouviu_depois_do_turno", True)
                                if in_buf and resto_atrasado and ouviu:
                                    # depois do resto atrasado ele voltou a falar: isto já é fala nova
                                    self.ui.write_log(f"You: {self._current_input_transcript}")
                                    in_buf = []
                                fala_nova = not in_buf
                                if fala_nova:
                                    self._current_input_transcript = ""
                                in_buf.append(txt)
                                self._current_input_transcript = " ".join(in_buf).strip()
                                if fala_nova and not ferramenta_no_turno and ouviu:
                                    fala_do_buf = self._nova_fala(self._current_input_transcript, em_pedacos=True)
                                    resto_atrasado, texto_antes = False, ""
                                else:
                                    # Transcrição que chega DEPOIS de uma ferramenta, no mesmo turno do
                                    # modelo, é o pedido chegando atrasado (ou ele falando por cima): não
                                    # conta como fala nova, senão um "pode fazer" dito junto com o pedido
                                    # aprovaria o vídeo antes de ele ouvir o preço. O resto de uma fala
                                    # ("Ok," ... "pode cancelar") faz o texto dela crescer: a aprovação
                                    # confere de novo com a fala inteira (aprovacao.ainda_aprovado).
                                    if fala_nova:
                                        fala_do_buf, resto_atrasado, texto_antes = None, False, ""
                                        if not ferramenta_no_turno and getattr(self, "_fala_em_pedacos", False):
                                            # Chegou depois do fim do turno sem o microfone ter mandado
                                            # nada desde então: é o resto atrasado da última fala (ex.: o
                                            # ", pode fazer" do pedido, chegando durante o preço). Ela cresce;
                                            # não vira uma fala nova depois da proposta.
                                            fala_do_buf, resto_atrasado = marca(self), True
                                            texto_antes = self._fala_texto
                                    mais_um_pedaco(self, fala_do_buf,
                                                   f"{texto_antes} {self._current_input_transcript}".strip())
                                if (
                                    not getattr(self, "_pending_self_quit", False)
                                    and self._is_explicit_self_quit_transcript(self._current_input_transcript)
                                ):
                                    self._queue_self_quit_after_farewell()

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self._checar_pedido_de_modo(full_in)
                                if not self._pedido_de_cerebro(full_in):
                                    self._pedido_de_ultron(full_in)  # "modo Ultron" falado abre o painel
                                self._current_input_transcript = full_in
                                self._last_input_transcript = full_in
                                self._last_input_transcript_at = time.monotonic()
                                if (
                                    not getattr(self, "_pending_self_quit", False)
                                    and self._is_explicit_self_quit_transcript(full_in)
                                ):
                                    self._queue_self_quit_after_farewell()
                                self.ui.write_log(f"You: {full_in}")
                            in_buf = []
                            fechar_fala(self, fala_do_buf)  # o que chegar depois já é outra fala
                            fala_do_buf, resto_atrasado, texto_antes = None, False, ""
                            ferramenta_no_turno = False

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                with self._trava_da_fala():
                                    if time.monotonic() > getattr(self, "_leituras_sem_registro_ate", 0.0):
                                        self._leituras_sem_registro = 0
                                    ja_escrito = getattr(self, "_leituras_sem_registro", 0) > 0
                                    if ja_escrito:  # leitura de um resultado do Ultron já mostrado
                                        self._leituras_sem_registro -= 1
                                if not ja_escrito:
                                    self.ui.write_log(f"Jarvis: {full_out}")
                                self._falar_com_voz_externa(full_out)
                            # fala nova, agora, só com áudio do microfone mandado depois deste turno (e
                            # da voz externa, se ela vai falar a resposta)
                            self._ouviu_depois_do_turno = False
                            if (
                                getattr(self, "_pending_self_quit", False)
                                and (full_out or turn_had_audio)
                            ):
                                self._mark_self_quit_farewell_received()
                                
                            out_buf = []
                            turn_had_audio = False
                            _new_turn = True

                    if response.tool_call:
                        ferramenta_no_turno = True
                        function_calls = list(response.tool_call.function_calls)
                        for fc in function_calls:
                            print(f"[JARVIS] 📞 {fc.name}")
                        inicio_ferramenta = time.monotonic()
                        fn_responses = await self._execute_tool_batch(function_calls)
                        print(f"[Tempo] {', '.join(fc.name for fc in function_calls)} levou "
                              f"{time.monotonic() - inicio_ferramenta:.1f}s")
                        if getattr(self, "_ultima_fala_em", None) is not None:
                            self._ultima_fala_em = time.monotonic()  # conta a resposta a partir daqui
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
                    if self._shutdown_requested.is_set():
                        return
        except Exception as e:
            if isinstance(e, genai.errors.APIError) and "1000" in str(e):
                print("[JARVIS] 🔌 Session closed normally.")
                if self._shutdown_requested.is_set():
                    return
                # Jarvis Ultron: o Google encerrou a sessão (ou a voz foi trocada). Sem o erro, as outras
                # tarefas ficavam esperando o microfone (mudo, ou o modo chamada esperando o "Hey
                # Jarvis") e a sessão morta nunca era esquecida: nem religava, nem ia para a reserva.
                raise
            print(f"[JARVIS] ❌ Recv: {e}")
            traceback.print_exc()
            raise



    async def _play_audio(self):
        print("[JARVIS] 🔊 Play started")

        # Jarvis Ultron: voz metálica (desligue com JARVIS_EFEITO_ULTRON=0 no .env)
        from core.efeito_ultron import criar_efeito
        efeito_ultron = criar_efeito(RECEIVE_SAMPLE_RATE)

        stream = None
        if not self.external_audio:
            stream = sd.RawOutputStream(
                samplerate=RECEIVE_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                latency=_latencia_audio(),
            )
            stream.start()

        try:
            while True:
                if self._shutdown_requested.is_set():
                    return
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                        if self._complete_self_quit_after_audio():
                            return
                    continue
                # Jarvis Ultron: no modo chamada, esperando o "Hey Jarvis", ele não fala sozinho
                # (a não ser a resposta a um texto que o Erton digitou).
                if not self._pode_falar_agora():
                    continue
                # Skip Gemini audio when external TTS is active
                if self._tts_engine and self._ext_tts_provider and self._ext_tts_provider != "gemini":
                    pass  # drain silently
                else:
                    self.set_speaking(True)
                    if self.external_audio:
                        send_audio = getattr(self.client, "send_audio", None)
                        if callable(send_audio):
                            send_audio(chunk, f"audio/pcm;rate={RECEIVE_SAMPLE_RATE}")
                    elif stream is not None:
                        if efeito_ultron is not None:
                            chunk = efeito_ultron.processar(chunk)
                        self._mostrar_volume(chunk)
                        await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[JARVIS] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            if stream is not None:
                stream.stop()
                stream.close()

    @contextlib.asynccontextmanager
    async def _esquecer_sessao_ao_sair(self):
        """Jarvis Ultron: quando a conexão com o Gemini acaba (caiu ou fechou), esquece a sessão velha
        na hora. Sem isso, o texto digitado (até no modo reserva) e os avisos iam para a conexão morta e
        sumiam calados; sem sessão, vão para a reserva, ficam guardados até religar ou aparecem na tela."""
        try:
            yield
        finally:
            with self._trava_textos():
                self.session = None
                self.out_queue = None

    async def run(self):
        # Jarvis Ultron: cérebro Gemma 4 no PC. Não usa o Gemini: liga o cérebro local e fica de pé.
        # No modo nuvem (cloud_safe, o servidor web) o Gemma não é usado (igual ao __init__): vai ao Gemini.
        from core.cerebro_gemma import cerebro_gemma

        if not getattr(self, "cloud_safe", False) and cerebro_gemma():
            if self._reserva is not None:
                self._ativar_modo_reserva()
            else:
                # Modo privado sem o Gemma: NUNCA cai para o Gemini (a tela mostra MODO PRIVADO).
                # Fica parado até ele pedir o modo normal (digitado) ou fechar o Jarvis.
                aviso = ("Modo privado: não consegui ligar o Gemma 4, e não vou usar a nuvem. Rode o Instalar "
                         "Gemma 4 na pasta do Jarvis, ou digite 'modo normal' para voltar ao Gemini.")
                self.ui.write_log(f"ERR: 🔒 {aviso}")
                from actions.tts_engine import falar_com_voz_do_windows

                threading.Thread(target=falar_com_voz_do_windows, args=(aviso,), daemon=True,
                                 name="AvisoPrivado").start()
            while not self._shutdown_requested.is_set():
                await asyncio.sleep(0.5)
            return
        # Jarvis Ultron: aberto pela reserva (Google recusou a chave): conversa pelo Groq já, e
        # continua tentando o Gemini em segundo plano.
        if os.environ.get("JARVIS_SEM_GEMINI") == "1" and self._reserva is not None:
            self._ativar_modo_reserva()
        api_key = self._api_key or _get_api_key()
        from core.gemini_acesso import opcoes_http
        client = genai.Client(
            api_key=api_key,
            http_options=opcoes_http()
        )
        live_model = await asyncio.to_thread(pick_live_model, client, API_CONFIG_PATH)
        live_model_id = live_model.removeprefix("models/")
        from core import modelos as central_de_modelos

        while True:
            if self._shutdown_requested.is_set():
                return
            # enforce runtime limit if configured (contado desde a abertura da tela, não deste cérebro)
            if self.runtime_limit_seconds is not None:
                elapsed = time.time() - _inicio_do_teste()
                if elapsed >= float(self.runtime_limit_seconds):
                    self._encerrar_fim_do_teste()

            # enforce presence of required unlock path (e.g. mounted encrypted volume)
            if getattr(self, "required_unlock_path", None):
                try:
                    path = Path(self.required_unlock_path)
                    if not path.exists():
                        print(f"[JARVIS] 🔒 Required unlock path not present: {self.required_unlock_path}")
                        print("Please mount the locked container (see scripts/create_locked_dmg.sh).")
                        time.sleep(5)
                        continue
                    if self.required_unlock_secret is not None:
                        content = path.read_text(encoding="utf-8").strip()
                        if content != self.required_unlock_secret:
                            print("[JARVIS] 🔒 unlock.key content does not match expected secret.")
                            print("Please mount the locked container with the correct unlock.key file.")
                            time.sleep(5)
                            continue
                except Exception as e:
                    print(f"[JARVIS] 🔒 Locked path check error: {e}")
                    time.sleep(1)
                    continue
            # Jarvis Ultron: o modelo de voz que vai ser usado agora (3.x antes do 2.5; se um falhar,
            # a central passa para o próximo).
            modelo_voz = central_de_modelos.resolver(live_model_id)
            conectou = False
            try:
                print(f"[JARVIS] 🔌 Connecting ({modelo_voz})...")
                self.ui.write_log(f"SYS: Modelo de voz: {modelo_voz}")
                self.ui.set_state("THINKING")
                config = self._build_config(modelo_voz)

                async with (
                    client.aio.live.connect(model=live_model_id, config=config) as session,
                    self._esquecer_sessao_ao_sair(),
                    asyncio.TaskGroup() as tg,
                ):
                    self.session        = session
                    self._loop          = asyncio.get_event_loop()
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue      = asyncio.Queue(maxsize=10)
                    self._turn_done_event = asyncio.Event()
                    # Jarvis Ultron: o que foi digitado antes de conectar (_guardar_ate_conectar)
                    with self._trava_textos():
                        esperando, self._textos_esperando = self._textos_esperando, []
                    if esperando:
                        self._ja_cumprimentou = True  # o Erton já pediu algo: responde isso, sem saudação

                    print("[JARVIS] ✅ Connected.")
                    conectou = True
                    self._falhas_seguidas = 0
                    if self._modo_reserva:
                        self._desativar_modo_reserva()
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: JARVIS online.")
                    if not self.cloud_safe:
                        try:
                            jarvis_status.write_status({
                                "state": "online",
                                "voice": self._get_current_voice(),
                                "pid": os.getpid(),
                            })
                        except Exception:
                            pass

                    tg.create_task(self._send_realtime())
                    if not self.external_audio:
                        tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    tg.create_task(self._announce_startup())
                    if esperando:
                        tg.create_task(self._mandar_textos_esperando(esperando))

            except Exception as e:
                if self._shutdown_requested.is_set():
                    return
                actual = e
                if isinstance(e, ExceptionGroup) and len(e.exceptions) == 1:
                    actual = e.exceptions[0]

                actual = _erro_da_api(e) or actual  # Jarvis Ultron: acha o erro do Google dentro do grupo
                argumento_invalido = "1007" in str(actual) or "invalid argument" in str(actual).lower()
                if (self._idioma_voz() and isinstance(actual, genai.errors.APIError)
                        and ("language" in str(actual).lower() or argumento_invalido)):
                    # Jarvis Ultron: este modelo de voz não aceita escolher o idioma; segue só com a regra
                    print(f"[JARVIS] ⚠️ O modelo de voz não aceitou language_code ({str(actual)[:120]}); "
                          "seguindo sem ele.")
                    self._idioma_recusado = True
                elif argumento_invalido and not self._shutdown_requested.is_set():
                    # Jarvis Ultron: este modelo de voz recusou a configuração mesmo sem o idioma:
                    # deixa ele de lado e tenta o próximo modelo do Gemini.
                    central_de_modelos.pular(modelo_voz)
                    proximo = central_de_modelos.resolver(live_model_id)
                    self.ui.write_log(f"SYS: A voz {modelo_voz} recusou a configuração. Tentando {proximo}...")
                    print(f"[Modelos] Voz: {modelo_voz} recusou a configuração (1007); trocando para {proximo}.")
                    self._idioma_recusado = False  # o próximo modelo pode aceitar o idioma
                    await self._wait_before_reconnect(2)
                elif _is_unsupported_voice_error(actual) and self.voice_name != DEFAULT_VOICE_NAME:
                    old_voice = self.voice_name
                    self.voice_name = DEFAULT_VOICE_NAME
                    self.ui.write_log(
                        f"SYS: Voice '{old_voice}' not available. Falling back to {DEFAULT_VOICE_NAME}."
                    )
                    print(f"[JARVIS] ⚠️ Voice '{old_voice}' unsupported; falling back to {DEFAULT_VOICE_NAME}.")
                    self.ui.sync_voice_display(DEFAULT_VOICE_NAME)
                    if not self.cloud_safe:
                        try:
                            jarvis_status.write_status({"state": "voice_fallback", "voice": DEFAULT_VOICE_NAME})
                        except Exception:
                            pass
                elif isinstance(actual, genai.errors.APIError) and "1000" in str(actual):
                    print("[JARVIS] 🔌 Session ended normally.")
                    if not self.cloud_safe:
                        try:
                            jarvis_status.write_status({"state": "offline"})
                        except Exception:
                            pass
                    # Jarvis Ultron: religa logo, mas sem ficar em laço se o Google fechar toda sessão nova
                    await self._wait_before_reconnect(1)
                else:
                    print(f"[JARVIS] ⚠️ {e}")
                    traceback.print_exc()
                    # Jarvis Ultron: espera antes de tentar de novo (o original tentava sem parar)
                    self._falhas_seguidas += 1
                    if self._reserva is not None and self._falhas_seguidas >= 2:
                        self._ativar_modo_reserva()
                    proximo = modelo_voz
                    if not conectou or _modelo_indisponivel(actual):
                        # Este modelo não pegou: deixa ele de lado e tenta outro modelo do Gemini.
                        central_de_modelos.pular(modelo_voz)
                        proximo = central_de_modelos.resolver(live_model_id)
                    if proximo != modelo_voz:
                        self.ui.write_log(f"SYS: A voz {modelo_voz} não respondeu. Tentando {proximo}...")
                        print(f"[Modelos] Voz: {modelo_voz} falhou; trocando para {proximo}.")
                        await self._wait_before_reconnect(2)
                    else:
                        await self._wait_before_reconnect(min(60, 2 ** min(self._falhas_seguidas, 6)))

# Avisos que as ferramentas dão inteiros em inglês (são para a IA): o painel Ultron fala em português.
_AVISOS_EM_PORTUGUES = {
    "Hermes is still working": ("O Hermes ainda está trabalhando nisso; o resultado aparece na tela "
                                "quando ficar pronto."),
    "There is no Geekie list yet": ("Ainda não há lista do Geekie. O Hermes lê o Geekie One às 7h e às 18h; "
                                    "entre uma vez no Geekie One pelo navegador do Hermes."),
    # agentes do painel Ultron (rodam no Claude)
    "Claude is working on it": "O Claude está trabalhando nisso; eu aviso quando ficar pronto.",
    "Claude is still working on the previous task": ("O Claude ainda está terminando a tarefa anterior. "
                                                     "Tente de novo daqui a pouco."),
    "Private mode is on, so nothing is sent to Claude": ("No modo privado nada vai para o Claude. Diga "
                                                         "'modo normal' para usar os agentes."),
    "Claude Code is not installed": ("O Claude ainda não está instalado. Dê dois cliques em 'Instalar Claude' "
                                     "na pasta do Jarvis."),
}


def _limpar_para_falar(texto: str) -> str:
    """Tira as instruções em inglês que as ferramentas deixam para a IA (ex.: 'Tell the user...'),
    para o painel Ultron falar só a parte em português quando roda a automação direto."""
    texto = str(texto or "").strip()
    for inicio, frase in _AVISOS_EM_PORTUGUES.items():
        if texto.startswith(inicio):
            return frase
    marcas = ["Tell the user", "Explique ao usuário", "Explique isso", "Answer the user", "Answer in",
              "Confirm to the user", "Confirm in", "Say this to the user", "Oriente o usuário",
              "\nTell the user", "Then tell the user", "Summarize for the user"]
    corte = len(texto)
    for m in marcas:
        i = texto.find(m)
        if i != -1:
            corte = min(corte, i)
    return texto[:corte].strip() or texto


def _pensamento_da_voz(modelo: str) -> types.ThinkingConfig:
    """Gemini 3.x não aceita desligar o raciocínio (thinking_budget=0 dá erro 1007 "invalid argument"):
    usa o nível mais baixo, que responde rápido. O 2.5 continua sem raciocínio.
    JARVIS_PENSAMENTO no .env: low (padrão), medium ou high."""
    from core.modelos import _versao

    if _versao(str(modelo or "")) >= 3:
        nivel = os.environ.get("JARVIS_PENSAMENTO", "low").strip().upper()
        if nivel not in ("LOW", "MEDIUM", "HIGH"):
            nivel = "LOW"
        return types.ThinkingConfig(thinking_level=nivel)
    return types.ThinkingConfig(thinking_budget=0)


def _erro_da_api(erro: BaseException):
    """O primeiro erro do Google (APIError) dentro de um grupo de erros (TaskGroup), se houver."""
    if isinstance(erro, genai.errors.APIError):
        return erro
    for filho in getattr(erro, "exceptions", ()) or ():
        achado = _erro_da_api(filho)
        if achado is not None:
            return achado
    causa = erro.__cause__ or erro.__context__
    return _erro_da_api(causa) if isinstance(causa, BaseException) and causa is not erro else None


def _modelo_indisponivel(erro: Exception) -> bool:
    """Erro que é do modelo (aposentado, sem cota, não suporta voz ao vivo), não da internet."""
    texto = f"{type(erro).__name__} {erro}".lower()
    codigo = getattr(erro, "code", None) or getattr(erro, "status_code", None)
    return codigo in (404, 429) or any(p in texto for p in (
        "not found", "not supported", "is not supported", "resource_exhausted", "quota", "deprecated",
        "no longer available", "retired", "1008"))


def _contar_mudanca_desfeita(jarvis, espera: float = 8.0) -> None:
    """Jarvis Ultron: uma mudança do Claude no código ficou pela metade (o Jarvis fechou no meio)? Ela é
    desfeita na abertura (pelo "Iniciar Jarvis Ultron" ou pelo cérebro); aqui o Erton fica sabendo."""
    try:
        from core import claude_chefe

        aviso = claude_chefe.desfazer_interrompida()
    except Exception as erro:
        print(f"[Claude] Não consegui conferir a mudança interrompida: {erro}")
        return
    if not aviso:
        return

    def contar():
        time.sleep(espera)  # deixa a conversa abrir antes de falar
        jarvis.anunciar(aviso, "Claude")
        claude_chefe.esquecer_interrompida(aviso)  # só a anotação deste aviso

    threading.Thread(target=contar, daemon=True, name="ClaudeDesfeita").start()


def _inicio_do_teste() -> float:
    """Quando o tempo de teste (JARVIS_TRIAL_KEYWORD) começou. A tela marca JARVIS_TESTE_INICIO uma vez
    e todo cérebro que ela abre herda: trocar de modo ou o cérebro cair e religar não dá uma hora nova."""
    agora = time.time()
    try:
        inicio = float(os.environ.get("JARVIS_TESTE_INICIO", ""))
    except ValueError:
        inicio = 0.0
    if not (0 < inicio <= agora):  # vazio, estragado ou no futuro: conta de agora
        inicio = agora
        os.environ["JARVIS_TESTE_INICIO"] = repr(inicio)
    return inicio


def _vigiar_fim_do_teste(jarvis) -> None:
    """Fecha o Jarvis quando o tempo de teste acabar, qualquer que seja o cérebro (Gemini ao vivo
    numa conversa longa, Gemma no modo privado ou a reserva): run() só conferia ao reconectar o Gemini."""
    restante = float(jarvis.runtime_limit_seconds) - (time.time() - _inicio_do_teste())
    relogio = threading.Timer(max(0.0, restante), jarvis._encerrar_fim_do_teste)
    relogio.daemon = True
    relogio.name = "FimDoTeste"
    relogio.start()


def rodar_cerebro(ui):
    """O cérebro do Jarvis (voz, IA, ferramentas). Roda num fio da tela (um programa só) ou
    no programa próprio do cérebro, com a UIRemota no lugar da tela (veja core/ponte.py)."""
    ui.wait_for_api_key()
    voice_name = _load_voice_name()
    jarvis = JarvisLive(ui, voice_name)
    ui.on_quit_requested = jarvis.request_shutdown
    _contar_mudanca_desfeita(jarvis)

    # Trial/keyword runtime limiting: set via env `JARVIS_TRIAL_KEYWORD`.
    # If set to any non-empty string, jarvis will run for 3600 seconds (1 hour).
    trial_kw = os.environ.get("JARVIS_TRIAL_KEYWORD")
    if trial_kw:
        jarvis.runtime_limit_seconds = int(os.environ.get("JARVIS_RUNTIME_SECONDS", "3600"))
        jarvis.ui.write_log(f"SYS: Trial keyword detected. Running for {jarvis.runtime_limit_seconds} seconds.")
        _vigiar_fim_do_teste(jarvis)

    locked_secret = os.environ.get("JARVIS_LOCKED_KEY_SECRET")
    if locked_secret:
        jarvis.required_unlock_secret = locked_secret.strip()

    # Locked container check: if `JARVIS_LOCKED_VOLUME` is set, require
    # presence of `/Volumes/<name>/unlock.key` before full operation.
    locked_vol = os.environ.get("JARVIS_LOCKED_VOLUME")
    if locked_vol:
        mount_path = f"/Volumes/{locked_vol}/unlock.key"
        jarvis.required_unlock_path = mount_path
        jarvis.ui.write_log(f"SYS: Locked volume required: {mount_path}")
    ui.on_voice_change = jarvis.update_voice
    def _on_tts_change(provider, api_key, voice_id):
        if provider == "gemini":
            jarvis._tts_engine = None
            jarvis._ext_tts_provider = ""
            jarvis._ext_tts_voice_id = ""
            jarvis._ext_tts_api_key = ""
            jarvis.update_voice(voice_id)
        else:
            jarvis._ext_tts_provider = provider
            jarvis._ext_tts_voice_id = voice_id
            jarvis._ext_tts_api_key = api_key
            try:
                from actions.tts_engine import TTSEngine
                jarvis._tts_engine = TTSEngine(
                    provider=provider,
                    api_key=api_key,
                    voice_id=voice_id,
                )
                jarvis.ui.write_log(f"SYS: TTS engine ready: {provider} / {voice_id}")
                jarvis.ui.write_log("SYS: Gemini audio muted - using external TTS")
            except Exception as e:
                jarvis.ui.write_log(f"SYS: TTS engine error: {e}")
            # Restart session so new TTS takes effect
            if jarvis.session and jarvis._loop:
                try:
                    asyncio.run_coroutine_threadsafe(jarvis.session.close(), jarvis._loop)
                except Exception as e:
                    print(f"[JARVIS] Could not close session: {e}")
    ui.on_tts_provider_change = _on_tts_change
    chave_eleven = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if chave_eleven and os.environ.get("JARVIS_USAR_ELEVENLABS", "1").strip() != "0":
        _on_tts_change("elevenlabs", chave_eleven,
                       os.environ.get("JARVIS_VOZ_ELEVENLABS", "").strip() or "pNInz6obpgDQGcFmaJgB")
    ligar = getattr(ui, "ligar_jarvis", None)
    if callable(ligar):  # cérebro em programa próprio: manda o estado dele para os painéis da tela
        # Só agora, com a troca de voz/TTS já ligada: o que o usuário mudou na tela enquanto o
        # cérebro abria é entregue aqui (e vale por cima do padrão do ElevenLabs acima). Num programa
        # só, depois de o cérebro separado não abrir, a ponte da tela entrega aqui o que ficou guardado.
        ligar(jarvis)
    try:
        asyncio.run(jarvis.run())
    except KeyboardInterrupt:
        print("\n🔴 Shutting down...")
    except Exception as exc:
        message = f"Gemini startup failed: {str(exc)[:180]}"
        print(f"[JARVIS] ❌ {message}")
        try:
            ui.write_log(f"ERR: {message}")
            ui.set_state("LISTENING")
        except Exception:
            pass


def _automacoes_de_tela(jarvis_na_tela) -> None:
    """Modo separado: as automações que desenham na tela (painel Stark, painel Ultron) rodam aqui,
    no programa da tela; o cérebro roda as outras."""
    carga = carregar_automacoes()
    for arquivo, iniciar in carga.inicios:
        if arquivo not in carga.na_tela:
            continue
        try:
            iniciar(jarvis_na_tela)
        except Exception as erro:
            print(f"[Automações] {arquivo}: {erro}")


def main():
    import sys

    if "--self-test" in sys.argv[1:]:
        from scripts.self_test import main as self_test_main

        return self_test_main([argument for argument in sys.argv[1:] if argument != "--self-test"])

    from ui import JarvisUI

    running_as_app = getattr(sys, "frozen", False)

    if os.environ.get("JARVIS_CLI") != "1" and not running_as_app:
        print("[JARVIS] Please launch with the JARVIS CLI: jarvis")
        return
    # Jarvis Ultron: abre direto, sem palmas.
    print("[JARVIS] ⚡ Powering up the interface...")
    try:
        ui = JarvisUI("face.png")
    except Exception as exc:
        print(f"[JARVIS] ❌ Interface startup failed: {exc}")
        traceback.print_exc()
        return
    try:
        from core import na_tela

        na_tela.preparar()  # Jarvis Ultron: automações podem mexer na tela com segurança
    except Exception as exc:
        print(f"[Automações] Tela: {exc}")

    from core.ponte import PonteTela, modo_separado

    if os.environ.get("JARVIS_TRIAL_KEYWORD"):
        _inicio_do_teste()  # marca a abertura uma vez; os cérebros que a tela abrir herdam (JARVIS_*)

    def no_mesmo_programa():
        threading.Thread(target=rodar_cerebro, args=(ui,), daemon=True, name="Cerebro").start()

    if modo_separado():
        # Jarvis Ultron: tela e cérebro em programas separados; um nunca trava o outro.
        ponte = PonteTela(ui, ao_falhar=no_mesmo_programa,
                          ao_conectar=lambda: _automacoes_de_tela(ponte.jarvis))
        ui._app.aboutToQuit.connect(ponte.encerrar)
        ponte.iniciar()
    else:
        no_mesmo_programa()
    print("[JARVIS] ✅ Interface ready.")
    ui.root.mainloop()
    print("[JARVIS] Interface closed.")

def cli_main():
    """Canonical console entry point installed as the `jarvis` command."""
    os.environ["JARVIS_CLI"] = "1"
    return main()


if __name__ == "__main__":
    raise SystemExit(main() or 0)
