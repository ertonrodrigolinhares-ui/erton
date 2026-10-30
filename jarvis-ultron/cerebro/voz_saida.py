"""A voz de saída do Jarvis Ultron (o que ele fala e com que voz): um pedaço da JarvisLive.

Etapa 15 da reorganização: a JarvisLive (main.py) é montada com pedaços como este, com os MESMOS nomes de
função e de atributo de antes. Nada aqui lê o ambiente nem toca no Gemini ao ser importado.

- set_speaking: a trava "está falando" (fecha o microfone; a voz do PC tem a trava própria dela);
- speak, _speak_vision_result e speak_error: mandam um texto para o Gemini dizer;
- update_voice, _get_current_voice, _idioma_voz e as vozes suportadas (SUPPORTED_VOICE_NAMES);
- _falar_com_voz_externa: ElevenLabs/OpenAI/Edge, quando escolhida;
- _limpar_para_falar: tira as instruções em inglês que as ferramentas deixam para a IA."""

import asyncio
import json
import os
import threading

from core.frases import frase

from cerebro.ambiente import API_CONFIG_PATH


SUPPORTED_VOICE_NAMES = {
    "puck", "charon", "kore", "fenrir", "aoede",
    "leda", "orus", "schedar", "zubenelgenubi"
}


DEFAULT_VOICE_NAME   = "puck"


def _normalize_voice_name(voice_name: str | None) -> str:
    if not voice_name:
        return DEFAULT_VOICE_NAME
    candidate = voice_name.strip().lower()
    return candidate if candidate in SUPPORTED_VOICE_NAMES else DEFAULT_VOICE_NAME


def _load_voice_name() -> str:
    voice = os.environ.get("GEMINI_VOICE_NAME")
    if voice:
        return _normalize_voice_name(voice)
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            return _normalize_voice_name(json.load(f).get("voice_name"))
    except Exception:
        return DEFAULT_VOICE_NAME


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
    for inicio, aviso in _AVISOS_EM_PORTUGUES.items():
        if texto.startswith(inicio):
            return aviso
    marcas = ["Tell the user", "Explique ao usuário", "Explique isso", "Answer the user", "Answer in",
              "Confirm to the user", "Confirm in", "Say this to the user", "Oriente o usuário",
              "\nTell the user", "Then tell the user", "Summarize for the user"]
    corte = len(texto)
    for m in marcas:
        i = texto.find(m)
        if i != -1:
            corte = min(corte, i)
    return texto[:corte].strip() or texto


class VozSaida:
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
        self.speak(frase("erro_na_ferramenta_falado", ferramenta=tool_name, detalhe=short))

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

    def _idioma_voz(self) -> str:
        """Jarvis Ultron: idioma da voz (JARVIS_IDIOMA, padrão pt-BR). Vazio se o modelo recusou."""
        if getattr(self, "_idioma_recusado", False):
            return ""
        return os.environ.get("JARVIS_IDIOMA", "pt-BR").strip()

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
