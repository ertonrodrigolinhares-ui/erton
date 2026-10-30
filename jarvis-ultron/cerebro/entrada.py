"""A entrada do Jarvis Ultron (o que o Erton digita e o áudio que o microfone manda): um pedaço da JarvisLive.

Etapa 15 da reorganização: a JarvisLive (main.py) é montada com pedaços como este, com os MESMOS nomes de
função e de atributo de antes. Nada aqui lê o ambiente nem toca no Gemini ao ser importado.

- _on_text_command: o texto digitado na tela; os pedidos de modo (chamada, privado, Ultron) são atendidos
  aqui mesmo, sem passar pela IA; sem o Gemini vai para a reserva ou fica guardado (_guardar_ate_conectar);
- send_text e _mandar_textos_esperando: mandam o texto ao Gemini; _avisar_se_nao_enviou avisa se caiu;
- _nova_fala: conta uma fala NOVA do Erton (o "ok" das aprovações, core/aprovacao.py);
- send_audio_chunk e _microfone_mandou_audio: o áudio do microfone;
- _trava_da_fala e _trava_textos: as travas (criadas no __init__; aqui só para quem nasce sem ele)."""

import asyncio
import threading
import time

from cerebro.desligar import SELF_QUIT_GOODBYE
from cerebro.ferramentas.politica import ESPERE_O_MODO_PRIVADO


class Entrada:
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
