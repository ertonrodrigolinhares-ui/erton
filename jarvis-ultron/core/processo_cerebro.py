"""O cérebro do Jarvis Ultron como programa próprio (aberto pela tela; veja core/ponte.py).

Não abra este arquivo direto: o "Iniciar Jarvis Ultron" abre a tela, e a tela abre o cérebro
passando o endereço e a senha do canal (JARVIS_PONTE_PORTA / JARVIS_PONTE_CHAVE).
"""

from __future__ import annotations

import os
import sys


def desfazer_mudanca_interrompida() -> None:
    """Uma mudança do Claude no código ficou pela metade (o cérebro antigo foi religado ou caiu no meio)?
    Desfaz ANTES de importar o resto do Jarvis, que pode estar com o código pela metade. O aviso ao
    Erton é dado depois, pelo cérebro já aberto (main._contar_mudanca_desfeita)."""
    try:
        from core import claude_chefe

        aviso = claude_chefe.desfazer_interrompida()
    except Exception as erro:
        print(f"[Cérebro] Não consegui conferir a mudança do Claude: {erro}")
        return
    if aviso:
        print(f"[Cérebro] {aviso}")


def principal() -> int:
    porta = os.environ.get("JARVIS_PONTE_PORTA", "").strip()
    chave = os.environ.get("JARVIS_PONTE_CHAVE", "").strip()
    if not porta or not chave:
        print("[Cérebro] Abra o Jarvis pelo 'Iniciar Jarvis Ultron' (este programa é aberto pela tela).")
        return 2
    from multiprocessing.connection import Client

    try:
        conexao = Client(("127.0.0.1", int(porta)), authkey=bytes.fromhex(chave))
    except Exception as erro:
        print(f"[Cérebro] Não consegui falar com a tela: {erro}")
        return 3
    # a senha não precisa ficar à vista de nada que o cérebro abrir depois
    os.environ.pop("JARVIS_PONTE_CHAVE", None)

    from core.ponte import UIRemota

    ui = UIRemota(conexao)
    ui.iniciar()
    desfazer_mudanca_interrompida()
    import main

    try:
        main.rodar_cerebro(ui)
    finally:
        try:
            conexao.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    codigo = principal()
    sys.stdout.flush()
    os._exit(codigo)  # threads de áudio/IA que sobrarem não seguram o programa aberto
