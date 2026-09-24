import numpy as np
import pytest

from jarvis import voz


def _tom(segundos=0.5):
    t = np.arange(int(voz.TAXA * segundos)) / voz.TAXA
    return (np.sin(2 * np.pi * 220 * t) * 12000).astype(np.int16)


@pytest.mark.parametrize("efeito", ["ultron", "robo"])
def test_efeitos_mudam_o_som_sem_estourar(efeito):
    original = _tom()
    saida = voz.aplicar_efeito(original, efeito)
    assert saida.dtype == np.int16 and len(saida) == len(original)
    assert not np.array_equal(saida, original)
    assert np.max(np.abs(saida.astype(np.int32))) <= 32767 * 0.9 + 1


def test_sem_efeito_e_grave_nao_alteram_amostras():
    original = _tom()
    assert voz.aplicar_efeito(original, "nenhum") is original
    assert voz.aplicar_efeito(original, "grave") is original  # "grave" muda o tom na própria voz


def test_voz_invalida_vira_padrao():
    falador = voz.Falador.__new__(voz.Falador)
    voz.Falador.__init__(falador, voz="inexistente", efeito="xyz")
    assert (falador.voz, falador.efeito) == ("antonio", "nenhum")


def test_elevenlabs_sem_chave_falha_para_usar_reserva():
    falador = voz.Falador(voz="elevenlabs")
    with pytest.raises(RuntimeError):
        falador._gerar("oi")
