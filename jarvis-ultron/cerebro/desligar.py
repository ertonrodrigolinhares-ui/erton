"""Desligar o Jarvis Ultron (só com o pedido claro e depois da despedida) e suspender por alguns minutos:
um pedaço da JarvisLive.

Etapa 15 da reorganização: a JarvisLive (main.py) é montada com pedaços como este, com os MESMOS nomes de
função e de atributo de antes. Nada aqui lê o ambiente nem toca no Gemini ao ser importado.

- _is_explicit_self_quit_transcript: a fala do Erton pediu mesmo para desligar? (_SELF_QUIT_PATTERNS);
- _queue_self_quit_after_farewell, _mark_self_quit_farewell_received, _complete_self_quit_after_audio e
  _force_complete_self_quit: ele se despede (SELF_QUIT_GOODBYE) e só então fecha;
- request_shutdown: o pedido de fechar, de qualquer fio;
- _suspender e _voltar_da_suspensao: "suspender por 5 minutos" cala o microfone e volta sozinho."""

import asyncio
import re
import threading


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


class Desligar:
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
        self.ui.handle_ui_command("quit_jarvis")  # ação interna da tela (o botão se chama "Sair do Jarvis")
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
