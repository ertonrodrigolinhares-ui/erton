"""Rodar código na tela do Jarvis a partir de qualquer parte do programa (Jarvis Ultron).

A tela (PyQt) só pode ser mexida pelo "fio" dela. Automações rodam em outros fios, então usam:

    from core.na_tela import executar
    executar(lambda: ...)   # roda a função na tela, assim que ela puder

`preparar()` é chamado uma vez pelo main.py, logo depois de a tela ser criada.
"""

from __future__ import annotations

import threading

_mensageiro = None
_pendentes: list = []
_trava = threading.Lock()


def preparar() -> None:
    """Chame no fio da tela, depois de criar o QApplication."""
    global _mensageiro
    from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

    class Mensageiro(QObject):
        pedido = pyqtSignal(object)

        @pyqtSlot(object)
        def rodar(self, funcao):
            try:
                funcao()
            except Exception as erro:  # uma automação com defeito nunca derruba a tela
                print(f"[Tela] Automação: {erro}")

    with _trava:
        _mensageiro = Mensageiro()
        _mensageiro.pedido.connect(_mensageiro.rodar)
        pendentes = list(_pendentes)
        _pendentes.clear()
    for funcao in pendentes:
        _mensageiro.pedido.emit(funcao)


def pronta() -> bool:
    return _mensageiro is not None


def executar(funcao) -> None:
    """Roda `funcao()` no fio da tela. Se a tela ainda não existe, roda quando ela abrir."""
    with _trava:
        if _mensageiro is None:
            _pendentes.append(funcao)
            return
        mensageiro = _mensageiro
    mensageiro.pedido.emit(funcao)
