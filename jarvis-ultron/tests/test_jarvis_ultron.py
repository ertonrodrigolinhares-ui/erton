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
        self.assertLess(vivos.index("gemini-2.5-flash-native-audio"),
                        vivos.index("gemini-3.5-flash-native-audio-preview"))

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
        self.assertEqual(set(config["mcp_servers"]), {"metricool", "meta_ads"})
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
