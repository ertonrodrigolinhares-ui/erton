"""O modo privado do Jarvis Ultron (trocar o cérebro: Gemma 4 no PC ou Gemini na nuvem): um pedaço da
JarvisLive.

Etapa 15 da reorganização: a JarvisLive (main.py) é montada com pedaços como este, com os MESMOS nomes de
função e de atributo de antes. Nada aqui lê o ambiente nem toca no Gemini ao ser importado.

- _pedido_de_cerebro: "modo privado" ou "modo normal", digitado ou falado. A trava _trocando_cerebro liga
  ANTES de abrir o fio TrocarCerebro: até o cérebro novo subir, nada do microfone nem do texto vai para a nuvem;
- _trocar_cerebro: confere o que falta (voz local, Gemma instalado, Claude mudando o código) e pede à tela
  para religar o cérebro; _recusar_troca e _troca_pela_voz_indisponivel avisam quando NÃO trocou;
- _avisar_o_que_para: o que roda em segundo plano (TRABALHOS_QUE_PARAM) morre ao religar; ele avisa antes.
A trava no código das ferramentas de nuvem fica em cerebro/ferramentas/politica.py (bloqueio_do_modo_privado)."""

import os
import threading

from cerebro.ferramentas.politica import ESPERE_O_MODO_PRIVADO


class ModoPrivado:
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
