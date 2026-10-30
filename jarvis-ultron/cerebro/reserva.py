"""O modo reserva do Jarvis Ultron (Groq, outra empresa ou o Gemma 4 no PC quando o Gemini não está):
um pedaço da JarvisLive.

Etapa 15 da reorganização: a JarvisLive (main.py) é montada com pedaços como este, com os MESMOS nomes de
função e de atributo de antes. Nada aqui lê o ambiente nem toca no Gemini ao ser importado.

- _ativar_modo_reserva, _desativar_modo_reserva e _ligar_cerebro_gemma: ligar e desligar a reserva
  (automacoes/autoconserto.py chama _ativar_modo_reserva);
- _escutar_reserva, _responder_pela_reserva e _falar_reserva: ouvir, responder e falar sem o Gemini;
- _ferramentas_da_reserva e _executar_ferramenta_reserva: as ferramentas essenciais (RESERVA_FERRAMENTAS_ESSENCIAIS,
  marcadas nas fichas) rodam pelo mesmo _execute_tool do Gemini, num laço próprio (_garantir_loop_reserva);
- _avisar_sem_ouvido: no modo privado sem a transcrição local, avisa uma vez."""

import asyncio
import os
import threading
import time
from types import SimpleNamespace

from cerebro.ferramentas.fichas import RESERVA_FERRAMENTAS_ESSENCIAIS as _RESERVA_DAS_FICHAS
from cerebro.ferramentas.politica import bloqueio_do_modo_privado
from cerebro.ferramentas.registro import carregar_automacoes, get_tool_declarations


class Reserva:
    def _ativar_modo_reserva(self) -> None:
        if self._modo_reserva:
            return
        from core.cerebro_gemma import CerebroGemma

        if isinstance(getattr(self, "_reserva", None), CerebroGemma):
            self._ligar_cerebro_gemma()
            return
        self._modo_reserva = True
        self.ui.write_log(f"SYS: Gemini indisponível. Modo reserva ({getattr(self._reserva, 'nome', 'Groq')}) ligado: "
                          "converso e executo as tarefas.")
        threading.Thread(target=self._escutar_reserva, daemon=True).start()
        aviso = "A conexão principal caiu. Estou no modo reserva, mas continuo executando suas tarefas."
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
    RESERVA_FERRAMENTAS_ESSENCIAIS = _RESERVA_DAS_FICHAS  # essencial_na_reserva=True nas fichas (Etapa 14)

    def _ferramentas_da_reserva(self):
        """Ferramentas do Jarvis no formato do Groq + a função que as executa (modo reserva).
        JARVIS_RESERVA_FERRAMENTAS=0 no .env desliga as ferramentas (fica só conversa, mais leve).
        No modo privado (Gemma) só vão as que não usam IA na nuvem, e sem gravar memória."""
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
