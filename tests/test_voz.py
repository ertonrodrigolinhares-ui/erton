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


def _blocos(sequencia):
    """sequencia: lista de volumes (0 = silêncio); gera blocos de 0,1 s."""
    tamanho = int(voz.TAXA_MICROFONE * voz.BLOCO)
    blocos = iter([np.full(tamanho, v, dtype=np.int16) for v in sequencia] +
                  [np.zeros(tamanho, dtype=np.int16)] * 500)
    return lambda: next(blocos)


def test_captura_so_o_trecho_falado():
    # 0,5 s de calibração, 1 s de silêncio, 2 s de fala, depois silêncio
    audio = voz.capturar_frase(_blocos([50] * 5 + [50] * 10 + [4000] * 20))
    assert audio is not None
    blocos_com_fala = int(np.sum(np.abs(audio) == 4000)) / (voz.TAXA_MICROFONE * voz.BLOCO)
    assert blocos_com_fala == 20
    assert len(audio) / voz.TAXA_MICROFONE < 3.5  # não gravou os 50 s de silêncio


def test_silencio_devolve_none():
    assert voz.capturar_frase(_blocos([50] * 200), espera_max=2) is None


def test_voz_microsoft_decodifica_mp3(monkeypatch):
    import io
    import soundfile

    t = np.arange(24000) / 24000
    buffer = io.BytesIO()
    soundfile.write(buffer, (np.sin(2 * np.pi * 200 * t) * 0.5).astype(np.float32), 24000, format="MP3")

    class ComunicacaoFalsa:
        def __init__(self, texto, voz_id, rate, pitch):
            assert voz_id == "pt-BR-AntonioNeural" and pitch == "-14Hz"

        async def stream(self):
            yield {"type": "audio", "data": buffer.getvalue()}

    monkeypatch.setattr(voz.edge_tts, "Communicate", ComunicacaoFalsa)
    tocados = []
    monkeypatch.setattr(voz, "tocar", lambda amostras, taxa=voz.TAXA: tocados.append(amostras))
    falador = voz.Falador(voz="antonio", efeito="ultron")
    falador.falar("Olá")
    falador.aguardar()
    assert falador.ultimo_erro == ""
    assert len(tocados) == 1 and tocados[0].dtype == np.int16 and len(tocados[0]) > 20000
