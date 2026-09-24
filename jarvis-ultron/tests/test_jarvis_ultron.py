"""Testes dos ajustes do Jarvis Ultron: central de modelos, suspensão e efeito de voz."""

import asyncio
import unittest
from unittest.mock import patch

from core import modelos


def _lista(*nomes, acao="generatecontent"):
    return [(n, {acao}) for n in nomes]


class CentralDeModelosTests(unittest.TestCase):
    def setUp(self):
        modelos._cache = _lista(
            "gemini-2.0-flash", "gemini-2.5-flash", "gemini-3.1-flash", "gemini-3.5-flash-preview",
            "gemini-3.1-flash-lite", "gemini-flash-latest", "gemini-3.1-pro",
            "gemini-3.1-flash-image", "gemini-2.5-flash-image",
        ) + _lista("gemini-3.1-flash-native-audio", acao="bidigeneratecontent")
        self.env = patch.dict("os.environ", {"GEMINI_API_KEY": "x"}, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        modelos._cache = None

    def test_mais_novo_estavel_primeiro_preview_e_antigo_por_ultimo(self):
        self.assertEqual(modelos.candidatos("gemini-2.5-flash"), [
            "gemini-3.1-flash", "gemini-2.5-flash", "gemini-flash-latest",
            "gemini-3.5-flash-preview", "gemini-2.0-flash"])

    def test_categorias(self):
        self.assertEqual(modelos.resolver("gemini-2.5-flash-lite"), "gemini-3.1-flash-lite")
        self.assertEqual(modelos.resolver("gemini-2.5-pro"), "gemini-3.1-pro")
        self.assertEqual(modelos.resolver("gemini-flash-image"), "gemini-3.1-flash-image")
        self.assertEqual(modelos.resolver("models/gemini-2.5-flash-native-audio-preview-12-2025"),
                         "gemini-3.1-flash-native-audio")

    def test_escolha_manual_no_env(self):
        with patch.dict("os.environ", {"JARVIS_MODELO_TEXTO": "gemini-2.5-flash"}):
            self.assertEqual(modelos.resolver("gemini-2.5-flash"), "gemini-2.5-flash")

    def test_sem_lista_usa_o_pedido_e_o_apelido(self):
        modelos._cache = []
        modelos._cache_momento = 10 ** 12
        self.assertEqual(modelos.candidatos("gemini-2.5-flash"), ["gemini-2.5-flash", "gemini-flash-latest"])

    def test_passa_para_o_proximo_quando_acaba_a_cota(self):
        from google.genai import errors

        tentados = []

        def chamar(model, **_):
            tentados.append(model)
            if model == "gemini-3.1-flash":
                raise errors.ClientError(429, {"error": {"message": "quota"}})
            return f"ok {model}"

        self.assertEqual(modelos._com_reserva(chamar, "gemini-2.5-flash", contents="oi"), "ok gemini-2.5-flash")
        self.assertEqual(tentados, ["gemini-3.1-flash", "gemini-2.5-flash"])

    def test_erro_de_outro_tipo_nao_troca_de_modelo(self):
        def chamar(model, **_):
            raise ValueError("pedido inválido")

        with self.assertRaises(ValueError):
            modelos._com_reserva(chamar, "gemini-2.5-flash")


class UIFalsa:
    def __init__(self):
        self.muted = False
        self.logs = []

    def set_muted_threadsafe(self, valor):
        self.muted = valor

    def write_log(self, texto):
        self.logs.append(texto)


class SessaoFalsa:
    def __init__(self):
        self.textos = []

    async def send_client_content(self, turns, turn_complete=True):
        self.textos.append(turns["parts"][0]["text"])


class SuspensaoTests(unittest.TestCase):
    def _jarvis(self):
        import main

        jarvis = object.__new__(main.JarvisLive)
        jarvis.ui, jarvis.session = UIFalsa(), SessaoFalsa()
        return jarvis

    def test_suspende_e_volta_sozinho(self):
        jarvis = self._jarvis()

        async def cenario():
            resposta = jarvis._suspender(10)
            self.assertTrue(jarvis.ui.muted)
            self.assertIn("10 minute", resposta)
            tarefa = jarvis._suspensao
            self.assertAlmostEqual(tarefa.when() - asyncio.get_running_loop().time(), 600, delta=2)
            tarefa.cancel()
            await jarvis._voltar_da_suspensao()  # simula o fim do tempo

        asyncio.run(cenario())
        self.assertFalse(jarvis.ui.muted)
        self.assertIn("de volta", jarvis.session.textos[0])

    def test_nao_avisa_se_o_usuario_ja_religou(self):
        jarvis = self._jarvis()
        asyncio.run(jarvis._voltar_da_suspensao())
        self.assertEqual(jarvis.session.textos, [])

    def test_limita_o_tempo(self):
        jarvis = self._jarvis()

        async def cenario():
            self.assertIn("240 minute", jarvis._suspender(9999))
            jarvis._suspensao.cancel()
            self.assertIn("10 minute", jarvis._suspender("abc"))
            jarvis._suspensao.cancel()

        asyncio.run(cenario())


class EfeitoUltronTests(unittest.TestCase):
    def test_processa_em_pedacos_sem_cortes(self):
        import numpy as np

        from core.efeito_ultron import EfeitoUltron

        audio = (np.sin(2 * np.pi * 200 * np.arange(24000) / 24000) * 10000).astype(np.int16)
        inteiro = EfeitoUltron().processar(audio.tobytes())
        efeito = EfeitoUltron()
        pedacos = b"".join(efeito.processar(audio[i:i + 1000].tobytes()) for i in range(0, 24000, 1000))
        self.assertEqual(pedacos, inteiro)
        self.assertNotEqual(inteiro, audio.tobytes())


if __name__ == "__main__":
    unittest.main()


# ---------- palavra de ativação ----------

import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from core import palavra_ativacao, reserva_groq
from core.palavra_ativacao import PortaoDeVoz

DADOS = Path(__file__).parent / "dados"


def _audio(nome):
    with wave.open(str(DADOS / f"{nome}.wav")) as arquivo:
        fala = np.frombuffer(arquivo.readframes(arquivo.getnframes()), dtype=np.int16)
    silencio = np.zeros(16000, dtype=np.int16)
    return np.concatenate([silencio, fala, silencio])


def _em_blocos(audio, tamanho=1024):
    return [audio[i:i + tamanho] for i in range(0, len(audio), tamanho)]


class Relogio:
    def __init__(self):
        self.agora = 0.0

    def __call__(self):
        return self.agora


class PalavraDeAtivacaoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.detector = palavra_ativacao.carregar_detector()
        except Exception as erro:  # pragma: no cover - depende do openwakeword instalado
            raise unittest.SkipTest(f"openwakeword indisponível: {erro}")

    def setUp(self):
        self.detector.reset()
        self.relogio = Relogio()
        self.avisos = []
        self.portao = PortaoDeVoz(self.detector, janela=20, avisar=self.avisos.append, relogio=self.relogio)

    def _passar(self, audio):
        return [self.portao.processar(b) for b in _em_blocos(audio)]

    def test_hey_jarvis_ativa_e_libera_o_audio(self):
        saidas = self._passar(_audio("hey_jarvis"))
        liberados = [s for s in saidas if s]
        self.assertTrue(liberados, "não detectou o Hey Jarvis")
        self.assertTrue(self.portao.acordado)
        self.assertGreater(len(liberados[0]), 16000)  # inclui o começo (pré-gravação)
        self.assertIn("SYS: Estou ouvindo.", self.avisos)

    def test_frase_comum_nao_ativa_e_nada_vai_para_o_google(self):
        self.assertEqual([s for s in self._passar(_audio("frase_comum")) if s], [])
        self.assertFalse(self.portao.acordado)

    def test_volta_a_dormir_depois_da_janela_e_estender_mantem_acordado(self):
        self._passar(_audio("hey_jarvis"))
        silencio = np.zeros(1024, dtype=np.int16)
        self.relogio.agora = 15
        self.portao.estender()  # ele terminou de falar: mais 20 s
        self.relogio.agora = 30
        self.assertIsNotNone(self.portao.processar(silencio))
        self.relogio.agora = 40
        self.assertIsNone(self.portao.processar(silencio))
        self.assertFalse(self.portao.acordado)
        self.assertIn('SYS: Aguardando "Hey Jarvis".', self.avisos)

    def test_desligado_libera_tudo(self):
        portao = PortaoDeVoz(None, ativo=False)
        bloco = np.ones(1024, dtype=np.int16)
        self.assertEqual(portao.processar(bloco), bloco.tobytes())

    def test_configuracao_pelo_env(self):
        with patch.dict("os.environ", {"JARVIS_PALAVRA_ATIVACAO": "0"}):
            self.assertFalse(PortaoDeVoz.da_configuracao().ativo)
        with patch.dict("os.environ", {"JARVIS_PALAVRA_ATIVACAO": "1", "JARVIS_SENSIBILIDADE": "0.7",
                                       "JARVIS_JANELA_CONVERSA": "12"}):
            portao = PortaoDeVoz.da_configuracao()
            self.assertTrue(portao.ativo)
            self.assertEqual((portao.limiar, portao.janela), (0.7, 12.0))


# ---------- reserva Groq ----------

class SeparaFalasTests(unittest.TestCase):
    def test_entrega_cada_frase_e_ignora_silencio(self):
        silencio = [np.zeros(1280, dtype=np.int16)] * 20
        fala = [np.full(1280, 3000, dtype=np.int16)] * 10
        blocos = silencio + fala + silencio + fala + silencio
        falas = list(reserva_groq.separar_falas(blocos, PortaoDeVoz(None, ativo=False)))
        self.assertEqual(len(falas), 2)
        segundos = len(falas[0]) / 2 / 16000
        self.assertTrue(0.8 < segundos < 3.0, segundos)  # fala + 1,2 s de silêncio final + pré-gravação

    def test_nao_grava_enquanto_o_jarvis_fala(self):
        blocos = [np.full(1280, 3000, dtype=np.int16)] * 10 + [np.zeros(1280, dtype=np.int16)] * 20
        falas = list(reserva_groq.separar_falas(blocos, PortaoDeVoz(None, ativo=False), pode_ouvir=lambda: False))
        self.assertEqual(falas, [])


def _resposta(texto):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=texto))])


class ClienteGroqFalso:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.pedidos, self.arquivos = [], []
        self.models = SimpleNamespace(list=lambda: SimpleNamespace(data=[SimpleNamespace(id="llama-3.3-70b-versatile")]))
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._criar))
        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self._transcrever))

    def _criar(self, **pedido):
        self.pedidos.append({**pedido, "messages": list(pedido["messages"])})
        proxima = self.respostas.pop(0)
        if isinstance(proxima, Exception):
            raise proxima
        return proxima

    def _transcrever(self, file, model, language):
        self.arquivos.append((file, model, language))
        return SimpleNamespace(text=" que horas são ")


class RateLimitError(Exception):
    pass


class ReservaGroqTests(unittest.TestCase):
    def test_responde_e_guarda_a_conversa(self):
        cliente = ClienteGroqFalso([_resposta("Olá, Erton."), _resposta("São dez horas.")])
        reserva = reserva_groq.ReservaGroq("gsk", cliente=cliente)
        self.assertEqual(reserva.responder("oi"), "Olá, Erton.")
        self.assertEqual(reserva.responder("que horas são?"), "São dez horas.")
        self.assertEqual(cliente.pedidos[1]["model"], "llama-3.3-70b-versatile")
        self.assertEqual([m["role"] for m in cliente.pedidos[1]["messages"]], ["system", "user", "assistant", "user"])

    def test_erro_vira_mensagem_e_nao_suja_o_historico(self):
        reserva = reserva_groq.ReservaGroq("gsk", cliente=ClienteGroqFalso([RateLimitError("429")]))
        self.assertIn("limite gratuito do Groq", reserva.responder("oi"))
        self.assertEqual(len(reserva.mensagens), 1)

    def test_transcreve_com_whisper_em_portugues(self):
        cliente = ClienteGroqFalso([])
        texto = reserva_groq.ReservaGroq("gsk", cliente=cliente).transcrever(b"\x00\x00" * 16000)
        self.assertEqual(texto, "que horas são")
        (nome, conteudo), modelo, idioma = cliente.arquivos[0]
        self.assertEqual((nome, modelo, idioma), ("fala.wav", "whisper-large-v3-turbo", "pt"))
        self.assertTrue(conteudo.startswith(b"RIFF"))

    def test_sem_chave_nao_cria_reserva(self):
        with patch.dict("os.environ", {"GROQ_API_KEY": ""}):
            self.assertIsNone(reserva_groq.ReservaGroq.da_configuracao())


class ModoReservaNoJarvisTests(unittest.TestCase):
    def _jarvis(self):
        import main

        jarvis = object.__new__(main.JarvisLive)
        jarvis.ui = UIFalsa()
        jarvis._loop = jarvis.session = None
        jarvis._modo_reserva = False
        jarvis._reserva = reserva_groq.ReservaGroq("gsk", cliente=ClienteGroqFalso([_resposta("Estou aqui.")]))
        jarvis._portao = PortaoDeVoz(None, ativo=False)
        jarvis._shutdown_requested = __import__("threading").Event()
        jarvis.falado = []
        jarvis._falar_reserva = jarvis.falado.append
        return jarvis

    def test_texto_digitado_sem_conexao_vai_para_a_reserva(self):
        jarvis = self._jarvis()
        jarvis._responder_pela_reserva("oi")
        self.assertEqual(jarvis.falado, ["Estou aqui."])
        self.assertIn("Jarvis: Estou aqui.", jarvis.ui.logs)

    def test_liga_e_desliga_o_modo_reserva(self):
        jarvis = self._jarvis()
        with patch.object(type(jarvis), "_escutar_reserva", lambda self: None):
            jarvis._ativar_modo_reserva()
            jarvis._ativar_modo_reserva()  # não liga duas vezes
        self.assertTrue(jarvis._modo_reserva)
        self.assertEqual(sum("Modo reserva (Groq) ligado" in l for l in jarvis.ui.logs), 1)
        jarvis._desativar_modo_reserva()
        self.assertFalse(jarvis._modo_reserva)
