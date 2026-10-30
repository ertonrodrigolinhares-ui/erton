"""As pontes do Jarvis Ultron para o Hermes, o Geekie One e o autodiagnóstico: um pedaço da JarvisLive.

Etapa 15 da reorganização: a JarvisLive (main.py) é montada com pedaços como este, com os MESMOS nomes de
função e de atributo de antes. Nada aqui lê o ambiente nem toca no Gemini ao ser importado.

- _hermes_sem_travar e _entregar_resultado_hermes: o Hermes pode levar minutos; a conversa não trava;
- _geekie_pendencias, _verificar_lembretes_geekie e _iniciar_lembretes_geekie: as atividades do Geekie One;
- _autodiagnostico: confere as próprias peças (core/autodiagnostico.py);
- _preparar_automacoes: mostra e liga as automações da pasta automacoes/ ao abrir."""

import asyncio
import threading
import time

from cerebro.ferramentas.politica import AVISO_MODO_PRIVADO
from cerebro.ferramentas.registro import carregar_automacoes


class Pontes:
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
