import asyncio
import os
import re
import threading
import json
import sys
import traceback
from pathlib import Path

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
send_message = _lazy_action("actions.send_message", "send_message")
prepare_message_reply = _lazy_action("actions.send_message", "prepare_message_reply")
email_control = _lazy_action("actions.email_control", "email_control")
check_messages = _lazy_action("actions.message_monitor", "check_messages")
reminder = _lazy_action("actions.reminder", "reminder")
computer_settings = _lazy_action("actions.computer_settings", "computer_settings")
screen_process = _lazy_action("actions.screen_processor", "screen_process")
youtube_video = _lazy_action("actions.youtube_video", "youtube_video")
media_control = _lazy_action("actions.media_control", "media_control")
desktop_control = _lazy_action("actions.desktop", "desktop_control")
browser_control = _lazy_action("actions.browser_control", "browser_control")
file_controller = _lazy_action("actions.file_controller", "file_controller")
code_helper = _lazy_action("actions.code_helper", "code_helper")
dev_agent = _lazy_action("actions.dev_agent", "dev_agent")
web_search_action = _lazy_action("actions.web_search", "web_search")
computer_control = _lazy_action("actions.computer_control", "computer_control")
game_updater = _lazy_action("actions.game_updater", "game_updater")
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
    # "João Pessoa"); o Bloco de Notas grava em UTF-8. Aceita os dois em vez de travar na abertura.
    import io

    try:
        bruto = (BASE_DIR / ".env").read_bytes()
    except OSError:
        return
    for codificacao in ("utf-8-sig", "cp850", "cp1252"):
        try:
            texto = bruto.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    else:
        texto = bruto.decode("utf-8", errors="replace")
    load_dotenv(stream=io.StringIO(texto))


BASE_DIR        = get_base_dir()
_load_dotenv()

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
            "by itself, and long multi-step tasks. Examples: 'what are today's posts?', 'how are my ads "
            "doing?', 'prepare 3 posts about my training'. Never use it to publish without approval."
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
            "Records the user's explicit approval and tells Hermes to publish/schedule the approved posts "
            "(kind='redes') or apply the approved ad change (kind='anuncios'). Call ONLY right after the user "
            "clearly approves in their own words (e.g. 'ok, pode publicar os posts 1 e 3'). Never assume approval."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "kind": {"type": "STRING", "enum": ["redes", "anuncios"], "description": "redes = posts; anuncios = Meta ads"},
                "details": {"type": "STRING", "description": "Exactly what was approved, e.g. 'posts 1 e 3, agendar no horario sugerido'"}
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
        "name": "check_messages",
        "description": (
            "Reads the current Instagram or Apple Messages conversation and optionally searches Contacts. "
            "Use this before drafting a reply or when the user asks about recent messages."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "platform": {"type": "STRING", "description": "all | Instagram | iMessage | Contacts. Default: all."},
                "include_contacts": {"type": "BOOLEAN", "description": "Also search the user's Contacts."},
                "contact_query": {"type": "STRING", "description": "Optional spoken contact name to match."},
                "max_messages": {"type": "INTEGER", "description": "Maximum current-chat lines to inspect. Default: 30."}
            },
            "required": []
        }
    },
    {
        "name": "prepare_message_reply",
        "description": (
            "Creates an approval-gated message draft, approves the current pending draft, or cancels it. "
            "Never approve unless the user explicitly confirms the exact pending draft."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "enum": ["prepare", "approve", "cancel"], "description": "Draft lifecycle action."},
                "platform": {"type": "STRING", "description": "Instagram, iMessage, WhatsApp, Telegram, or another supported platform."},
                "receiver": {"type": "STRING", "description": "Recipient name. Optional for the currently open chat."},
                "message_text": {"type": "STRING", "description": "Exact draft text, required for prepare."}
            },
            "required": ["action"]
        }
    },
    {
        "name": "send_message",
        "description": (
            "Sends a user-authored message through iMessage, WhatsApp, Telegram, Instagram, Discord, or the current chat. "
            "For Instagram, the first call prepares a visible draft; use action=approve only after explicit user confirmation."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":       {"type": "STRING", "enum": ["send", "approve", "cancel"], "description": "Default: send. Approve/cancel operates on the pending draft."},
                "receiver":     {"type": "STRING", "description": "Recipient contact name. Optional for current/focused chats and approval actions."},
                "message_text": {"type": "STRING", "description": "Exact message content. Required for send."},
                "platform":     {"type": "STRING", "description": "iMessage, WhatsApp, Telegram, Instagram, Discord, or current/focused."}
            },
            "required": ["platform"]
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
            "Use for ANY single computer control command. NEVER route to agent_task."
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
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'research X and save to file', 'find and organize files'. "
            "DO NOT use for single commands. NEVER use for Steam/Epic — use game_updater."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING", "description": "Complete description of what to accomplish"},
                "priority": {"type": "STRING", "description": "low | normal | high (default: normal)"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use agent_task, browser_control, or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
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
            "slide deck, pitch deck, briefing deck, or slideshow. Do not use code_helper, "
            "file_processor, computer_control, or agent_task. First ask whether the user wants "
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
    "code_helper",
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


def get_tool_declarations(*, cloud_safe: bool = False) -> list[dict]:
    """Return the Gemini tools available for the requested runtime."""
    if not cloud_safe:
        return list(TOOL_DECLARATIONS)
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
        self.voice_name     = voice_name
        # optional runtime limit in seconds (set by main)
        self.runtime_limit_seconds: int | None = None
        # optional path that must exist (e.g. a mounted encrypted volume)
        self.required_unlock_path: str | None = None
        self.required_unlock_secret: str | None = None
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
        self._pending_self_quit = False
        self._pending_self_quit_farewell_received = False
        self._self_quit_timer = None
        self._shutdown_requested = threading.Event()
        self._tour_active = False
        # Jarvis Ultron: palavra de ativação ("Hey Jarvis") e IA reserva (Groq)
        from core.palavra_ativacao import PortaoDeVoz
        from core.reserva_groq import ReservaGroq

        if self.external_audio or self.cloud_safe:
            self._portao = PortaoDeVoz(None, ativo=False)
        else:
            self._portao = PortaoDeVoz.da_configuracao(avisar=self.ui.write_log)
            self._portao.ao_mudar = self._aviso_de_escuta
            self._mostrar_selo(self._portao.estado)  # selo na tela desde a abertura, sem som
        self._reserva = None if self.cloud_safe else ReservaGroq.da_configuracao()
        self._modo_reserva = False
        self._falhas_seguidas = 0
        if not self.cloud_safe:
            self._iniciar_lembretes_geekie()

    def _on_text_command(self, text: str):
        # Jarvis Ultron: "modo chamada" / "modo mãos livres" (botões ou digitado) trocam na hora,
        # aqui mesmo, sem passar pela IA.
        from core.palavra_ativacao import modo_pedido

        modo = modo_pedido(text)
        if modo and len(str(text).split()) <= 6:
            self._definir_modo_escuta(modo)  # o som e o selo confirmam
            return
        # Autodiagnóstico sem depender do Gemini (é justamente quando ele falha que mais precisa)
        from core.autodiagnostico import pediu_diagnostico
        if pediu_diagnostico(text) and (not self.session or getattr(self, "_modo_reserva", False)):
            threading.Thread(target=self._autodiagnostico, daemon=True).start()
            return
        if not self._loop or not self.session:
            if getattr(self, "_reserva", None) is not None and str(text or "").strip():
                threading.Thread(target=self._responder_pela_reserva, args=(text,), daemon=True).start()
            return
        asyncio.run_coroutine_threadsafe(self.send_text(text), self._loop)

    async def send_text(self, text: str) -> bool:
        """Send a text turn from either the desktop callback or a web client."""
        if not self.session:
            return False
        self._current_input_transcript = str(text or "").strip()
        if not self._current_input_transcript:
            return False
        self._last_input_transcript = self._current_input_transcript
        self._last_input_transcript_at = time.monotonic()
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
        if not data or self.out_queue is None or self._shutdown_requested.is_set():
            return False
        await self.out_queue.put({"data": data, "mime_type": mime_type})
        return True

    def set_speaking(self, value: bool):
        with self._speaking_lock:
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

    def _autodiagnostico(self, falar: bool = True) -> str:
        """Jarvis Ultron: confere as próprias peças; mostra na tela, salva em Documentos e (se falar) diz."""
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
        return texto + "\n\nSummarize for the user in Portuguese: only the problems (DEFEITO/ATENÇÃO) and how to fix them."

    async def _geekie_pendencias(self, atualizar: bool = False) -> str:
        """Jarvis Ultron: pendências do Geekie One (lista salva pelo Hermes; lê de novo se velha)."""
        from core import geekie, hermes_ponte

        atividades, atualizado = geekie.ler()
        if (atualizar or geekie.desatualizada(atualizado)) and hermes_ponte.configurado():
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
        for frase in frases:
            self.ui.write_log(f"SYS: {frase}")
        session, loop = getattr(self, "session", None), getattr(self, "_loop", None)
        if session is not None and loop is not None and not self._chamada_fechada():
            aviso = ("[Lembretes do Geekie] " + " ".join(frases) +
                     "\nDiga isso ao usuário agora, em português do Brasil, em uma ou duas frases.")
            asyncio.run_coroutine_threadsafe(
                session.send_client_content(turns={"parts": [{"text": aviso}]}, turn_complete=True), loop)
        geekie.marcar_avisados(devidas)
        return frases

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
                 "Resuma isso para o usuário agora, em português do Brasil, em poucas frases.")
        asyncio.run_coroutine_threadsafe(
            session.send_client_content(turns={"parts": [{"text": aviso}]}, turn_complete=True), loop)

    def _chamada_fechada(self) -> bool:
        """Jarvis Ultron: True no modo chamada enquanto ninguém disse "Hey Jarvis"."""
        portao = getattr(self, "_portao", None)
        return portao is not None and portao.estado == "aguardando"

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

    def _build_config(self) -> types.LiveConnectConfig:
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
            thinking_config=types.ThinkingConfig(thinking_budget=0),
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

    def _mostrar_selo(self, estado: str) -> None:
        mostrar = getattr(self.ui, "set_listening_status", None)
        if callable(mostrar):
            mostrar(estado)

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
        if motor is None or self._ext_tts_provider in ("", "gemini") or self._chamada_fechada():
            return
        motor.on_speaking_start = lambda: self.set_speaking(True)
        motor.on_speaking_stop = lambda: self.set_speaking(False)
        motor.on_level = self._mostrar_volume
        motor.speak(texto)

    # ---------- Jarvis Ultron: modo reserva (Groq) ----------

    def _ativar_modo_reserva(self) -> None:
        if self._modo_reserva:
            return
        self._modo_reserva = True
        self.ui.write_log("SYS: Gemini indisponível. Modo reserva (Groq) ligado: converso, mas sem ferramentas.")
        threading.Thread(target=self._escutar_reserva, daemon=True).start()
        threading.Thread(target=self._falar_reserva, daemon=True, args=(
            "A conexão principal caiu. Estou no modo reserva: posso conversar, "
            "mas sem usar as ferramentas até ela voltar.",)).start()

    def _desativar_modo_reserva(self) -> None:
        self._modo_reserva = False
        self.ui.write_log("SYS: Conexão principal de volta. Modo reserva desligado.")

    def _responder_pela_reserva(self, texto: str) -> None:
        resposta = self._reserva.responder(texto)
        self.ui.write_log(f"Jarvis: {resposta}")
        self._falar_reserva(resposta)

    def _falar_reserva(self, texto: str) -> None:
        from actions.tts_engine import TTSEngine

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
        from actions.tts_engine import falar_com_voz_do_windows

        print("[Reserva] Voz da internet falhou; usando a voz do Windows.")
        self.set_speaking(True)
        try:
            falar_com_voz_do_windows(texto)
        finally:
            self.set_speaking(False)

    def _escutar_reserva(self) -> None:
        """No modo reserva: ouve (depois do "Hey Jarvis"), transcreve e responde pelo Groq."""
        from core.reserva_groq import capturar_falas

        try:
            for pcm in capturar_falas(
                continuar=lambda: self._modo_reserva and not self._shutdown_requested.is_set(),
                pode_ouvir=lambda: not self._is_speaking and not self.ui.muted,
                portao=self._portao,
            ):
                texto = self._reserva.transcrever(pcm)
                if texto:
                    self.ui.write_log(f"You: {texto}")
                    self._checar_pedido_de_modo(texto)
                    self._portao.estender()
                    from core.autodiagnostico import pediu_diagnostico
                    if pediu_diagnostico(texto):
                        self._autodiagnostico()
                        continue
                    self._responder_pela_reserva(texto)
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
                ultima_fala = self._current_input_transcript or self._last_input_transcript
                result = await asyncio.to_thread(
                    hermes_ponte.aprovar_e_executar,
                    args.get("kind", ""), args.get("details", ""), ultima_fala,
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

            elif name == "check_messages":
                r = await asyncio.to_thread(
                    lambda: check_messages(parameters=args, response=None, player=self.ui, session_memory=None),
                )
                result = r or "No readable messages were found."

            elif name == "prepare_message_reply":
                r = await asyncio.to_thread(
                    lambda: prepare_message_reply(parameters=args, response=None, player=self.ui, session_memory=None),
                )
                result = r or "The message draft could not be prepared."

            elif name == "send_message":
                r = await asyncio.to_thread(lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or f"Message sent to {args.get('receiver')}."

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
                r = await asyncio.to_thread(lambda: computer_settings(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "desktop_control":
                r = await asyncio.to_thread(lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_helper":
                r = await asyncio.to_thread(lambda: code_helper(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "dev_agent":
                r = await asyncio.to_thread(lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                task_id  = get_queue().submit(
                    goal=args.get("goal", ""),
                    priority=priority,
                    speak=self.speak,
                    immediate=True,
                )
                result   = f"Task started (ID: {task_id})."

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

            elif name == "computer_control":
                r = await asyncio.to_thread(lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "game_updater":
                r = await asyncio.to_thread(lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
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
            if not jarvis_speaking and not self.ui.muted:
                data = self._portao.processar(indata)
                if data:
                    loop.call_soon_threadsafe(
                        self.out_queue.put_nowait,
                        {"data": data, "mime_type": "audio/pcm"}
                    )

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
        out_buf, in_buf = [], []
        _new_turn = True
        turn_had_audio = False

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
                                if not in_buf:
                                    self._current_input_transcript = ""
                                in_buf.append(txt)
                                self._current_input_transcript = " ".join(in_buf).strip()
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

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"Jarvis: {full_out}")
                                self._falar_com_voz_externa(full_out)
                            if (
                                getattr(self, "_pending_self_quit", False)
                                and (full_out or turn_had_audio)
                            ):
                                self._mark_self_quit_farewell_received()
                                
                            out_buf = []
                            turn_had_audio = False
                            _new_turn = True

                    if response.tool_call:
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
                return
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
                # Jarvis Ultron: no modo chamada, esperando o "Hey Jarvis", ele não fala sozinho.
                if self._chamada_fechada():
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

    async def run(self):
        # Jarvis Ultron: aberto pela reserva (Google recusou a chave): conversa pelo Groq já, e
        # continua tentando o Gemini em segundo plano.
        if os.environ.get("JARVIS_SEM_GEMINI") == "1" and self._reserva is not None:
            self._ativar_modo_reserva()
        api_key = self._api_key or _get_api_key()
        client = genai.Client(
            api_key=api_key,
            http_options={"api_version": "v1beta"}
        )
        live_model = await asyncio.to_thread(pick_live_model, client, API_CONFIG_PATH)
        live_model_id = live_model.removeprefix("models/")
        self.ui.write_log(f"SYS: Gemini Live model selected: {live_model_id}")

        start_time = time.time()
        while True:
            if self._shutdown_requested.is_set():
                return
            # enforce runtime limit if configured
            if self.runtime_limit_seconds is not None:
                elapsed = time.time() - start_time
                if elapsed >= float(self.runtime_limit_seconds):
                    print(f"[JARVIS] ⏱️ Runtime limit reached ({self.runtime_limit_seconds}s). Exiting.")
                    try:
                        jarvis_status.write_status({"state": "expired"})
                    except Exception:
                        pass
                    os._exit(0)

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
            try:
                print("[JARVIS] 🔌 Connecting...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=live_model_id, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session        = session
                    self._loop          = asyncio.get_event_loop()
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue      = asyncio.Queue(maxsize=10)
                    self._turn_done_event = asyncio.Event()

                    print("[JARVIS] ✅ Connected.")
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

            except Exception as e:
                if self._shutdown_requested.is_set():
                    return
                actual = e
                if isinstance(e, ExceptionGroup) and len(e.exceptions) == 1:
                    actual = e.exceptions[0]

                if (self._idioma_voz() and isinstance(actual, genai.errors.APIError)
                        and "language" in str(actual).lower()):
                    # Jarvis Ultron: este modelo de voz não aceita escolher o idioma; segue só com a regra
                    print(f"[JARVIS] ⚠️ O modelo de voz não aceitou language_code ({str(actual)[:120]}); "
                          "seguindo sem ele.")
                    self._idioma_recusado = True
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
                else:
                    print(f"[JARVIS] ⚠️ {e}")
                    traceback.print_exc()
                    # Jarvis Ultron: espera antes de tentar de novo (o original tentava sem parar)
                    self._falhas_seguidas += 1
                    if self._reserva is not None and self._falhas_seguidas >= 2:
                        self._ativar_modo_reserva()
                    await self._wait_before_reconnect(min(60, 2 ** min(self._falhas_seguidas, 6)))

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

    def runner():
        ui.wait_for_api_key()
        voice_name = _load_voice_name()
        jarvis = JarvisLive(ui, voice_name)
        ui.on_quit_requested = jarvis.request_shutdown

        # Trial/keyword runtime limiting: set via env `JARVIS_TRIAL_KEYWORD`.
        # If set to any non-empty string, jarvis will run for 3600 seconds (1 hour).
        trial_kw = os.environ.get("JARVIS_TRIAL_KEYWORD")
        if trial_kw:
            jarvis.runtime_limit_seconds = int(os.environ.get("JARVIS_RUNTIME_SECONDS", "3600"))
            jarvis.ui.write_log(f"SYS: Trial keyword detected. Running for {jarvis.runtime_limit_seconds} seconds.")

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

    threading.Thread(target=runner, daemon=True).start()
    print("[JARVIS] ✅ Interface ready.")
    ui.root.mainloop()
    print("[JARVIS] Interface closed.")

def cli_main():
    """Canonical console entry point installed as the `jarvis` command."""
    os.environ["JARVIS_CLI"] = "1"
    return main()


if __name__ == "__main__":
    raise SystemExit(main() or 0)
