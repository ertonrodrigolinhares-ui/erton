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
from core import status as jarvis_status
from core.jarvis_client import JarvisClient
from core.frases import frase
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
)
import time

from core.live_model import pick_live_model
# Etapa 15: a pasta do Jarvis e os caminhos fixos moram em cerebro/ambiente.py (os nomes continuam aqui)
from cerebro.ambiente import API_CONFIG_PATH, BASE_DIR, PROMPT_PATH, get_base_dir  # noqa: F401


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


_load_dotenv()
# Jarvis Ultron: caminho do Gemini (normal ou Vertex AI, para as chaves "AQ."); vale para tudo
from core.gemini_acesso import aplicar_via as _aplicar_via_gemini
_aplicar_via_gemini()

# Jarvis Ultron: escolhe sozinho os modelos do Gemini disponíveis para a chave
from core.modelos import instalar as _instalar_central_de_modelos
_instalar_central_de_modelos()
LIVE_MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
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


def _is_unsupported_voice_error(exc: Exception) -> bool:
    if not isinstance(exc, genai.errors.APIError):
        return False
    code = getattr(exc, "code", None)
    msg = str(exc).lower()
    if code == 1007:
        return "requested voice api_name" in msg and "not available for model" in msg
    return "requested voice api_name" in msg and "not available for model" in msg


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

from cerebro.ferramentas.declaracoes import TOOL_DECLARATIONS  # Etapa 12: o texto mora lá, igual ao de antes

# Etapas 12 a 14: as ferramentas moram em cerebro/ferramentas/ (declarações, regras, executores e o registro
# das automações). Os nomes continuam aqui para quem usa main.<nome> (core/cerebro_gemma, painel_ultron, testes).
from cerebro.ferramentas.politica import (  # noqa: E402
    AVISO_MODO_PRIVADO, ESPERE_O_MODO_PRIVADO, FERRAMENTAS_DESLIGADAS, FERRAMENTAS_NUVEM_IA, MUDAM_ALGO,
    bloqueio_do_modo_privado, resposta_de_desligada,
)
from cerebro.ferramentas.registro import carregar_automacoes, get_tool_declarations  # noqa: E402,F401
from cerebro.ferramentas.fichas import EXECUTORES  # noqa: E402
from cerebro.ferramentas.executores import (  # noqa: E402,F401
    browser_control, computer_settings, desktop_control, email_control, file_controller,
    file_processor, flight_finder, media_control, open_app, reminder, request_deep_research,
    request_presentation, screen_process, weather_action, web_search_action, youtube_video,
)

# Etapa 15: a JarvisLive é montada com pedaços que moram em cerebro/*.py, com os mesmos nomes de antes
# (tests/test_cerebro_em_pedacos.py diz o que mora em cada um). As constantes continuam aqui para quem usa main.X.
from cerebro.avisos import Avisos  # noqa: E402
from cerebro.escuta import Escuta, QUIET_MODE_RESULT  # noqa: E402,F401
from cerebro.pontes import Pontes  # noqa: E402
from cerebro.voz_saida import (  # noqa: E402,F401
    DEFAULT_VOICE_NAME, SUPPORTED_VOICE_NAMES, VozSaida, _AVISOS_EM_PORTUGUES, _limpar_para_falar,
    _load_voice_name, _normalize_voice_name,
)
from cerebro.ultron import Ultron  # noqa: E402
from cerebro.desligar import Desligar, SELF_QUIT_GOODBYE, _SELF_QUIT_PATTERNS  # noqa: E402,F401
from cerebro.entrada import Entrada  # noqa: E402
from cerebro.reserva import Reserva  # noqa: E402
from cerebro.modo_privado import ModoPrivado  # noqa: E402


def muda_algo(nome: str) -> bool:
    """Esta ferramenta muda alguma coisa (roda em fila num lote)? Etapa 14 (c): o padrão seguro é SIM. Só as
    fichas marcadas muda_algo=False (só leitura) e as automações com MUDA_ALGO = False rodam em paralelo.
    Nome desconhecido também vai para a fila."""
    if nome in MUDAM_ALGO:
        return True
    from cerebro.ferramentas.fichas import POR_NOME

    if nome in POR_NOME:
        return False  # ficha marcada como só leitura
    automacao = carregar_automacoes().ferramentas.get(nome)
    if automacao is not None:
        return bool(getattr(automacao, "muda_algo", True))
    return True




class JarvisLive(Avisos, Escuta, Pontes, VozSaida, Ultron, Desligar, Entrada, Reserva, ModoPrivado):

    def __init__(
        self,
        client: JarvisClient,
        voice_name: str = "Puck",
        *,
        api_key: str | None = None,
    ):
        # Keep ``ui`` as a compatibility alias for desktop integrations that
        # already inspect JarvisLive.ui. The engine contract is JarvisClient.
        # (Etapa 14 d: os modos do servidor web, cloud_safe e external_audio, saíram com o servidor.)
        self.client         = client
        self.ui             = client
        self._api_key       = api_key.strip() if isinstance(api_key, str) else None
        self.tool_declarations = get_tool_declarations()
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self._falando_no_pc = 0  # Jarvis Ultron: a voz do Windows falando (trava própria do microfone)
        self._voz_externa_pendente = 0  # respostas que a voz externa (ElevenLabs...) ainda vai falar
        self.voice_name     = voice_name
        self._textos_trava = threading.Lock()  # texto digitado antes de o Gemini conectar
        self._textos_esperando = []
        self.ui.on_text_command = self._on_text_command
        self._turn_done_event: asyncio.Event | None = None
        self._tts_engine = None
        self._ext_tts_provider = ""
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
        # Jarvis Ultron: palavra de ativação ("Hey Jarvis") e IA reserva (Groq)
        from core.palavra_ativacao import PortaoDeVoz
        self._portao = PortaoDeVoz.da_configuracao(avisar=self.ui.write_log)
        self._portao.ao_mudar = self._aviso_de_escuta
        self._mostrar_selo(self._portao.estado)  # selo na tela desde a abertura, sem som
        from core.cerebro_gemma import CerebroGemma, cerebro_gemma

        if cerebro_gemma():  # Jarvis Ultron: Gemma 4 no PC como cérebro principal
            self._reserva = CerebroGemma.da_configuracao()
        else:  # Groq e/ou outra empresa (JARVIS_RESERVA), em fila: quando o limite de uma acaba, vai a outra
            from core.reserva_outra import reserva_da_configuracao

            self._reserva = reserva_da_configuracao()
        # modo privado mesmo se o Gemma não subiu (assim "modo normal" digitado ainda troca)
        self._cerebro_nome = "gemma" if cerebro_gemma() else "gemini"
        self._trocando_cerebro = False  # indo para o modo privado: nada do microfone/texto vai para a nuvem
        self._modo_reserva = False
        self._falhas_seguidas = 0
        self._avisos_trava = threading.Lock()  # avisos guardados no modo chamada
        self._avisos_guardados = []
        self._avisos_ao_falar = []  # quem quer saber quando o aviso guardado foi falado
        # Jarvis Ultron (etapa 15): tudo o que a JarvisLive guarda nasce aqui, e não no meio do caminho.
        # O tests/test_contratos.py confere que todo getattr(self, ...) do main.py lê um atributo
        # criado neste __init__: um erro de digitação dava para mudar o comportamento sem dar erro.
        self._resposta_digitada_ate = 0.0  # até quando a resposta a um texto digitado é falada (modo chamada)
        self._ja_cumprimentou = False  # a saudação da abertura já foi dita
        self._idioma_recusado = False  # o modelo da voz não aceitou escolher o idioma
        self._erro_ouvido_avisado = None  # o último erro do microfone da reserva já avisado (não repete)
        self._ultima_fala_em = None  # quando o Erton falou por último (mede a demora da resposta)
        self._leituras_sem_registro = 0  # resultados do Ultron que o Gemini vai ler sem escrever de novo
        self._leituras_sem_registro_ate = 0.0  # ... e até quando isso vale
        self._loop_reserva = None  # o laço assíncrono da reserva (Groq/Gemma), criado quando é preciso
        self._reserva_ferramentas = None  # as ferramentas traduzidas para a reserva, montadas uma vez
        self._suspensao = None  # a tarefa que acorda o Jarvis depois de "suspender por N minutos"
        self._abrir_ultron = None  # o painel Ultron registra aqui como abrir/fechar (automacoes/painel_ultron.py)
        # o "ok" das aprovações (core/aprovacao.py) escreve nestes três: a fala atual chega em pedaços?
        self._fala_em_pedacos = False
        self._fala_aberta = False
        self._fala_mudou_em = 0.0
        self._iniciar_lembretes_geekie()
        threading.Thread(target=self._preparar_automacoes, daemon=True, name="Automacoes").start()

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

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        # Jarvis Ultron: modo privado. Trava no código (não só no prompt do Gemma): vale também para o
        # painel Ultron e para chamadas que o modelo inventar. (A trava do servidor, cloud_safe, que vinha
        # antes desta, saiu com o servidor na Etapa 14.)
        bloqueio = bloqueio_do_modo_privado(name, args)
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
            executor = EXECUTORES.get(name)
            if executor is not None:
                result = await executor(self, args)

            elif name in FERRAMENTAS_DESLIGADAS:
                # desligada de propósito (Etapa 3): responde e não chama nada
                self.ui.write_log(f"SYS: ⛔ {name} está desligada no Jarvis.")
                result = resposta_de_desligada(name)

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
        call_list = list(calls or [])
        if any(muda_algo(getattr(call, "name", "")) for call in call_list):
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
                    if stream is not None:
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
        from core.cerebro_gemma import cerebro_gemma

        if cerebro_gemma():
            if self._reserva is not None:
                self._ativar_modo_reserva()
            else:
                # Modo privado sem o Gemma: NUNCA cai para o Gemini (a tela mostra MODO PRIVADO).
                # Fica parado até ele pedir o modo normal (digitado) ou fechar o Jarvis.
                aviso = frase("gemma_nao_ligou")
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
                    try:
                        jarvis_status.write_status({
                            "state": "online",
                            "voice": self._get_current_voice(),
                            "pid": os.getpid(),
                        })
                    except Exception:
                        pass

                    tg.create_task(self._send_realtime())
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
                if self._modo_reserva and not getattr(self.ui, "muted", False):
                    # a reserva está ouvindo: o anel volta a "OUVINDO" em vez de ficar em "PENSANDO" até o Gemini voltar
                    self.ui.set_state("LISTENING")
                argumento_invalido = "1007" in str(actual) or "invalid argument" in str(actual).lower()
                if _chave_recusada(actual):
                    # Jarvis Ultron: o Google recusou a CHAVE, não o modelo (o aviso também vem com o código
                    # 1007). Avisa uma vez, cai para a reserva e espera cada vez mais entre as tentativas.
                    # Antes caía no "modelo recusou a configuração" e ficava em laço a cada 2 s, enchendo o
                    # Canal com três avisos por volta.
                    self._falhas_seguidas += 1
                    if self._falhas_seguidas == 1:
                        self.ui.write_log(f"SYS: {frase('chave_gemini_recusada')}")
                    print(f"[JARVIS] ⚠️ Chave do Gemini recusada: {str(actual)[:120]}")
                    if self._reserva is not None:
                        self._ativar_modo_reserva()
                    await self._wait_before_reconnect(min(300, 30 * 2 ** min(self._falhas_seguidas - 1, 4)))
                elif (self._idioma_voz() and isinstance(actual, genai.errors.APIError)
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
                    if proximo == modelo_voz:
                        # não há outro modelo para tentar: espera cada vez mais (antes ficava em laço a cada 2 s)
                        self._falhas_seguidas += 1
                        if self._falhas_seguidas == 1:
                            self.ui.write_log(f"SYS: A voz {modelo_voz} recusou a configuração. Vou tentar de novo "
                                              "daqui a pouco.")
                        print(f"[Modelos] Voz: {modelo_voz} recusou a configuração (1007); sem outro modelo para tentar.")
                        await self._wait_before_reconnect(min(60, 2 ** min(self._falhas_seguidas, 6)))
                    else:
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
                    try:
                        jarvis_status.write_status({"state": "voice_fallback", "voice": DEFAULT_VOICE_NAME})
                    except Exception:
                        pass
                elif isinstance(actual, genai.errors.APIError) and "1000" in str(actual):
                    print("[JARVIS] 🔌 Session ended normally.")
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


def _chave_recusada(erro: BaseException) -> bool:
    """O Google recusou a chave do Gemini (errada, apagada ou vencida). Não é erro do modelo nem da internet."""
    texto = f"{erro}".lower()
    return any(p in texto for p in ("api key not valid", "api_key_invalid", "invalid api key", "api key expired",
                                    "api_key_expired"))


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


def rodar_cerebro(ui):
    """O cérebro do Jarvis (voz, IA, ferramentas). Roda num fio da tela (um programa só) ou
    no programa próprio do cérebro, com a UIRemota no lugar da tela (veja core/ponte.py)."""
    ui.wait_for_api_key()
    voice_name = _load_voice_name()
    jarvis = JarvisLive(ui, voice_name)
    ui.on_quit_requested = jarvis.request_shutdown
    _contar_mudanca_desfeita(jarvis)

    ui.on_voice_change = jarvis.update_voice
    def _on_tts_change(provider, api_key, voice_id):
        if provider == "gemini":
            jarvis._tts_engine = None
            jarvis._ext_tts_provider = ""
            jarvis.update_voice(voice_id)
        else:
            jarvis._ext_tts_provider = provider
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
