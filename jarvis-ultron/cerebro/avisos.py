"""Os avisos falados do Jarvis Ultron (lembretes, Geekie, automações, Hermes): um pedaço da JarvisLive.

Etapa 15 da reorganização: a JarvisLive (main.py) é montada com pedaços como este, com os MESMOS nomes de
função e de atributo de antes. Nada aqui lê o os.environ nem cria cliente do Gemini ao ser importado.

- anunciar: qualquer fio chama; respeita o modo de escuta (fala agora, guarda ou só mostra na tela);
- _falar_aviso: pelo Gemini, pela voz reserva ou, se sigiloso, só pela voz do Windows (_falar_no_pc);
- _falar_avisos_guardados: o que ficou guardado no modo chamada sai depois do "Hey Jarvis";
- _notificar_na_tela: o balão do Windows e o aviso dentro da janela."""

import asyncio
import os
import threading
import time


class Avisos:
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
