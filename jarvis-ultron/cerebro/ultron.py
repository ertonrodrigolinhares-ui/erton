"""O modo Ultron do Jarvis (o painel de automações, pela voz e pelos botões): um pedaço da JarvisLive.

Etapa 15 da reorganização: a JarvisLive (main.py) é montada com pedaços como este, com os MESMOS nomes de
função e de atributo de antes. Nada aqui lê o ambiente nem toca no Gemini ao ser importado.

- _pedido_de_ultron: "modo ultron" abre o painel e "modo jarvis" fecha (digitado ou falado);
- rodar_automacao_ultron: um botão do painel roda a automação DIRETO, sem passar pela IA
  (automacoes/painel_ultron.py e core/ponte.py chamam por este nome);
- _falar_resultado_ultron: o resultado sai pela voz que estiver disponível, uma vez só no Canal."""

import asyncio
import re
import threading
import time

from cerebro.voz_saida import _limpar_para_falar


class Ultron:
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
