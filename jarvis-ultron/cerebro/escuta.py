"""O modo de escuta do Jarvis Ultron (mãos livres ou chamada, "Hey Jarvis"): um pedaço da JarvisLive.

Etapa 15 da reorganização: a JarvisLive (main.py) é montada com pedaços como este, com os MESMOS nomes de
função e de atributo de antes. Nada aqui lê o ambiente nem toca no Gemini ao ser importado.

- _definir_modo_escuta: a ferramenta que troca o modo (o portão é o core/palavra_ativacao.py);
- _aviso_de_escuta: o som curto e o selo na tela quando ele começa ou para de ouvir;
- _checar_pedido_de_modo: troca o modo pela frase falada, mesmo que a IA não chame a ferramenta;
- _mostrar_selo e _mostrar_volume: o que a tela mostra do microfone."""


# Jarvis Ultron: a troca de modo já é avisada por um som e pelo selo na tela.
QUIET_MODE_RESULT = ("Done. The user already heard a chime and sees the mode on screen: do not announce "
                     "or explain the listening mode. Say nothing at all.")


class Escuta:
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
        if estado in ("ouvindo", "maos_livres"):
            self._falar_avisos_guardados()

    def _mostrar_selo(self, estado: str) -> None:
        mostrar = getattr(self.ui, "set_listening_status", None)
        if callable(mostrar):
            mostrar(estado)

    def _mostrar_volume(self, pcm: bytes) -> None:
        """Jarvis Ultron: manda o volume da voz para a esfera pulsar enquanto ele fala."""
        definir = getattr(self.ui, "set_voice_level", None)
        if callable(definir):
            from core.efeito_ultron import nivel_da_voz
            definir(nivel_da_voz(pcm))

    def _checar_pedido_de_modo(self, fala: str) -> None:
        """Troca o modo pela frase falada, mesmo que a IA não chame a ferramenta."""
        from core.palavra_ativacao import modo_pedido

        portao = getattr(self, "_portao", None)
        modo = modo_pedido(fala)
        if modo and portao is not None and portao.modo != modo:
            self._definir_modo_escuta(modo)
