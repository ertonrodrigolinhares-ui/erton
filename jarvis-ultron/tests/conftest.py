"""Ajustes do pytest para os testes do Jarvis Ultron.

A sentinela (test_sentinela.py) tira a foto dos dados do Erton ao ser carregada: por isso ela é
carregada aqui, antes de todos os outros testes. E roda por último, para pegar qualquer teste que
tenha mexido no .env, nas chaves, na memória ou no tmp/."""

import test_sentinela  # noqa: F401  (tira a foto antes de qualquer outro teste ser carregado)


def pytest_collection_modifyitems(session, config, items):
    """Põe os testes da sentinela no fim da fila, sem mudar a ordem dos outros."""
    sentinela = [item for item in items if item.path.name == "test_sentinela.py"]
    if sentinela:
        items[:] = [item for item in items if item.path.name != "test_sentinela.py"] + sentinela
