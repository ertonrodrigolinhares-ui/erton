from datetime import datetime
from unittest.mock import patch

from jarvis import comandos
from jarvis.assistente import remover_palavra_ativacao


def test_hora():
    agora = datetime(2026, 9, 23, 14, 5)
    assert comandos.cmd_hora("que horas sao", agora) == "Agora são 14 horas e 05 minutos."


def test_data():
    agora = datetime(2026, 9, 23, 9, 0)
    assert comandos.cmd_data("que dia e hoje", agora) == "Hoje é quarta-feira, 23 de setembro de 2026."


def test_calcular():
    assert comandos.executar("Calcule 2 mais 3 vezes 4") == "O resultado é 14."
    assert comandos.executar("quanto é 10 dividido por 4?") == "O resultado é 2,5."
    assert comandos.executar("calcule 1500 x 12") == "O resultado é 18000."


def test_calcular_invalido_vai_para_ia():
    assert comandos.executar("calcule o imposto da minha empresa") is None
    assert comandos.executar("calcule 2 ** 99999") is None


def test_abrir_e_pesquisar_abrem_navegador():
    with patch("webbrowser.open") as abrir:
        assert comandos.executar("Abra o YouTube") == "Abrindo youtube."
        assert comandos.executar("pesquise no google holding familiar") == "Pesquisando holding familiar no Google."
        assert comandos.executar("pesquisar no youtube ironman havai") == "Pesquisando ironman havai no YouTube."
        # Sem citar o site, a pesquisa fica com a IA.
        assert comandos.executar("pesquise as notícias da reforma tributária") is None
    assert abrir.call_count == 3


def test_pergunta_livre_nao_e_comando():
    assert comandos.executar("o que é governança corporativa?") is None


def test_palavra_ativacao():
    assert remover_palavra_ativacao("Jarvis, que horas são?", "jarvis") == "que horas sao"
    assert remover_palavra_ativacao("que horas são", "jarvis") == ""
