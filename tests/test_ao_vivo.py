import asyncio
import time
from types import SimpleNamespace

import numpy as np
from google.genai import types

from jarvis import ao_vivo, config, voz


def test_escolhe_modelo_de_audio_nativo():
    modelos = [
        SimpleNamespace(name="models/gemini-2.5-flash", supported_actions=["generateContent"]),
        SimpleNamespace(name="models/gemini-live-2.5-flash", supported_actions=["bidiGenerateContent"]),
        SimpleNamespace(name="models/gemini-2.5-flash-native-audio-x", supported_actions=["bidiGenerateContent"]),
    ]
    cliente = SimpleNamespace(models=SimpleNamespace(list=lambda: modelos))
    assert ao_vivo.escolher_modelo(cliente) == "gemini-2.5-flash-native-audio-x"
    assert ao_vivo.escolher_modelo(cliente, "gemini-live-2.5-flash") == "gemini-live-2.5-flash"


def test_efeito_continuo_sem_cortes():
    t = np.arange(24000) / 24000
    audio = (np.sin(2 * np.pi * 200 * t) * 10000).astype(np.int16)
    inteiro = ao_vivo.voz.EfeitoContinuo("ultron").processar(audio.tobytes())
    efeito = voz.EfeitoContinuo("ultron")
    em_pedacos = b"".join(efeito.processar(audio[i:i + 1000].tobytes()) for i in range(0, 24000, 1000))
    assert em_pedacos == inteiro  # processar aos poucos dá o mesmo resultado que tudo junto


# ---------- conversa completa com servidor, microfone e alto-falante simulados ----------

def _mensagem_audio(dados):
    return types.LiveServerMessage(server_content=types.LiveServerContent(model_turn=types.Content(
        parts=[types.Part(inline_data=types.Blob(data=dados, mime_type="audio/pcm;rate=24000"))])))


class SessaoFalsa:
    def __init__(self):
        self.enviados, self.respostas_ferramentas, self.textos = [], [], []
        self.roteiro = [[
            types.LiveServerMessage(server_content=types.LiveServerContent(
                input_transcription=types.Transcription(text="lembre que o aniversário"))),
            types.LiveServerMessage(server_content=types.LiveServerContent(
                input_transcription=types.Transcription(text=" da Yvnna é em maio"))),
            types.LiveServerMessage(tool_call=types.LiveServerToolCall(function_calls=[types.FunctionCall(
                id="c1", name="lembrar_informacao",
                args={"assunto": "aniversário da Yvnna", "informacao": "maio"})])),
            _mensagem_audio(b"\x10\x00" * 2400),
            types.LiveServerMessage(server_content=types.LiveServerContent(
                output_transcription=types.Transcription(text="Pronto, guardei."))),
            types.LiveServerMessage(server_content=types.LiveServerContent(turn_complete=True)),
        ]]

    async def send_client_content(self, turns, turn_complete=True):
        self.textos.append(turns["parts"][0]["text"])

    async def send_realtime_input(self, audio):
        self.enviados.append(audio)

    async def send_tool_response(self, function_responses):
        self.respostas_ferramentas += function_responses

    async def receive(self):
        if not self.roteiro:
            await asyncio.sleep(30)
        for mensagem in self.roteiro.pop(0):
            yield mensagem


class ConexaoFalsa:
    def __init__(self, sessao):
        self.sessao = sessao

    async def __aenter__(self):
        return self.sessao

    async def __aexit__(self, *erro):
        return False


class SomFalso:
    escrito = []

    class RawInputStream:
        def __init__(self, callback, **_):
            self.callback = callback

        def __enter__(self):
            self.callback(b"\x01\x00" * 1024, 1024, None, None)  # alguém falou
            return self

        def __exit__(self, *erro):
            return False

    class RawOutputStream:
        def __init__(self, **_):
            pass

        def start(self):
            pass

        def write(self, dados):
            SomFalso.escrito.append(dados)

        def stop(self):
            pass

        def close(self):
            pass


def test_conversa_ao_vivo_completa(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PASTA_TRABALHO", tmp_path)
    sessao = SessaoFalsa()
    configs = []

    class ClienteFalso:
        def __init__(self, **_):
            self._api_client = None
            self.models = SimpleNamespace(list=lambda: [])
            self.aio = SimpleNamespace(live=SimpleNamespace(
                connect=lambda model, config: (configs.append((model, config)), ConexaoFalsa(sessao))[1]))

    monkeypatch.setattr(ao_vivo.genai, "Client", ClienteFalso)
    monkeypatch.setattr(ao_vivo.types.FunctionDeclaration, "from_callable",
                        classmethod(lambda cls, client, callable: types.FunctionDeclaration(name=callable.__name__)))
    monkeypatch.setattr(voz, "sounddevice", SomFalso)

    from jarvis.ferramentas import criar_ferramentas
    ferramentas = [f for f in criar_ferramentas(lambda *a: True, print) if f.__name__.startswith("lembrar")]
    falas, estados, fim = [], [], []
    vivo = ao_vivo.SessaoAoVivo("chave", "Erton", "Charon", "ultron", ferramentas,
                                ao_texto=lambda q, t: falas.append((q, t)), ao_estado=estados.append,
                                ao_terminar=fim.append)
    vivo.iniciar()
    limite = time.time() + 10
    while len(falas) < 2 and time.time() < limite:
        time.sleep(0.05)
    vivo.parar()
    vivo.thread.join(5)

    assert fim == [None]  # terminou sem erro
    modelo, cfg = configs[0]
    assert modelo == ao_vivo.MODELO_PADRAO
    assert cfg.speech_config.voice_config.prebuilt_voice_config.voice_name == "Charon"
    assert sessao.textos and "Cumprimente" in sessao.textos[0]
    assert sessao.enviados and sessao.enviados[0].mime_type == "audio/pcm;rate=16000"
    assert sessao.respostas_ferramentas[0].id == "c1"
    assert "Guardei na memória" in sessao.respostas_ferramentas[0].response["result"]
    assert "maio" in (tmp_path / "memoria.json").read_text(encoding="utf-8")
    assert falas == [("Você", "lembre que o aniversário da Yvnna é em maio"), ("Jarvis", "Pronto, guardei.")]
    assert SomFalso.escrito and len(SomFalso.escrito[0]) == 4800  # tocou o áudio (com efeito)
