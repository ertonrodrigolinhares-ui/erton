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
        # 2.5 está sendo aposentado: fica na reserva, depois dos 3.x (inclusive preview)
        self.assertEqual(modelos.candidatos("gemini-2.5-flash"), [
            "gemini-3.1-flash", "gemini-flash-latest", "gemini-3.5-flash-preview",
            "gemini-2.5-flash", "gemini-2.0-flash"])

    def test_categorias(self):
        self.assertEqual(modelos.resolver("gemini-2.5-flash-lite"), "gemini-3.1-flash-lite")
        self.assertEqual(modelos.resolver("gemini-2.5-pro"), "gemini-3.1-pro")
        self.assertEqual(modelos.resolver("gemini-flash-image"), "gemini-3.1-flash-image")
        self.assertEqual(modelos.resolver("models/gemini-2.5-flash-native-audio-preview-12-2025"),
                         "gemini-3.1-flash-native-audio")

    def test_versao_preferida_3_5_vem_primeiro(self):
        modelos._cache += _lista("gemini-3.5-flash-native-audio-preview", "gemini-3.5-pro-preview",
                                 acao="generatecontent")
        modelos._cache += _lista("gemini-3.5-flash-native-audio-preview", acao="bidigeneratecontent")
        with patch.dict("os.environ", {"JARVIS_GEMINI_VERSAO": "3.5"}):  # sem pedir "versao": rapidez manda
            self.assertEqual(modelos.resolver("gemini-2.5-flash"), "gemini-3.1-flash")
        with patch.dict("os.environ", {"JARVIS_GEMINI_VERSAO": "3.5", "JARVIS_PRIORIDADE": "versao"}):
            self.assertEqual(modelos.resolver("gemini-2.5-flash"), "gemini-3.5-flash-preview")
            self.assertEqual(modelos.resolver("gemini-2.5-pro"), "gemini-3.5-pro-preview")
            self.assertEqual(modelos.resolver("gemini-live-native-audio"), "gemini-3.5-flash-native-audio-preview")
            # sem 3.5 de imagem na chave: segue a escolha normal
            self.assertEqual(modelos.resolver("gemini-flash-image"), "gemini-3.1-flash-image")
            self.assertIn("gemini-3.5-flash-preview", modelos.resumo())
        with patch.dict("os.environ", {"JARVIS_GEMINI_VERSAO": "3,5", "JARVIS_PRIORIDADE": "versao"}):
            self.assertEqual(modelos.versao_preferida(), 3.5)
        self.assertEqual(modelos.resolver("gemini-2.5-flash"), "gemini-3.1-flash")  # sem preferência

    def test_rapidez_prefere_voz_estavel_a_preview(self):
        modelos._cache += _lista("gemini-3.5-flash-native-audio-preview", "gemini-2.5-flash-native-audio",
                                 acao="bidigeneratecontent")
        self.assertEqual(modelos.prioridade(), "rapidez")
        vivos = modelos.candidatos("gemini-live-native-audio")
        self.assertEqual(vivos[0], "gemini-3.1-flash-native-audio")  # estável e mais novo
        # o 2.5 (aposentando) fica depois até do 3.5 preview
        self.assertLess(vivos.index("gemini-3.5-flash-native-audio-preview"),
                        vivos.index("gemini-2.5-flash-native-audio"))

    def test_voz_3x_antes_do_2_5_mesmo_sem_audio_nativo_e_troca_quando_falha(self):
        modelos._cache = _lista("gemini-2.5-flash-native-audio-preview-12-2025", "gemini-3.1-flash-live-preview",
                                "gemini-3.5-flash-live-preview", acao="bidigeneratecontent")
        modelos._falharam.clear()
        with patch.dict("os.environ", {"JARVIS_PRIORIDADE": "rapidez"}):
            self.assertEqual(modelos.candidatos("gemini-live-native-audio"), [
                "gemini-3.5-flash-live-preview", "gemini-3.1-flash-live-preview",
                "gemini-2.5-flash-native-audio-preview-12-2025"])
            modelos.pular("models/gemini-3.5-flash-live-preview")  # a voz não conectou nele
            self.assertEqual(modelos.resolver("gemini-live-native-audio"), "gemini-3.1-flash-live-preview")
            modelos.pular("gemini-3.1-flash-live-preview")
            self.assertEqual(modelos.resolver("gemini-live-native-audio"),
                             "gemini-2.5-flash-native-audio-preview-12-2025")
            modelos.pular("gemini-2.5-flash-native-audio-preview-12-2025")  # todos falharam: recomeça
            self.assertEqual(modelos.resolver("gemini-live-native-audio"), "gemini-3.5-flash-live-preview")
        modelos._falharam.clear()

    def test_erro_de_modelo_indisponivel(self):
        import main
        self.assertTrue(main._modelo_indisponivel(RuntimeError("models/x is not found for API version v1beta")))
        self.assertTrue(main._modelo_indisponivel(RuntimeError("1008 policy violation: model deprecated")))
        self.assertFalse(main._modelo_indisponivel(OSError("Temporary failure in name resolution")))

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

        self.assertEqual(modelos._com_reserva(chamar, "gemini-2.5-flash", contents="oi"), "ok gemini-flash-latest")
        self.assertEqual(tentados, ["gemini-3.1-flash", "gemini-flash-latest"])

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
                                       "JARVIS_JANELA_CONVERSA": "12", "JARVIS_ATIVACAO": "voz"}):
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


# ---------- Hermes: trava de aprovação, ponte e kit ----------

import importlib.util
import json as _json
import subprocess
import sys
import time as _time

from core import hermes_ponte

KIT = Path(__file__).resolve().parent.parent / "hermes"


def _carregar_gancho():
    spec = importlib.util.spec_from_file_location("aprovacao_jarvis", KIT / "hooks" / "aprovacao_jarvis.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class TravaDeAprovacaoTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.pasta = Path(tempfile.mkdtemp())
        self.env = patch.dict("os.environ", {"HERMES_HOME": str(self.pasta), "HERMES_JARVIS_HOME": str(self.pasta),
                                             "HERMES_API_KEY": "chave"})
        self.env.start()
        self.gancho = _carregar_gancho()

    def tearDown(self):
        self.env.stop()

    def _evento(self, ferramenta):
        return {"hook_event_name": "pre_tool_call", "tool_name": ferramenta, "tool_input": {}}

    def test_leitura_passa_e_publicacao_e_bloqueada_sem_ok(self):
        self.assertIsNone(self.gancho.decidir(self._evento("mcp__metricool__get_posts")))
        self.assertIsNone(self.gancho.decidir(self._evento("mcp__metricool__best_time_to_post")))
        bloqueio = self.gancho.decidir(self._evento("mcp__metricool__create_post"))
        self.assertEqual(bloqueio["action"], "block")
        self.assertIn("ok", bloqueio["message"])
        self.assertEqual(self.gancho.decidir(self._evento("mcp__meta_ads__update_budget"))["action"], "block")

    def test_outras_ferramentas_nao_sao_afetadas(self):
        self.assertIsNone(self.gancho.decidir(self._evento("terminal")))
        self.assertIsNone(self.gancho.decidir(self._evento("mcp__github__create_issue")))

    def test_ok_do_jarvis_libera_so_a_categoria_e_so_por_10_minutos(self):
        hermes_ponte.registrar_aprovacao("redes")
        self.assertIsNone(self.gancho.decidir(self._evento("mcp__metricool__create_post")))
        self.assertEqual(self.gancho.decidir(self._evento("mcp__meta_ads__create_campaign"))["action"], "block")
        depois = _time.time() + hermes_ponte.JANELA_APROVACAO + 1
        self.assertEqual(self.gancho.decidir(self._evento("mcp__metricool__create_post"), agora=depois)["action"], "block")

    def test_script_segue_o_protocolo_do_hermes(self):
        entrada = _json.dumps(self._evento("mcp__metricool__schedule_post"))
        saida = subprocess.run([sys.executable, str(KIT / "hooks" / "aprovacao_jarvis.py")], input=entrada,
                               capture_output=True, text=True, timeout=30)
        self.assertEqual(_json.loads(saida.stdout)["action"], "block")
        leitura = subprocess.run([sys.executable, str(KIT / "hooks" / "aprovacao_jarvis.py")],
                                 input=_json.dumps(self._evento("mcp__metricool__get_posts")),
                                 capture_output=True, text=True, timeout=30)
        self.assertEqual(leitura.stdout.strip(), "")

    def test_aprovacao_exige_ok_na_fala_do_usuario(self):
        with patch.object(hermes_ponte, "perguntar", return_value="Publicado.") as pedido:
            self.assertIn("Não registrei", hermes_ponte.aprovar_e_executar("redes", "posts 1 e 3", "quais os posts de hoje?"))
            self.assertIn("Não registrei", hermes_ponte.aprovar_e_executar("redes", "posts 1", "não pode publicar"))
            pedido.assert_not_called()
            self.assertFalse(hermes_ponte.arquivo_aprovacao().exists())
            self.assertEqual(hermes_ponte.aprovar_e_executar("redes", "posts 1 e 3", "ok, pode publicar o 1 e o 3"), "Publicado.")
            self.assertIn("publicar-aprovados", pedido.call_args.args[0])
        self.assertIsNone(self.gancho.decidir(self._evento("mcp__metricool__create_post")))


class RespostaHttp:
    def __init__(self, status, dados=None, texto=""):
        self.status_code, self._dados, self.text = status, dados, texto

    def json(self):
        return self._dados


class PonteHermesTests(unittest.TestCase):
    def test_pergunta_pela_api_local(self):
        import requests

        chamadas = []

        def post(url, headers, json, timeout):
            chamadas.append((url, headers, json))
            return RespostaHttp(200, {"choices": [{"message": {"content": " Preparei 3 posts. "}}]})

        with patch.dict("os.environ", {"HERMES_API_KEY": "k", "HERMES_API_URL": "http://127.0.0.1:8642/"}), \
                patch.object(requests, "post", post):
            self.assertEqual(hermes_ponte.perguntar("quais os posts de hoje?"), "Preparei 3 posts.")
        url, cabecalho, corpo = chamadas[0]
        self.assertEqual(url, "http://127.0.0.1:8642/v1/chat/completions")
        self.assertEqual(cabecalho["Authorization"], "Bearer k")
        self.assertEqual(corpo["model"], "hermes-agent")

    def test_erros_viram_mensagens(self):
        import requests

        with patch.dict("os.environ", {"HERMES_API_KEY": "k"}):
            with patch.object(requests, "post", side_effect=requests.exceptions.ConnectionError()):
                self.assertIn("desligado", hermes_ponte.perguntar("oi"))
            with patch.object(requests, "post", return_value=RespostaHttp(401)):
                self.assertIn("não reconheceu o Jarvis", hermes_ponte.perguntar("oi"))
        with patch.dict("os.environ", {"HERMES_API_KEY": ""}):
            self.assertIn("Instalar Hermes", hermes_ponte.perguntar("oi"))


class VozElevenLabsTests(unittest.TestCase):
    def test_fala_a_resposta_pela_voz_externa(self):
        import main

        class Motor:
            def __init__(self):
                self.falas = []

            def speak(self, texto):
                self.falas.append(texto)

        jarvis = object.__new__(main.JarvisLive)
        jarvis.ui = UIFalsa()
        jarvis._tts_engine, jarvis._ext_tts_provider = Motor(), "elevenlabs"
        jarvis._falar_com_voz_externa("Bom dia, Erton.")
        self.assertEqual(jarvis._tts_engine.falas, ["Bom dia, Erton."])
        jarvis._ext_tts_provider = "gemini"
        jarvis._falar_com_voz_externa("não deve falar")
        self.assertEqual(len(jarvis._tts_engine.falas), 1)


class KitHermesTests(unittest.TestCase):
    def test_config_e_skills_validos(self):
        import yaml

        config = yaml.safe_load((KIT / "config-jarvis.yaml").read_text(encoding="utf-8"))
        self.assertEqual(config["model"]["provider"], "nous")  # cérebro grátis
        self.assertTrue(config["model"]["default"].endswith(":free"))
        self.assertTrue(all(r["model"].endswith(":free") for r in config["fallback_providers"]))
        self.assertNotIn("provider", config["delegation"])  # sub-agentes herdam o cérebro grátis
        self.assertEqual(set(config["mcp_servers"]), {"metricool"})  # Meta Ads: conector oficial não aceita o Hermes
        gancho = config["hooks"]["pre_tool_call"][0]
        self.assertTrue(gancho["fail_closed"])
        self.assertRegex("mcp__metricool__create_post", gancho["matcher"])
        habilidades = list((KIT / "skills" / "jarvis").glob("*/SKILL.md")) + \
            list((KIT / "agentes-futuros").glob("*/SKILL.md"))
        self.assertGreaterEqual(len(habilidades), 17)
        for skill in habilidades:
            frente = yaml.safe_load(skill.read_text(encoding="utf-8").split("---")[1])
            self.assertEqual(frente["name"], skill.parent.name)
            self.assertTrue(frente["description"])


# ---------- modos de escuta: mãos livres / chamada ----------

class ModosDeEscutaTests(unittest.TestCase):
    def setUp(self):
        try:
            self.detector = palavra_ativacao.carregar_detector()
        except Exception as erro:  # pragma: no cover
            raise unittest.SkipTest(f"openwakeword indisponível: {erro}")
        self.detector.reset()

    def _jarvis(self, portao):
        import main

        jarvis = object.__new__(main.JarvisLive)
        jarvis.ui = UIFalsa()
        jarvis._portao = portao
        return jarvis

    def test_reconhece_as_frases(self):
        self.assertEqual(palavra_ativacao.modo_pedido("Hey Jarvis, modo mãos livres"), "maos_livres")
        self.assertEqual(palavra_ativacao.modo_pedido("Jarvis, modo chamada"), "chamada")
        self.assertIsNone(palavra_ativacao.modo_pedido("que horas são?"))

    def test_maos_livres_libera_tudo_e_chamada_volta_a_esperar_hey_jarvis(self):
        portao = PortaoDeVoz(self.detector)
        frase = _audio("frase_comum")
        self.assertEqual([s for s in (portao.processar(b) for b in _em_blocos(frase)) if s], [])

        jarvis = self._jarvis(portao)
        jarvis._checar_pedido_de_modo("Hey Jarvis, modo mãos livres")
        self.assertEqual(portao.modo, "maos_livres")
        self.assertIn("SYS: Modo mãos livres: estou ouvindo tudo.", jarvis.ui.logs)
        self.assertTrue(all(portao.processar(b) for b in _em_blocos(frase)))

        resposta = jarvis._definir_modo_escuta("chamada")
        self.assertIn("do not announce", resposta)  # o som e o selo já avisam
        self.assertEqual(portao.modo, "chamada")
        self.assertFalse(portao.acordado)
        self.assertEqual([s for s in (portao.processar(b) for b in _em_blocos(frase)) if s], [])
        self.assertIn("Say nothing", jarvis._definir_modo_escuta("chamada"))

    def test_chamada_indisponivel_sem_detector(self):
        jarvis = self._jarvis(PortaoDeVoz(None, ativo=False))
        self.assertIn("unavailable", jarvis._definir_modo_escuta("chamada"))
        self.assertEqual(jarvis._portao.modo, "maos_livres")


# ---------- tela Stark ----------

class TelaStarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_monta_painel_atualiza_dados_e_botoes_mandam_comandos(self):
        import tempfile

        from PyQt6.QtWidgets import QWidget

        import ui_stark

        comandos = []
        with patch.object(ui_stark.TelaStark, "_buscar_da_internet", lambda self: None):
            tela = ui_stark.TelaStark(QWidget(), comandos.append, pasta_dados=Path(tempfile.mkdtemp()))
        tela._a_cada_segundo()
        self.assertIn("Tempo ligado", tela.ligado.text())
        self.assertTrue(tela.cpu.texto.endswith("%"))
        self.assertEqual(len(tela.botoes), len(ui_stark.BOTOES))
        tela.botoes[0].click()
        self.assertEqual(comandos, ["quais são os posts de hoje?"])

    def test_notas_ficam_salvas(self):
        import tempfile

        from PyQt6.QtWidgets import QWidget

        import ui_stark

        pasta = Path(tempfile.mkdtemp())
        with patch.object(ui_stark.TelaStark, "_buscar_da_internet", lambda self: None):
            tela = ui_stark.TelaStark(QWidget(), lambda texto: None, pasta_dados=pasta)
            tela.notas.setPlainText("treino de bike às 6h")
            tela._gravar_notas()
            outra = ui_stark.TelaStark(QWidget(), lambda texto: None, pasta_dados=pasta)
        self.assertEqual(outra.notas.toPlainText(), "treino de bike às 6h")

    def test_noticias_e_clima_sem_internet_nao_quebram(self):
        from PyQt6.QtWidgets import QWidget

        import ui_stark

        with patch.object(ui_stark.TelaStark, "_buscar_da_internet", lambda self: None):
            tela = ui_stark.TelaStark(QWidget(), lambda texto: None)
        tela._mostrar_noticias([])
        tela._mostrar_noticias([("Manchete de teste", "https://example.com")])
        self.assertEqual(tela.noticias.count(), 1)

    def test_pode_desligar_pelo_env(self):
        import ui_stark

        with patch.dict("os.environ", {"JARVIS_TEMA_STARK": "0"}):
            self.assertFalse(ui_stark.ligada())
        with patch.dict("os.environ", {"JARVIS_TEMA_STARK": "1"}):
            self.assertTrue(ui_stark.ligada())


class NavegadorPlanoBTests(unittest.TestCase):
    """Se o navegador automático não abrir (ex.: Firefox), o site abre no navegador normal."""

    def _sessao_que_falha(self, nome, exe=None):
        from actions import browser_control as bc

        class Sessao:
            browser_name = nome
            _spec = {"engine": "firefox", "exe": exe, "channel": None}
            _context = None
            _loop = None

            def go_to(self, url):
                return url

            search = new_tab = go_to

            def run(self, coro, timeout=60):
                raise RuntimeError("Executable doesn't exist")

            def close(self):
                pass

        sess = Sessao()
        bc._registry._sessions[nome] = sess
        return bc, sess

    def test_firefox_abre_o_site_no_firefox_normal(self):
        bc, _ = self._sessao_que_falha("firefox", exe="C:/Firefox/firefox.exe")
        with patch.object(bc._registry, "get", return_value=bc._registry._sessions["firefox"]), \
                patch.object(bc.subprocess, "Popen") as popen:
            resultado = bc.browser_control({"action": "go_to", "url": "instagram", "browser": "firefox"})
        popen.assert_called_once_with(["C:/Firefox/firefox.exe", "https://instagram.com"])
        self.assertIn("Opened https://instagram.com in firefox", resultado)
        self.assertNotIn("firefox", bc._registry._sessions)  # tenta de novo da próxima vez

    def test_sem_executavel_usa_o_navegador_padrao(self):
        bc, sess = self._sessao_que_falha("chrome")
        with patch.object(bc._registry, "get", return_value=sess), \
                patch("webbrowser.open", return_value=True) as abrir:
            resultado = bc.browser_control({"action": "search", "query": "ironman 70.3", "browser": "chrome"})
        abrir.assert_called_once_with("https://www.google.com/search?q=ironman+70.3")
        self.assertIn("navegador padrão", resultado)

    def test_clique_nao_abre_nada_por_fora(self):
        bc, sess = self._sessao_que_falha("chrome")
        with patch.object(bc._registry, "get", return_value=sess), \
                patch("webbrowser.open") as abrir:
            resultado = bc.browser_control({"action": "click", "text": "Entrar", "browser": "chrome"})
        abrir.assert_not_called()
        self.assertIn("Browser error (click)", resultado)
        bc._registry._sessions.pop("chrome", None)


def _silencio(segundos, nivel=40):
    rng = np.random.default_rng(3)
    return rng.integers(-nivel, nivel, int(16000 * segundos)).astype(np.int16)


class AvisoDeModoTests(unittest.TestCase):
    def test_avisa_cada_mudanca_de_estado(self):
        try:
            detector = palavra_ativacao.carregar_detector()
        except Exception as erro:  # pragma: no cover
            raise unittest.SkipTest(f"openwakeword indisponível: {erro}")
        portao = PortaoDeVoz(detector)
        estados = []
        portao.ao_mudar = estados.append
        for b in _em_blocos(_audio("hey_jarvis")):
            portao.processar(b)
        self.assertTrue(portao.acordado)
        portao.definir_modo("maos_livres")
        portao.definir_modo("chamada")
        self.assertEqual(estados, ["ouvindo", "maos_livres", "aguardando"])

    def test_aviso_com_erro_nao_derruba_o_microfone(self):
        portao = PortaoDeVoz(object())
        portao.ao_mudar = lambda estado: 1 / 0
        self.assertTrue(portao.definir_modo("maos_livres"))
        self.assertEqual(portao.modo, "maos_livres")


class SilencioComChamadaFechadaTests(unittest.TestCase):
    def _jarvis(self, acordado):
        import main
        jarvis = object.__new__(main.JarvisLive)
        jarvis.ui = UIFalsa()
        jarvis._portao = PortaoDeVoz(object())
        jarvis._portao.acordado = acordado
        return jarvis

    def test_chamada_fechada_nao_cumprimenta_nem_fala(self):
        jarvis = self._jarvis(acordado=False)
        self.assertTrue(jarvis._chamada_fechada())

        class Sessao:
            enviados = []

            async def send_client_content(self, **kw):
                self.enviados.append(kw)

        jarvis.session = Sessao()
        asyncio.run(jarvis._announce_startup())
        self.assertEqual(Sessao.enviados, [])

    def test_cumprimenta_uma_vez_so(self):
        jarvis = self._jarvis(acordado=True)
        self.assertFalse(jarvis._chamada_fechada())

        class Sessao:
            enviados = []

            async def send_client_content(self, **kw):
                self.enviados.append(kw)

        jarvis.session = Sessao()
        with patch("main.load_memory", return_value={}):
            asyncio.run(jarvis._announce_startup())
            asyncio.run(jarvis._announce_startup())  # reconexão
        self.assertEqual(len(Sessao.enviados), 1)


class IdiomaTests(unittest.TestCase):
    def test_instrucoes_mandam_falar_portugues_e_voz_pt_br(self):
        import main
        jarvis = object.__new__(main.JarvisLive)
        jarvis.voice_name = "charon"
        with patch("main.load_memory", return_value={}), patch.object(main.JarvisLive, "_get_current_voice", return_value="charon"):
            config = jarvis._build_config()
        texto = config.system_instruction if isinstance(config.system_instruction, str) else str(config.system_instruction)
        self.assertTrue(texto.startswith("[IDIOMA"))
        self.assertTrue(texto.rstrip().endswith(main.REGRA_IDIOMA.rstrip()))
        self.assertEqual(config.speech_config.language_code, "pt-BR")
        jarvis._idioma_recusado = True  # modelo que não aceita escolher o idioma
        with patch("main.load_memory", return_value={}), patch.object(main.JarvisLive, "_get_current_voice", return_value="charon"):
            self.assertIsNone(jarvis._build_config().speech_config.language_code)

    def test_raciocinio_da_voz_por_modelo(self):
        import main
        tres = main._pensamento_da_voz("gemini-3.1-flash-live-preview")
        self.assertIsNone(tres.thinking_budget)  # 3.x recusa thinking_budget=0 (erro 1007)
        self.assertEqual(str(getattr(tres.thinking_level, "value", tres.thinking_level)), "LOW")
        self.assertEqual(main._pensamento_da_voz("gemini-2.5-flash-native-audio-preview-12-2025").thinking_budget, 0)
        jarvis = object.__new__(main.JarvisLive)
        jarvis.voice_name = "charon"
        with patch("main.load_memory", return_value={}), patch.object(main.JarvisLive, "_get_current_voice", return_value="charon"):
            self.assertIsNone(jarvis._build_config("gemini-3.5-flash-live-preview").thinking_config.thinking_budget)

    def test_acha_o_erro_1007_dentro_do_grupo(self):
        import main
        from google.genai import errors
        erro = errors.APIError(1007, {"error": {"message": "Request contains an invalid argument."}})
        grupo = ExceptionGroup("tarefas", [RuntimeError("outra"), ExceptionGroup("dentro", [erro])])
        self.assertIs(main._erro_da_api(grupo), erro)
        self.assertIsNone(main._erro_da_api(RuntimeError("sem internet")))

    def test_desligar_em_portugues(self):
        import main
        jarvis = object.__new__(main.JarvisLive)
        self.assertTrue(jarvis._is_explicit_self_quit_transcript("desliga o Jarvis"))
        self.assertTrue(jarvis._is_explicit_self_quit_transcript("Jarvis, saia do ar"))
        self.assertFalse(jarvis._is_explicit_self_quit_transcript("Jarvis, desligar palmas"))
        self.assertIn("Até a próxima", main.SELF_QUIT_GOODBYE)


class BotoesDeModoTests(unittest.TestCase):
    def test_botao_troca_o_modo_na_hora_sem_ir_para_a_ia(self):
        import main
        jarvis = object.__new__(main.JarvisLive)
        jarvis.ui = UIFalsa()
        jarvis._portao = PortaoDeVoz(object())
        jarvis._loop = jarvis.session = None
        jarvis._reserva = None
        with patch.object(main.JarvisLive, "_aviso_de_escuta") as aviso:
            jarvis._portao.ao_mudar = lambda estado: jarvis._aviso_de_escuta(estado)  # como no __init__
            jarvis._on_text_command("modo mãos livres")
            self.assertEqual(jarvis._portao.modo, "maos_livres")
            jarvis._on_text_command("Jarvis, modo chamada")
            self.assertEqual(jarvis._portao.modo, "chamada")
        self.assertTrue(aviso.called)


class HermesSemTravarTests(unittest.TestCase):
    def _jarvis(self):
        import main
        jarvis = object.__new__(main.JarvisLive)
        jarvis.ui = UIFalsa()
        jarvis._portao = PortaoDeVoz(object(), ativo=False)  # mãos livres: pode falar
        return jarvis

    def test_resposta_rapida_volta_direto(self):
        jarvis = self._jarvis()
        with patch("core.hermes_ponte.perguntar", return_value="3 posts prontos"):
            self.assertEqual(asyncio.run(jarvis._hermes_sem_travar("posts de hoje")), "3 posts prontos")

    def test_tarefa_longa_nao_trava_e_entrega_depois(self):
        import time as _time
        jarvis = self._jarvis()
        jarvis.HERMES_ESPERA = 0.2
        enviados = []

        class Sessao:
            async def send_client_content(self, **kw):
                enviados.append(kw)

        def devagar(pedido):
            _time.sleep(0.6)
            return "relatório pronto"

        async def cenario():
            jarvis.session, jarvis._loop = Sessao(), asyncio.get_running_loop()
            inicio = _time.monotonic()
            resposta = await jarvis._hermes_sem_travar("relatório de anúncios")
            self.assertLess(_time.monotonic() - inicio, 0.5)  # não esperou a tarefa inteira
            self.assertIn("still working", resposta)
            await asyncio.sleep(0.8)

        with patch("core.hermes_ponte.perguntar", side_effect=devagar):
            asyncio.run(cenario())
        self.assertTrue(any("relatório pronto" in l for l in jarvis.ui.logs))
        self.assertEqual(len(enviados), 1)
        self.assertIn("relatório pronto", enviados[0]["turns"]["parts"][0]["text"])


class HermesEnderecoTests(unittest.TestCase):
    def test_procura_o_perfil_jarvis_no_servico_unico(self):
        from core import hermes_ponte
        with patch.dict("os.environ", {"HERMES_API_URL": "http://127.0.0.1:8642"}):
            self.assertEqual(hermes_ponte.enderecos(),
                             ["http://127.0.0.1:8642", "http://127.0.0.1:8642/p/jarvis"])
        with patch.dict("os.environ", {"HERMES_API_URL": "http://127.0.0.1:8642/p/jarvis/"}):
            self.assertEqual(hermes_ponte.enderecos(),
                             ["http://127.0.0.1:8642/p/jarvis", "http://127.0.0.1:8642"])

    def test_pula_endereco_errado_e_usa_o_certo(self):
        import requests
        from core import hermes_ponte

        class Resp:
            def __init__(self, codigo, texto=""):
                self.status_code, self.text = codigo, texto

            def json(self):
                return {"choices": [{"message": {"content": "3 posts prontos"}}]}

        chamados = []

        def post(url, **kw):
            chamados.append(url)
            if "/p/jarvis" in url:
                return Resp(200)
            return Resp(401)

        with patch.dict("os.environ", {"HERMES_API_URL": "http://127.0.0.1:8642", "HERMES_API_KEY": "k" * 20}), \
                patch.object(requests, "post", side_effect=post):
            self.assertEqual(hermes_ponte.perguntar("posts"), "3 posts prontos")
        self.assertEqual(chamados[-1], "http://127.0.0.1:8642/p/jarvis/v1/chat/completions")

        def desligado(url, **kw):
            raise requests.exceptions.ConnectionError()

        with patch.dict("os.environ", {"HERMES_API_KEY": "k" * 20}), patch.object(requests, "post", side_effect=desligado):
            self.assertIn("desligado", hermes_ponte.perguntar("posts"))


class EnvArquivoTests(unittest.TestCase):
    def test_troca_so_a_linha_da_chave(self):
        import tempfile
        from pathlib import Path
        from core.env_arquivo import atualizar_env
        arquivo = Path(tempfile.mkdtemp()) / ".env"
        arquivo.write_text('GEMINI_API_KEY="velha"\nJARVIS_CIDADE=João Pessoa\nGROQ_API_KEY="g"\n', encoding="utf-8")
        atualizar_env(arquivo, "GEMINI_API_KEY", "AQ.nova-chave_123")
        texto = arquivo.read_text(encoding="utf-8")
        self.assertIn('GEMINI_API_KEY="AQ.nova-chave_123"', texto)
        self.assertNotIn("velha", texto)
        self.assertIn("JARVIS_CIDADE=João Pessoa", texto)
        self.assertIn('GROQ_API_KEY="g"', texto)
        atualizar_env(arquivo, "NOVA", "x")
        self.assertTrue(arquivo.read_text(encoding="utf-8").rstrip().endswith('NOVA="x"'))

    def test_chave_nova_do_google_passa_na_conferencia_basica(self):
        from core.api_key_validator import _basic_key_check, normalize_gemini_api_key
        chave = "AQ.ExemploFalso0000000000000000000000"
        self.assertEqual(normalize_gemini_api_key(f'GEMINI_API_KEY="{chave}"'), chave)
        self.assertIsNone(_basic_key_check(chave))


class ReservaNaTelaDaChaveTests(unittest.TestCase):
    def test_chave_recusada_mostra_botao_da_reserva_e_abre(self):
        import os
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        import ui
        with patch.dict("os.environ", {"GROQ_API_KEY": "gsk_teste", "GEMINI_API_KEY": ""}):
            tela = ui.SetupOverlay()
            self.assertTrue(tela._reserva_btn.isHidden())
            tela._on_validation_finished(False, "API key was rejected by Gemini.", "AQ.xxxxxxxxxxxxxxxxxxxxxxxx", False)
            self.assertFalse(tela._reserva_btn.isHidden())
            recebido = []
            tela.done.connect(lambda chave, so, lembrar: recebido.append((chave, lembrar)))
            tela._key_input.setText("AQ.xxxxxxxxxxxxxxxxxxxxxxxx")
            tela._continuar_com_reserva()
            self.assertEqual(recebido, [("AQ.xxxxxxxxxxxxxxxxxxxxxxxx", False)])
            self.assertTrue(tela._modo_reserva)

    def test_sem_groq_nao_mostra_o_botao(self):
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        import ui
        with patch.dict("os.environ", {"GROQ_API_KEY": ""}):
            tela = ui.SetupOverlay()
            tela._on_validation_finished(False, "API key was rejected by Gemini.", "AQ.x" * 6, False)
            self.assertTrue(tela._reserva_btn.isHidden())


class VozDaReservaTests(unittest.TestCase):
    def _jarvis(self):
        import main
        jarvis = object.__new__(main.JarvisLive)
        jarvis.ui = UIFalsa()
        jarvis._speaking_lock = __import__("threading").Lock()
        jarvis._is_speaking = False
        jarvis.set_speaking = lambda valor: None
        jarvis._mostrar_volume = lambda pcm: None
        return jarvis

    def test_se_a_voz_da_internet_falha_usa_a_do_windows(self):
        jarvis = self._jarvis()
        with patch("actions.tts_engine.TTSEngine.speak_sync", return_value=False), \
                patch("actions.tts_engine.falar_com_voz_do_windows", return_value=True) as windows:
            jarvis._falar_reserva("Bom dia, senhor.")
        windows.assert_called_once_with("Bom dia, senhor.")

    def test_voz_da_internet_ok_nao_chama_a_do_windows(self):
        jarvis = self._jarvis()
        with patch("actions.tts_engine.TTSEngine.speak_sync", return_value=True), \
                patch("actions.tts_engine.falar_com_voz_do_windows") as windows:
            jarvis._falar_reserva("Bom dia.")
        windows.assert_not_called()

    def test_voz_do_windows_fora_do_windows_nao_quebra(self):
        from actions.tts_engine import falar_com_voz_do_windows
        with patch("os.name", "posix"):
            self.assertFalse(falar_com_voz_do_windows("oi"))


class AutodiagnosticoTests(unittest.TestCase):
    def test_reconhece_o_pedido(self):
        from core.autodiagnostico import pediu_diagnostico
        for frase in ("faça um autodiagnóstico do sistema", "Jarvis, diagnóstico", "o que está com defeito?",
                      "verifique seu sistema"):
            self.assertTrue(pediu_diagnostico(frase), frase)
        self.assertFalse(pediu_diagnostico("que horas são?"))

    def test_relatorio_e_resumo_falado(self):
        from core.autodiagnostico import Item, relatorio, resumo_falado, salvar
        import tempfile
        itens = [Item("Internet", "ok", "conectado"),
                 Item("Hermes (agentes)", "defeito", "o Hermes está desligado", "Dê dois cliques em 'Ligar Hermes'."),
                 Item("Computador", "atencao", "memória 88%", "Feche abas.")]
        texto = relatorio(itens)
        self.assertIn("[DEFEITO] Hermes (agentes): o Hermes está desligado", texto)
        self.assertIn("→ Dê dois cliques em 'Ligar Hermes'.", texto)
        falado = resumo_falado(itens)
        self.assertIn("encontrei 2 pontos", falado)
        self.assertLess(falado.index("Hermes"), falado.index("Computador"))  # defeito antes de atenção
        self.assertIn("tudo funcionando", resumo_falado([Item("Internet", "ok", "conectado")]))
        arquivo = salvar(texto, tempfile.mkdtemp())
        self.assertEqual(arquivo.read_text(encoding="utf-8").strip(), texto.strip())

    def test_hermes_desligado_e_sem_chaves(self):
        import requests
        from core import autodiagnostico as ad

        def recusa(*a, **k):
            raise requests.exceptions.ConnectionError()

        with patch.dict("os.environ", {"HERMES_API_KEY": "k" * 20, "GROQ_API_KEY": ""}), \
                patch.object(requests, "get", side_effect=recusa):
            hermes = ad.verificar_hermes()
            groq = ad.verificar_groq()
        self.assertEqual((hermes.estado, groq.estado), ("defeito", "atencao"))
        self.assertIn("Ligar Hermes", hermes.dica)

    def test_chave_aq_recusada_vira_dica_certa(self):
        from core import autodiagnostico as ad

        class Cliente:
            def __init__(self, **kw):
                self.models = self

            def list(self):
                raise RuntimeError("401 UNAUTHENTICATED ... ACCESS_TOKEN_TYPE_UNSUPPORTED")

        with patch.dict("os.environ", {"GEMINI_API_KEY": "AQ.ExemploFalso0000000000000000"}), \
                patch("google.genai.Client", Cliente):
            item = ad.verificar_gemini()
        self.assertEqual(item.estado, "defeito")
        self.assertIn("outro Gmail", item.dica)

    def test_uma_verificacao_quebrada_nao_derruba_as_outras(self):
        from core import autodiagnostico as ad
        with patch.object(ad, "verificar_internet", side_effect=RuntimeError("boom")), \
                patch.object(ad, "verificar_gemini", return_value=ad.Item("Chave do Gemini", "ok", "x")), \
                patch.object(ad, "verificar_groq", return_value=ad.Item("Reserva Groq", "ok", "x")), \
                patch.object(ad, "verificar_hermes", return_value=ad.Item("Hermes (agentes)", "ok", "x")), \
                patch.object(ad, "verificar_modelos", return_value=ad.Item("Modelos do Gemini", "ok", "x")):
            itens = ad.diagnosticar(None)
        nomes = [i.nome for i in itens]
        self.assertIn("Internet", nomes)
        self.assertEqual(itens[0].estado, "atencao")
        self.assertIn("Computador", nomes)

    def test_botao_sem_gemini_roda_local(self):
        import main
        jarvis = object.__new__(main.JarvisLive)
        jarvis.ui = UIFalsa()
        jarvis._portao = PortaoDeVoz(object())
        jarvis.session = None
        jarvis._reserva = None
        with patch.object(main.JarvisLive, "_autodiagnostico") as auto:
            jarvis._on_text_command("faça um autodiagnóstico do sistema")
            import time as _t
            _t.sleep(0.2)
        auto.assert_called_once()


class GeekieTests(unittest.TestCase):
    def _base(self, atividades, atualizado="2026-09-25T18:00"):
        import json, tempfile
        from pathlib import Path
        base = Path(tempfile.mkdtemp())
        (base / "jarvis" / "geekie").mkdir(parents=True)
        (base / "jarvis" / "geekie" / "pendencias.json").write_text(
            json.dumps({"atualizado_em": atualizado, "atividades": atividades}), encoding="utf-8")
        return base

    def test_resumo_ordena_por_prazo_e_ignora_feitas(self):
        from datetime import date
        from core import geekie
        base = self._base([
            {"disciplina": "História", "titulo": "Resumo cap. 4", "prazo": "2026-09-30", "status": "pendente"},
            {"disciplina": "Matemática", "titulo": "Lista 3", "prazo": "2026-09-26", "status": "pendente"},
            {"disciplina": "Inglês", "titulo": "Quiz", "prazo": "2026-09-20", "status": "feita"},
            {"disciplina": "Ciências", "titulo": "Relatório", "prazo": "2026-09-24", "status": "atrasada"},
        ])
        atividades, atualizado = geekie.ler(base)
        self.assertEqual(len(atividades), 4)
        texto = geekie.resumo(atividades, hoje=date(2026, 9, 25))
        self.assertTrue(texto.startswith("No Geekie há 3 atividades pendentes"))
        self.assertLess(texto.index("Ciências"), texto.index("Matemática"))
        self.assertLess(texto.index("Matemática"), texto.index("História"))
        self.assertIn("vence amanhã", texto)
        self.assertNotIn("Inglês", texto)

    def test_lembra_uma_vez_por_dia_so_o_que_vence_em_ate_2_dias(self):
        from datetime import date
        from core import geekie
        base = self._base([
            {"disciplina": "Matemática", "titulo": "Lista 3", "prazo": "2026-09-27", "status": "pendente"},
            {"disciplina": "História", "titulo": "Resumo", "prazo": "2026-10-10", "status": "pendente"},
        ])
        atividades, _ = geekie.ler(base)
        hoje = date(2026, 9, 25)
        devidas = geekie.lembretes_do_dia(atividades, geekie.carregar_avisados(base), hoje)
        self.assertEqual([a.titulo for a in devidas], ["Lista 3"])
        self.assertIn("faltam 2 dias", geekie.frase_lembrete(devidas[0], hoje))
        geekie.marcar_avisados(devidas, base, hoje)
        self.assertEqual(geekie.lembretes_do_dia(atividades, geekie.carregar_avisados(base), hoje), [])
        self.assertEqual(len(geekie.lembretes_do_dia(atividades, geekie.carregar_avisados(base), date(2026, 9, 26))), 1)

    def test_lista_velha_pede_ao_hermes(self):
        from datetime import datetime
        from core import geekie
        self.assertTrue(geekie.desatualizada(None))
        self.assertTrue(geekie.desatualizada(datetime(2026, 9, 24, 7), agora=datetime(2026, 9, 25, 12)))
        self.assertFalse(geekie.desatualizada(datetime(2026, 9, 25, 7), agora=datetime(2026, 9, 25, 12)))

    def test_lembrete_com_modo_chamada_fica_so_na_tela(self):
        import main
        base = self._base([{"disciplina": "Matemática", "titulo": "Lista 3", "prazo": "2026-01-01", "status": "atrasada"}])
        jarvis = object.__new__(main.JarvisLive)
        jarvis.ui = UIFalsa()
        jarvis._portao = PortaoDeVoz(object())  # modo chamada, esperando o Hey Jarvis
        jarvis.session, jarvis._loop = object(), None
        with patch.dict("os.environ", {"HERMES_JARVIS_HOME": str(base)}):
            frases = jarvis._verificar_lembretes_geekie()
            self.assertEqual(len(frases), 1)
            self.assertIn("atrasada", frases[0])
            self.assertTrue(any("atrasada" in l for l in jarvis.ui.logs))
            self.assertEqual(jarvis._verificar_lembretes_geekie(), [])  # já lembrou hoje

    def test_skill_e_somente_leitura(self):
        texto = (KIT / "skills" / "jarvis" / "geekie-pendencias" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("SOMENTE LEITURA", texto)
        self.assertIn("Nunca digite senhas", texto)
        self.assertIn("__PASTA_JARVIS__/geekie/pendencias.json", texto)


class AutomacoesTests(unittest.TestCase):
    def _pasta(self):
        import tempfile
        from pathlib import Path
        return Path(tempfile.mkdtemp())

    def test_arquivo_py_vira_ferramenta_e_com_erro_nao_derruba(self):
        from core.automacoes import carregar_ferramentas
        pasta = self._pasta()
        (pasta / "boa.py").write_text(
            'FERRAMENTA = {"name": "say_hi", "description": "Says hi."}\n'
            'def executar(args, jarvis):\n    return "oi " + args.get("nome", "")\n', encoding="utf-8")
        (pasta / "quebrada.py").write_text("isto nao e python (", encoding="utf-8")
        (pasta / "repetida.py").write_text(
            'FERRAMENTA = {"name": "web_search", "description": "x"}\ndef executar(a, j): return ""\n',
            encoding="utf-8")
        (pasta / "_desligada.py").write_text("raise SystemExit", encoding="utf-8")
        carga = carregar_ferramentas(pasta, reservados={"web_search"})
        self.assertEqual(list(carga.ferramentas), ["say_hi"])
        self.assertEqual(carga.ferramentas["say_hi"].executar({"nome": "Erton"}, None), "oi Erton")
        self.assertEqual(carga.ferramentas["say_hi"].declaracao["parameters"]["type"], "OBJECT")
        self.assertEqual(sorted(a for a, _ in carga.erros), ["quebrada.py", "repetida.py"])

    def test_exemplo_da_pasta_funciona_quando_ativado(self):
        import shutil
        from pathlib import Path
        from core.automacoes import carregar_ferramentas
        pasta = self._pasta()
        exemplo = Path(__file__).resolve().parent.parent / "automacoes" / "dias_ate_a_data.py.exemplo"
        self.assertNotIn("days_until_date", carregar_ferramentas(exemplo.parent).ferramentas)  # .exemplo não carrega
        shutil.copy(exemplo, pasta / "dias_ate_a_data.py")
        carga = carregar_ferramentas(pasta)
        self.assertIn("Faltam", carga.ferramentas["days_until_date"].executar({"date": "2999-01-01"}, None))

    def test_arquivo_md_vira_habilidade_do_hermes(self):
        from core.automacoes import sincronizar_habilidades
        pasta, perfil = self._pasta(), self._pasta()
        (pasta / "resumo.md").write_text(
            "---\nname: resumo-noticias\ndescription: teste\n---\nSalve em __PASTA_JARVIS__/x.txt\n",
            encoding="utf-8")
        (pasta / "LEIA-ME.md").write_text("# guia", encoding="utf-8")
        carga = sincronizar_habilidades(pasta, perfil, criar_rotinas=False)
        self.assertEqual(carga.habilidades, ["resumo-noticias"])
        copia = (perfil / "skills" / "jarvis" / "resumo-noticias" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn((perfil / "jarvis").as_posix() + "/x.txt", copia)

    def test_jarvis_oferece_e_executa_a_automacao(self):
        import main
        from core.automacoes import Automacao, Carga
        from pathlib import Path
        carga = Carga(ferramentas={"say_hi": Automacao(
            "say_hi", {"name": "say_hi", "description": "Says hi.", "parameters": {"type": "OBJECT", "properties": {}}},
            lambda args, jarvis: "oi!", Path("x.py"))})
        with patch.object(main, "_AUTOMACOES", carga):
            nomes = [d["name"] for d in main.get_tool_declarations()]
            self.assertIn("say_hi", nomes)
            self.assertNotIn("say_hi", [d["name"] for d in main.get_tool_declarations(cloud_safe=True)])
            jarvis = object.__new__(main.JarvisLive)
            jarvis.ui = UIFalsa()
            jarvis.ui.set_state = lambda *a: None
            jarvis.cloud_safe = False

            class Chamada:
                name, args, id = "say_hi", {}, "1"

            resposta = asyncio.run(jarvis._execute_tool(Chamada()))
        self.assertEqual(resposta.response["result"], "oi!")


class AutoconsertoTests(unittest.TestCase):
    def _plugin(self):
        from core.automacoes import carregar_ferramentas
        from pathlib import Path
        carga = carregar_ferramentas(Path(__file__).resolve().parent.parent / "automacoes")
        self.assertEqual(carga.erros, [])
        return carga.ferramentas["self_repair"]

    def test_conserta_o_que_e_seguro_e_diz_o_que_falta(self):
        import sys
        from core import autodiagnostico as ad
        plugin = self._plugin()
        acoes = []

        class Jarvis:
            _portao = None
            _reserva = object()
            _modo_reserva = False

            def _ativar_modo_reserva(self):
                acoes.append("reserva")
                self._modo_reserva = True

            def _definir_modo_escuta(self, modo):
                acoes.append(modo)

            class ui:
                @staticmethod
                def set_graphics_quality(q):
                    acoes.append("grafico-" + q)

        itens = [ad.Item("Internet", "defeito", "sem conexão", "Confira o Wi-Fi."),
                 ad.Item("Chave do Gemini", "defeito", "chave recusada", "Crie outra."),
                 ad.Item("Computador", "atencao", "memória 88%, disco 40%", "Feche abas."),
                 ad.Item("Escuta", "defeito", "o detector do 'Hey Jarvis' não carregou", "x"),
                 ad.Item("Microfone", "ok", "USB")]
        with patch.object(ad, "diagnosticar", side_effect=[itens, [itens[0]]]):
            resposta = plugin.executar({}, Jarvis())
        self.assertEqual(acoes, ["reserva", "grafico-low", "maos_livres"])
        self.assertIn("Consertei: liguei a reserva Groq", resposta)
        self.assertIn("Ainda precisa de você: Internet: sem conexão. Confira o Wi-Fi.", resposta)

    def test_hermes_desligado_liga_o_servico(self):
        import sys
        from core import autodiagnostico as ad
        plugin = self._plugin()
        g = plugin.executar.__globals__  # o módulo da automação (carregado do arquivo)
        chamadas = []

        class Resultado:
            returncode = 0

        with patch("core.automacoes._hermes", return_value="hermes"), \
                patch.object(g["subprocess"], "run", side_effect=lambda cmd, **k: chamadas.append(cmd) or Resultado()), \
                patch.object(g["time"], "sleep"), \
                patch.object(ad, "verificar_hermes", return_value=ad.Item("Hermes (agentes)", "ok", "ligado")):
            feitos = g["consertar"]([ad.Item("Hermes (agentes)", "defeito", "o Hermes está desligado")], object())
        self.assertEqual(chamadas, [["hermes", "gateway", "restart"]])
        self.assertEqual(feitos, ["liguei o Hermes"])

    def test_tudo_ok_nao_mexe_em_nada(self):
        from core import autodiagnostico as ad
        plugin = self._plugin()
        with patch.object(ad, "diagnosticar", return_value=[ad.Item("Internet", "ok", "conectado")]):
            resposta = plugin.executar({}, object())
        self.assertIn("Não havia nada que eu pudesse consertar", resposta)
        self.assertIn("tudo funcionando", resposta)


def _plugin_da_pasta(arquivo: str):
    """Carrega um arquivo da pasta 'automacoes' como módulo (igual o Jarvis faz)."""
    import importlib.util
    from pathlib import Path
    caminho = Path(__file__).resolve().parent.parent / "automacoes" / arquivo
    spec = importlib.util.spec_from_file_location(f"teste_{caminho.stem}", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class AutomacoesQueIniciamTests(unittest.TestCase):
    def test_iniciar_sozinho_ou_junto_com_ferramenta(self):
        import tempfile
        from pathlib import Path
        from core.automacoes import carregar_ferramentas
        pasta = Path(tempfile.mkdtemp())
        (pasta / "so_tela.py").write_text("def iniciar(jarvis):\n    jarvis.append('tela')\n", encoding="utf-8")
        (pasta / "os_dois.py").write_text(
            'FERRAMENTA = {"name": "both_things", "description": "x"}\n'
            "def executar(a, j): return 'ok'\ndef iniciar(jarvis):\n    jarvis.append('dois')\n", encoding="utf-8")
        (pasta / "vazia.py").write_text("X = 1\n", encoding="utf-8")
        carga = carregar_ferramentas(pasta)
        self.assertEqual(list(carga.ferramentas), ["both_things"])
        self.assertEqual(sorted(a for a, _ in carga.inicios), ["os_dois.py", "so_tela.py"])
        self.assertEqual([a for a, _ in carga.erros], ["vazia.py"])
        feitos = []
        for _, iniciar in carga.inicios:
            iniciar(feitos)
        self.assertEqual(sorted(feitos), ["dois", "tela"])

    def test_novas_automacoes_da_pasta_carregam_sem_erro(self):
        from pathlib import Path
        from core.automacoes import carregar_ferramentas
        carga = carregar_ferramentas(Path(__file__).resolve().parent.parent / "automacoes")
        self.assertEqual(carga.erros, [])
        self.assertTrue({"spoken_reminders", "saved_routines", "self_repair", "external_memory_drive"} <= set(carga.ferramentas))
        self.assertEqual(sorted(a for a, _ in carga.inicios), ["lembretes.py", "memoria_hd.py", "painel_stark.py"])


class AvisosFaladosTests(unittest.TestCase):
    def _jarvis(self, chamada_fechada: bool):
        import main
        jarvis = object.__new__(main.JarvisLive)
        jarvis.ui, jarvis.session = UIFalsa(), SessaoFalsa()
        jarvis._modo_reserva = False
        jarvis._chamada_fechada = lambda: chamada_fechada
        return jarvis

    def test_conversa_aberta_fala_na_hora(self):
        jarvis = self._jarvis(False)

        async def cenario():
            jarvis._loop = asyncio.get_running_loop()
            self.assertEqual(jarvis.anunciar("tirar o bolo do forno"), "falado")
            await asyncio.sleep(0.05)
        asyncio.run(cenario())
        self.assertIn("tirar o bolo do forno", jarvis.session.textos[0])
        self.assertTrue(any("🔔" in l for l in jarvis.ui.logs))

    def test_modo_chamada_guarda_e_fala_quando_chamar(self):
        jarvis = self._jarvis(True)
        jarvis.AVISO_ESPERA_AO_CHAMAR = 0

        async def cenario():
            jarvis._loop = asyncio.get_running_loop()
            self.assertEqual(jarvis.anunciar("ligar para o contador"), "guardado")
            await asyncio.sleep(0.05)
            self.assertEqual(jarvis.session.textos, [])  # não interrompe o modo chamada
            jarvis._chamada_fechada = lambda: False  # disse "Hey Jarvis"
            with patch("core.palavra_ativacao.tocar_aviso"):
                jarvis._aviso_de_escuta("ouvindo")
            for _ in range(40):
                await asyncio.sleep(0.05)
                if jarvis.session.textos:
                    break
        asyncio.run(cenario())
        self.assertIn("Enquanto você estava fora: ligar para o contador", jarvis.session.textos[0])
        self.assertEqual(jarvis._avisos_guardados, [])

    def test_sem_gemini_fala_com_a_voz_reserva(self):
        jarvis = self._jarvis(False)
        jarvis.session, jarvis._loop = None, None
        falados = []
        jarvis._falar_reserva = falados.append
        self.assertEqual(jarvis.anunciar("beber água"), "falado")
        import time as _t
        for _ in range(40):
            if falados:
                break
            _t.sleep(0.05)
        self.assertEqual(falados, ["beber água"])


class LembretesFaladosTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from datetime import datetime
        from pathlib import Path
        self.m = _plugin_da_pasta("lembretes.py")
        self.arquivo = Path(tempfile.mkdtemp()) / "lembretes.json"
        self.agora = datetime(2026, 9, 25, 14, 0)  # sexta-feira

    def test_criar_por_minutos_e_por_horario(self):
        r = self.m.criar({"text": "tirar o bolo", "in_minutes": 20}, self.agora, self.arquivo)
        self.assertIn("hoje às 14:20", r)
        r = self.m.criar({"text": "treino", "time": "7h"}, self.agora, self.arquivo)  # já passou: amanhã
        self.assertIn("amanhã às 07:00", r)
        r = self.m.criar({"text": "e-mails", "time": "08:00", "repeat": "weekdays"}, self.agora, self.arquivo)
        self.assertIn("em 28/09 às 08:00", r)  # sábado e domingo pulados
        self.assertIn("de segunda a sexta", r)
        self.assertIn("Não consegui marcar", self.m.criar({"text": "x", "time": "25:00"}, self.agora, self.arquivo))
        lista = self.m.listar(self.agora, self.arquivo)
        self.assertIn("1) hoje às 14:20: tirar o bolo", lista)

    def test_vencidos_avisa_repete_e_cancela(self):
        from datetime import timedelta
        self.m.criar({"text": "tirar o bolo", "in_minutes": 20}, self.agora, self.arquivo)
        self.m.criar({"text": "treino", "time": "15:00", "repeat": "daily"}, self.agora, self.arquivo)
        self.m.criar({"text": "reunião", "time": "18:00"}, self.agora, self.arquivo)
        self.assertEqual(self.m.vencidos(self.agora + timedelta(minutes=10), self.arquivo), [])
        frases = self.m.vencidos(self.agora + timedelta(hours=1, minutes=1), self.arquivo)
        self.assertEqual(frases, ["tirar o bolo (era para as 14:20)", "treino"])
        dados = self.m.ler(self.arquivo)
        self.assertEqual(sorted(l["texto"] for l in dados["lembretes"]), ["reunião", "treino"])
        treino = [l for l in dados["lembretes"] if l["texto"] == "treino"][0]
        self.assertEqual(treino["quando"], "2026-09-26T15:00")  # repete amanhã
        self.assertIn("ultimo_aviso", dados)
        self.assertIn("cancelado", self.m.cancelar({"text": "reunião"}, self.arquivo))
        self.assertIn("Não achei", self.m.cancelar({"number": 99}, self.arquivo))

    def test_lembrete_muito_antigo_nao_e_falado(self):
        from datetime import timedelta
        self.m.criar({"text": "velho", "in_minutes": 5}, self.agora, self.arquivo)
        self.assertEqual(self.m.vencidos(self.agora + timedelta(days=2), self.arquivo), [])
        self.assertEqual(self.m.ler(self.arquivo)["lembretes"], [])

    def test_avisar_usa_o_anunciar_do_jarvis(self):
        avisos = []

        class Jarvis:
            def anunciar(self, texto, titulo=""):
                avisos.append((titulo, texto))
        self.m._avisar(Jarvis(), ["beber água"])
        self.assertEqual(avisos, [("Lembrete", "Lembrete: beber água.")])


class RotinasSalvasTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.m = _plugin_da_pasta("rotinas.py")
        self.arquivo = Path(tempfile.mkdtemp()) / "rotinas.json"

    def test_prontas_salvar_rodar_e_apagar(self):
        self.assertIn("bom dia", self.m.listar(self.arquivo))
        r = self.m.salvar({"name": "Rotina Treino", "steps": ["veja o clima", "abra o Strava"]}, self.arquivo)
        self.assertIn("Rotina 'treino' salva com 2 passos", r)
        r = self.m.rodar({"name": "treino"}, None, self.arquivo)
        self.assertIn("1) veja o clima 2) abra o Strava", r)
        self.assertIn("explicit 'ok'", r)  # regras de segurança sempre junto
        self.assertIn("1) Diga como está o tempo", self.m.rodar({"name": "Bom Dia"}, None, self.arquivo))
        self.assertIn("apagada", self.m.apagar({"name": "treino"}, self.arquivo))
        self.assertIn("Não achei", self.m.rodar({"name": "treino"}, None, self.arquivo))
        self.assertIn("Faltam os passos", self.m.salvar({"name": "x"}, self.arquivo))

    def test_rotina_do_hermes_vai_para_o_hermes(self):
        self.m.salvar({"name": "pesquisa", "steps": "pesquise provas de triathlon; liste as datas",
                       "agent": "hermes"}, self.arquivo)
        pedidos = []

        class Jarvis:
            _loop = None
        with patch("core.hermes_ponte.perguntar", side_effect=lambda p: pedidos.append(p) or "3 provas"):
            r = self.m.rodar({"name": "pesquisa"}, Jarvis(), self.arquivo)
        self.assertEqual(r, "[Hermes, rotina pesquisa] 3 provas")
        self.assertIn("1) pesquise provas de triathlon 2) liste as datas", pedidos[0])
        self.assertIn("Nunca publique", pedidos[0])


class PainelStarkTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.m = _plugin_da_pasta("painel_stark.py")
        self.pasta = Path(tempfile.mkdtemp())
        self.m.pasta_dados = lambda: self.pasta

    def test_textos_do_painel(self):
        import json
        from datetime import datetime
        agora = datetime(2026, 9, 25, 14, 0)
        self.assertEqual(self.m.texto_lembrete(agora), ("Nenhum lembrete marcado", False))
        self.assertEqual(self.m.nomes_rotinas(), ["bom dia", "fim do dia"])
        (self.pasta / "lembretes.json").write_text(json.dumps({"lembretes": [
            {"texto": "treino", "quando": "2026-09-26T06:00"}, {"texto": "reunião", "quando": "2026-09-25T18:00"}],
            "ultimo_aviso": None}), encoding="utf-8")
        self.assertEqual(self.m.texto_lembrete(agora), ("hoje 18:00 · reunião  (+1)", False))
        dados = json.loads((self.pasta / "lembretes.json").read_text(encoding="utf-8"))
        dados["ultimo_aviso"] = {"texto": "beber água", "em": "2026-09-25T13:59:30"}
        (self.pasta / "lembretes.json").write_text(json.dumps(dados), encoding="utf-8")
        self.assertEqual(self.m.texto_lembrete(agora), ("⚠ beber água", True))
        (self.pasta / "rotinas.json").write_text(json.dumps({"rotinas": {"treino": {}}}), encoding="utf-8")
        self.assertEqual(self.m.nomes_rotinas(), ["treino"])

    def test_estado_da_voz(self):
        class J:
            session, _modo_reserva = object(), False
        self.assertEqual(self.m.texto_voz(J()), ("Voz: Gemini ao vivo", True))
        J._modo_reserva = True
        self.assertEqual(self.m.texto_voz(J()), ("Voz: reserva (Groq)", False))


class MemoriaNoHDTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.m = _plugin_da_pasta("memoria_hd.py")
        self.base = Path(tempfile.mkdtemp())
        self.memoria = self.base / "jarvis" / "memory"
        self.docs = self.base / "docs"
        self.hermes = self.base / "hermes"
        for pasta in (self.memoria, self.docs, self.hermes / "memories"):
            pasta.mkdir(parents=True)
        (self.memoria / "long_term.json").write_text('{"nome": "Erton"}', encoding="utf-8")
        (self.memoria / "answer_cache.py").write_text("codigo", encoding="utf-8")  # não é memória
        (self.docs / "lembretes.json").write_text("{}", encoding="utf-8")
        (self.docs / ".env").write_text("GEMINI_API_KEY=segredo", encoding="utf-8")
        (self.docs / "api_keys.json").write_text("{}", encoding="utf-8")
        (self.hermes / "memories" / "MEMORY.md").write_text("gosta de triathlon", encoding="utf-8")
        (self.hermes / "auth.json").write_text("{}", encoding="utf-8")
        self.config = self.base / "config.json"
        self.m.fontes = lambda: [("memoria-jarvis", self.memoria, ["*.json", "*.md"]),
                                 ("documentos", self.docs, None),
                                 ("hermes/memories", self.hermes / "memories", None)]
        self.m.arquivo_config = lambda: self.config
        self.hd = self.base / "HD"

    def test_copia_o_que_aprendeu_sem_chaves_e_guarda_historico(self):
        from datetime import datetime
        pasta = self.m.preparar_hd(self.hd / self.m.PASTA_NO_HD)
        copiados, total = self.m.salvar(pasta, datetime(2026, 9, 25, 10, 0))
        self.assertEqual((copiados, total), (3, 3))
        atual = pasta / "atual"
        self.assertTrue((atual / "memoria-jarvis" / "long_term.json").exists())
        self.assertTrue((atual / "hermes" / "memories" / "MEMORY.md").exists())
        self.assertFalse((atual / "documentos" / ".env").exists())
        self.assertFalse((atual / "documentos" / "api_keys.json").exists())
        self.assertFalse((atual / "memoria-jarvis" / "answer_cache.py").exists())
        self.assertTrue((pasta / "historico" / "2026-09-25" / "memoria-jarvis" / "long_term.json").exists())
        self.assertEqual(self.m.salvar(pasta)[0], 0)  # nada mudou: não copia de novo
        self.assertIn("ultima_copia", self.m.ler_config())

    def test_reconhece_o_hd_pela_marca_mesmo_se_a_letra_mudar(self):
        pasta = self.m.preparar_hd(self.hd / self.m.PASTA_NO_HD)
        outro = self.base / "OutroHD" / self.m.PASTA_NO_HD
        outro.mkdir(parents=True)
        (outro / self.m.MARCADOR).write_text("de-outro-computador", encoding="utf-8")
        self.assertEqual(self.m.achar_hd(discos=[self.base / "OutroHD", self.hd]), pasta)
        self.assertIsNone(self.m.achar_hd(discos=[self.base / "OutroHD"]))
        manual = self.base / "Novo" / self.m.PASTA_NO_HD
        manual.mkdir(parents=True)  # pasta criada à mão pelo usuário
        self.assertEqual(self.m.achar_hd({}, discos=[self.base / "Novo"]), manual)

    def test_recuperar_so_com_confirmacao_e_guarda_a_atual(self):
        pasta = self.m.preparar_hd(self.hd / self.m.PASTA_NO_HD)
        self.m.salvar(pasta)
        (self.memoria / "long_term.json").write_text("{}", encoding="utf-8")  # memória perdida
        self.m.achar_hd = lambda *a, **k: pasta
        self.assertIn("confirm", self.m.executar({"action": "restore"}, None))
        self.assertIn("Recuperei", self.m.executar({"action": "restore", "confirm": True}, None))
        self.assertEqual((self.memoria / "long_term.json").read_text(encoding="utf-8"), '{"nome": "Erton"}')
        self.assertEqual((self.memoria / "long_term.json.antes-de-restaurar").read_text(encoding="utf-8"), "{}")
        self.assertFalse((self.hermes / "memories" / "MEMORY.md.antes-de-restaurar").exists())
