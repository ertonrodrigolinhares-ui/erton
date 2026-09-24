"""Ponto de entrada do Jarvis.

    python -m jarvis                    # abre a janela (o normal)
    python -m jarvis --terminal         # conversa digitando no terminal
    python -m jarvis --terminal --voz   # terminal ouvindo o microfone ("Jarvis, ...")
"""

import argparse
import traceback
from pathlib import Path

from . import voz
from .assistente import remover_palavra_ativacao, responder, saudacao
from .config import ARQUIVO_ENV, Config
from .ia import criar_cerebro


def modo_terminal(usar_voz: bool) -> None:
    config = Config.carregar()
    falador_aviso = voz.Falador.da_config(config) if usar_voz else None

    def confirmar(titulo: str, detalhe: str) -> bool:
        print(f"\n[{titulo}]\n{detalhe}")
        return input("Autoriza? (s/n): ").strip().lower().startswith("s")

    def avisar(texto: str) -> None:
        print(f"\nJarvis: {texto}")
        if falador_aviso:
            falador_aviso.falar(texto)

    cerebro = criar_cerebro(config, confirmar=confirmar, avisar=avisar,
                            ao_usar=lambda nome: print(f"  (usando {nome})"))
    if cerebro is None:
        print(f"[Jarvis] Falta a chave {config.nome_chave} em {ARQUIVO_ENV} ({config.site_chave}).")
        print("         Por enquanto só os comandos locais vão funcionar.")

    if usar_voz and not (voz.fala_disponivel() and voz.microfone_disponivel()):
        print("[Jarvis] Microfone ou bibliotecas de voz indisponíveis; usando texto.")
        usar_voz = False
    falador = falador_aviso if usar_voz else None

    def falar(texto: str) -> None:
        print(f"Jarvis: {texto}")
        if falador:
            falador.falar(texto)
            falador.aguardar()

    falar(saudacao(config.nome_usuario))
    if usar_voz:
        falar(f"Diga '{config.palavra_ativacao}' antes de cada pedido.")

    while True:
        if usar_voz:
            print("Ouvindo...")
            entrada = voz.ouvir_microfone(config.idioma)
            if entrada:
                print(f"Você: {entrada}")
            entrada = remover_palavra_ativacao(entrada, config.palavra_ativacao)
        else:
            try:
                entrada = input("Você: ").strip()
            except EOFError:
                entrada = "sair"
        if not entrada:
            continue

        resposta, acao = responder(entrada, cerebro, config.nome_usuario)
        falar(resposta)
        if acao == "sair":
            break


def main() -> None:
    parser = argparse.ArgumentParser(description="Jarvis - assistente pessoal em Python")
    parser.add_argument("--terminal", action="store_true", help="usar o terminal em vez da janela")
    parser.add_argument("--voz", action="store_true", help="no terminal, ouvir pelo microfone")
    args = parser.parse_args()

    if args.terminal:
        modo_terminal(args.voz)
        return
    try:
        from .janela import abrir
        abrir()
    except Exception:
        # Aberto com dois cliques não há terminal: registra o erro num arquivo.
        registro = Path(__file__).resolve().parent.parent / "jarvis-erro.txt"
        registro.write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
