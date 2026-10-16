import contextlib
import io
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import gemini_acesso as ga

CHAVE_AQ = "AQ.Ab8RN6Kexemplo-de-chave-que-nao-existe-1234567890"
RECUSA_AQ = Exception("401 UNAUTHENTICATED. {'reason': 'ACCESS_TOKEN_TYPE_UNSUPPORTED'}")


class ClienteFalso:
    """Imita o google.genai.Client: o caminho normal recusa a chave AQ.; o Vertex aceita."""

    def __init__(self, via, vivos_ok=("gemini-live-2.5-flash",), recusa=RECUSA_AQ):
        self.via, self.vivos_ok, self.recusa = via, set(vivos_ok), recusa
        self.models = NS(list=self._listar, generate_content=self._gerar)
        self.aio = NS(live=NS(connect=self._conectar))

    def _listar(self, config=None):
        if self.via == "studio" and self.recusa:
            raise self.recusa
        return [NS(name="publishers/google/models/gemini-2.5-flash", supported_actions=None)]

    def _gerar(self, model, contents, config=None):
        if self.via == "studio" and self.recusa:
            raise self.recusa
        return NS(text="ok")

    @contextlib.asynccontextmanager
    async def _conectar(self, model, config):
        if model not in self.vivos_ok:
            raise Exception(f"404 NOT_FOUND model {model}")
        yield NS()


class CaminhoTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("JARVIS_GEMINI_VIA", None)
        os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)

    def test_aplicar_vertex_vale_para_todas_as_conexoes(self):
        ga.aplicar_via("vertex")
        self.assertEqual(os.environ["GOOGLE_GENAI_USE_VERTEXAI"], "true")
        self.assertEqual(ga.via(), "vertex")
        self.assertIsNone(ga.versao_api())
        self.assertEqual(ga.opcoes_http(timeout=5), {"timeout": 5})
        ga.aplicar_via("studio")
        self.assertNotIn("GOOGLE_GENAI_USE_VERTEXAI", os.environ)
        self.assertEqual(ga.opcoes_http(), {"api_version": "v1beta"})

    def test_biblioteca_do_google_obedece_a_chave_geral(self):
        from google import genai
        ga.aplicar_via("vertex")
        cliente = genai.Client(api_key=CHAVE_AQ)
        self.assertTrue(cliente._api_client.vertexai)
        self.assertIn("aiplatform.googleapis.com", cliente._api_client._http_options.base_url)
        ga.aplicar_via("studio")
        cliente = genai.Client(api_key=CHAVE_AQ)
        self.assertFalse(cliente._api_client.vertexai)

    def test_nomes_de_modelos_dos_dois_caminhos(self):
        self.assertEqual(ga.nome_curto("models/gemini-2.5-flash"), "gemini-2.5-flash")
        self.assertEqual(ga.nome_curto("publishers/google/models/gemini-2.5-flash"), "gemini-2.5-flash")

    def test_explica_os_erros_em_portugues(self):
        casos = {
            "TIPO_DE_CHAVE": RECUSA_AQ,
            "CHAVE_INVALIDA": Exception("400 API_KEY_INVALID"),
            "API_DESLIGADA": Exception("403 SERVICE_DISABLED Vertex AI API has not been used in project 123"),
            "FATURAMENTO": Exception("403 This API method requires billing to be enabled"),
            "COTA": Exception("429 RESOURCE_EXHAUSTED"),
            "REDE": Exception("Connection timed out"),
        }
        for codigo, erro in casos.items():
            self.assertEqual(ga.explicar_erro(erro, "vertex")[0], codigo, erro)


class DiagnosticoTests(unittest.TestCase):
    def _cliente(self, chave, via_, timeout_ms=15000):
        return ClienteFalso(via_)

    def test_chave_aq_recusada_no_normal_funciona_no_vertex(self):
        with patch.object(ga, "cliente", self._cliente):
            estudio = ga.testar_via(CHAVE_AQ, "studio")
            vertex = ga.testar_via(CHAVE_AQ, "vertex")
            vencedor, todos = ga.escolher_caminho(CHAVE_AQ)
        self.assertFalse(estudio.ok)
        self.assertEqual(estudio.codigo, "TIPO_DE_CHAVE")
        self.assertTrue(vertex.ok)
        self.assertEqual(vertex.modelo_texto, "gemini-2.5-flash")
        self.assertEqual(vencedor.via, "vertex")
        self.assertEqual([r.via for r in todos], ["studio", "vertex"])

    def test_acha_o_modelo_de_voz_que_abre(self):
        with patch.object(ga, "cliente", self._cliente), patch.dict(os.environ, {"GEMINI_LIVE_MODEL": ""}):
            modelo, falhas = ga.testar_ao_vivo(CHAVE_AQ, "vertex", espera=5)
        self.assertEqual(modelo, "gemini-live-2.5-flash")
        self.assertEqual(falhas[0][0], "gemini-live-2.5-flash-native-audio")


class ValidadorDaTelaTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("JARVIS_GEMINI_VIA", None)
        os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)

    def test_chave_aq_e_aceita_pelo_vertex(self):
        from core import api_key_validator as v

        with patch("google.genai.Client", lambda **kw: ClienteFalso("studio")), \
                patch.object(ga, "testar_via", lambda chave, via_: ga.Resultado(via=via_, ok=True)):
            r = v.validate_gemini_api_key(CHAVE_AQ, timeout_seconds=5)
        self.assertTrue(r.valid, r.message)
        self.assertIn("Vertex", r.message)
        self.assertEqual(r.via, "vertex")
        # o validador não troca o caminho do programa (no servidor valeria para todos os usuários)
        self.assertNotIn("JARVIS_GEMINI_VIA", os.environ)
        self.assertNotIn("GOOGLE_GENAI_USE_VERTEXAI", os.environ)

    def test_chave_aceita_pelo_caminho_normal_devolve_caminho_normal(self):
        from core import api_key_validator as v

        normal = ClienteFalso("studio", recusa=None)
        normal.models = NS(list=lambda: [NS(name="models/gemini-2.5-flash-native-audio",
                                            supported_actions=["bidiGenerateContent"])])
        ga.aplicar_via("vertex")  # escolha antiga, de uma chave "AQ." de antes
        with patch("google.genai.Client", lambda **kw: normal):
            r = v.validate_gemini_api_key("AIza" + "a" * 35, timeout_seconds=5)
        self.assertTrue(r.valid, r.message)
        self.assertEqual(r.via, "studio")

    def test_tela_passa_a_usar_o_caminho_em_que_a_chave_funcionou(self):
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        import ui
        from core.api_key_validator import ApiKeyValidationResult

        ga.aplicar_via("vertex")
        with patch("core.api_key_validator.validate_gemini_api_key",
                   lambda chave: ApiKeyValidationResult(True, "Gemini API key verified.", via="studio")), \
                patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            tela = ui.SetupOverlay()
            tela.validate_candidate("AIza" + "a" * 35)
            limite = time.monotonic() + 5
            while tela._validation_pending and time.monotonic() < limite:
                app.processEvents()
                time.sleep(0.02)
            self.assertFalse(tela._validation_pending)
            self.assertEqual(ga.via(), "studio")
            self.assertNotIn("GOOGLE_GENAI_USE_VERTEXAI", os.environ)

    def test_tela_grava_no_env_o_caminho_normal_por_cima_de_um_vertex_antigo(self):
        import ui

        pasta = Path(tempfile.mkdtemp())
        env = pasta / ".env"
        env.write_text('GEMINI_API_KEY="AQ.antiga-000000000000000000"\nJARVIS_GEMINI_VIA="vertex"\n')
        chave = "AIza" + "b" * 35
        overlay = NS(_verified_key=chave, _modo_reserva=False, _modo_gemma=False, hide=lambda: None)
        janela = NS(_overlay=overlay, _log=NS(append_log=lambda texto: None), _ready=False,
                    _apply_state=lambda estado: None, _show_voice_select_then_name=lambda: None)
        ga.aplicar_via("studio")
        with patch.object(ui, "BASE_DIR", pasta), patch.object(ui, "CONFIG_DIR", pasta / "config"), \
                patch.object(ui, "API_FILE", pasta / "config" / "api_keys.json"), \
                patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            ui.MainWindow._on_setup_done(janela, chave, "windows", False)
        conteudo = env.read_text()
        self.assertIn('JARVIS_GEMINI_VIA="studio"', conteudo)
        self.assertNotIn('"vertex"', conteudo)

    def test_cerebro_segue_o_caminho_que_a_tela_mandou(self):
        from core.ponte import UIRemota

        with patch.dict(os.environ, {"JARVIS_GEMINI_VIA": "vertex", "GOOGLE_GENAI_USE_VERTEXAI": "true"}):
            remota = UIRemota(None)
            remota._tratar(("pronto", {"JARVIS_GEMINI_VIA": "studio", "GEMINI_API_KEY": "chave-da-tela"}))
            self.assertTrue(remota._pronto.is_set())
            self.assertNotIn("GOOGLE_GENAI_USE_VERTEXAI", os.environ)
            self.assertEqual(ga.via(), "studio")

    def test_chave_aq_que_nao_funciona_em_nenhum_caminho(self):
        from core import api_key_validator as v

        with patch("google.genai.Client", lambda **kw: ClienteFalso("studio")), \
                patch.object(ga, "testar_via", lambda chave, via_: ga.Resultado(via=via_, ok=False)):
            r = v.validate_gemini_api_key(CHAVE_AQ, timeout_seconds=5)
        self.assertFalse(r.valid)
        self.assertNotIn("JARVIS_GEMINI_VIA", os.environ)


class ModeloDeVozNoVertexTests(unittest.TestCase):
    def test_vertex_sem_lista_de_voz_usa_o_testado(self):
        from core.live_model import pick_live_model

        cliente = NS(models=NS(list=lambda: [NS(name="publishers/google/models/gemini-2.5-flash",
                                                supported_actions=None)]))
        with patch.dict(os.environ, {"JARVIS_GEMINI_VIA": "vertex", "GEMINI_LIVE_MODEL": "gemini-live-2.5-flash"}):
            self.assertEqual(pick_live_model(cliente, Path("/nao/existe.json")), "gemini-live-2.5-flash")

    def test_vertex_sem_poder_listar_nunca_usa_o_nome_do_ai_studio(self):
        from core.live_model import pick_live_model

        cliente = NS(models=NS(list=lambda: (_ for _ in ()).throw(Exception("403 PERMISSION_DENIED"))))
        pasta = Path(tempfile.mkdtemp())
        config = pasta / "api_keys.json"
        config.write_text('{"live_model": "models/gemini-2.5-flash-native-audio-preview-12-2025"}')
        with patch.dict(os.environ, {"JARVIS_GEMINI_VIA": "vertex", "GEMINI_LIVE_MODEL": ""}):
            self.assertEqual(pick_live_model(cliente, Path("/nao/existe.json")), ga.VIVO_VERTEX[0])
            self.assertEqual(pick_live_model(cliente, config), ga.VIVO_VERTEX[0])
        with patch.dict(os.environ, {"JARVIS_GEMINI_VIA": "vertex", "GEMINI_LIVE_MODEL": "gemini-live-2.5-flash"}):
            self.assertEqual(pick_live_model(cliente, config), "gemini-live-2.5-flash")

    def test_caminho_normal_continua_exigindo_modelo_de_voz(self):
        from core.live_model import pick_live_model

        cliente = NS(models=NS(list=lambda: [NS(name="models/gemini-2.5-flash", supported_actions=["generateContent"])]))
        with patch.dict(os.environ, {"JARVIS_GEMINI_VIA": "", "GEMINI_LIVE_MODEL": ""}):
            with self.assertRaises(RuntimeError):
                pick_live_model(cliente, Path("/nao/existe.json"))


class CentralDeModelosNoVertexTests(unittest.TestCase):
    def setUp(self):
        from core import modelos

        self.modelos = modelos
        self.guardado = (modelos._cache, modelos._cache_momento)
        modelos._falharam.clear()
        self.env = patch.dict(os.environ, {"GEMINI_API_KEY": "x", "GEMINI_LIVE_MODEL": "",
                                           "JARVIS_GEMINI_VIA": "vertex"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.modelos._cache, self.modelos._cache_momento = self.guardado
        self.modelos._falharam.clear()

    def test_nome_de_voz_do_vertex_tem_versao(self):
        self.assertEqual(self.modelos._versao("gemini-live-2.5-flash-native-audio"), 2.5)
        self.assertEqual(self.modelos._versao("gemini-3.1-flash"), 3.1)

    def test_lista_do_vertex_poe_o_modelo_de_voz_estavel_primeiro(self):
        self.modelos._cache = [(n, {"bidigeneratecontent"}) for n in (
            "gemini-2.5-flash-native-audio-preview-12-2025", "gemini-2.0-flash-live-preview-04-09",
            "gemini-live-2.5-flash-native-audio", "gemini-live-2.5-flash")]
        vivos = self.modelos.candidatos(ga.VIVO_VERTEX[0])
        self.assertEqual(vivos[0], "gemini-live-2.5-flash-native-audio")
        self.assertLess(vivos.index("gemini-live-2.5-flash"), vivos.index("gemini-2.0-flash-live-preview-04-09"))
        # um 3.x de voz, se a lista tiver, continua vindo antes do 2.5
        self.modelos._cache.append(("gemini-3.1-flash-live-preview", {"bidigeneratecontent"}))
        self.assertEqual(self.modelos.candidatos(ga.VIVO_VERTEX[0])[0], "gemini-3.1-flash-live-preview")

    def test_vertex_sem_lista_a_voz_troca_entre_os_modelos_do_vertex(self):
        self.modelos._cache = []
        self.modelos._cache_momento = 10 ** 12
        self.assertEqual(self.modelos.candidatos(ga.VIVO_VERTEX[0]), list(ga.VIVO_VERTEX))
        self.modelos.pular(ga.VIVO_VERTEX[0])  # a voz não conectou nele: passa para o próximo
        self.assertEqual(self.modelos.resolver(ga.VIVO_VERTEX[0]), ga.VIVO_VERTEX[1])
        with patch.dict(os.environ, {"JARVIS_GEMINI_VIA": "studio"}):  # caminho normal: como antes
            self.assertEqual(self.modelos.candidatos("gemini-live-2.5-flash-preview"),
                             ["gemini-live-2.5-flash-preview"])

    def test_biblioteca_antiga_vai_pela_nova_no_vertex(self):
        import google.generativeai as antiga

        with patch.object(self.modelos, "_chave", lambda: ""):
            self.modelos.instalar()  # o main.py faz isso ao abrir
        pedidos = []

        class ClienteNovo:
            def __init__(self, **kwargs):
                pedidos.append(("cliente", kwargs.get("api_key")))
                self.models = NS(generate_content=self._gerar)

            def _gerar(self, model, contents, config=None):
                pedidos.append((model, contents, config))
                return NS(text="ok")

        with patch.object(self.modelos, "candidatos", lambda pedido: [pedido.removeprefix("models/")]), \
                patch("google.genai.Client", ClienteNovo):
            antiga.configure(api_key=CHAVE_AQ)
            modelo = antiga.GenerativeModel(model_name="gemini-2.5-flash-lite", system_instruction="Responda em JSON.")
            resposta = modelo.generate_content("Goal: abrir o bloco de notas")
        self.assertEqual(resposta.text, "ok")
        self.assertEqual(pedidos[0], ("cliente", CHAVE_AQ))
        self.assertEqual(pedidos[1][:2], ("gemini-2.5-flash-lite", "Goal: abrir o bloco de notas"))
        self.assertEqual(pedidos[1][2]["system_instruction"], "Responda em JSON.")

    def test_arquivo_vai_junto_com_o_pedido_no_vertex(self):
        from actions import file_processor as fp

        pasta = Path(tempfile.mkdtemp())
        arquivo = pasta / "nota.pdf"
        arquivo.write_bytes(b"%PDF-1.4\x00\x01\x02\x03" * 200)
        enviados = []
        with patch.object(fp, "_generate_content",
                          lambda partes, model="gemini-2.5-flash": enviados.append(partes) or "resumo"), \
                patch.object(fp, "_gemini_client", lambda: self.fail("a File API não existe no Vertex AI")):
            self.assertEqual(fp._process_unknown(arquivo, "", {}), "resumo")
        parte = enviados[0][1]
        self.assertEqual(parte.inline_data.mime_type, "application/pdf")


class DiagnosticoNoVertexTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"GEMINI_API_KEY": CHAVE_AQ, "GEMINI_LIVE_MODEL": "",
                                           "JARVIS_GEMINI_VIA": "vertex"})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_vertex_que_funciona_nao_e_defeito(self):
        from core.autodiagnostico import verificar_gemini

        # a lista do Vertex vem sem "supported_actions" (não diz quais modelos são de voz)
        with patch.object(ga, "cliente", lambda chave, via_, timeout_ms=15000: ClienteFalso(via_)):
            item = verificar_gemini()
        self.assertEqual(item.estado, "ok", item)
        self.assertIn(ga.VIVO_VERTEX[0], item.detalhe)

    def test_vertex_com_problema_manda_para_o_testador_e_nao_para_o_ai_studio(self):
        from core.autodiagnostico import verificar_gemini

        def cliente(erro):
            def fazer(chave, via_, timeout_ms=15000):
                c = ClienteFalso(via_)
                c.models = NS(list=lambda config=None: [],
                              generate_content=lambda **kw: (_ for _ in ()).throw(erro))
                return c
            return fazer

        with patch.object(ga, "cliente", cliente(Exception("403 SERVICE_DISABLED Vertex AI API has not been used"))):
            item = verificar_gemini()
        self.assertEqual(item.estado, "defeito")
        self.assertIn("Testar chave do Gemini", item.dica)
        self.assertNotIn("AI Studio", item.dica)
        with patch.object(ga, "cliente", cliente(Exception("429 RESOURCE_EXHAUSTED"))):
            item = verificar_gemini()
        self.assertEqual(item.estado, "atencao")  # cota: a chave funciona; não liga a reserva à toa


class TestadorTests(unittest.TestCase):
    def test_testador_grava_o_caminho_e_nunca_mostra_a_chave(self):
        pasta = Path(tempfile.mkdtemp())
        env = pasta / ".env"
        env.write_text('GEMINI_API_KEY="AIza-antiga-0000000000000000000"\nJARVIS_CIDADE="Campina Grande"\n')
        saida = io.StringIO()
        with patch.object(ga, "_arquivo_env", lambda: env), \
                patch("getpass.getpass", lambda prompt="": CHAVE_AQ), \
                patch.object(ga, "cliente", lambda chave, via_, timeout_ms=15000: ClienteFalso(via_)), \
                patch.dict(os.environ, {"GEMINI_API_KEY": "", "GEMINI_LIVE_MODEL": ""}), \
                contextlib.redirect_stdout(saida):
            codigo = ga.principal()
        texto = saida.getvalue()
        self.assertEqual(codigo, 0, texto)
        self.assertNotIn(CHAVE_AQ, texto)            # a chave nunca aparece
        self.assertNotIn(CHAVE_AQ[3:20], texto)
        conteudo = env.read_text()
        self.assertIn(f'GEMINI_API_KEY="{CHAVE_AQ}"', conteudo)
        self.assertIn('JARVIS_GEMINI_VIA="vertex"', conteudo)
        self.assertIn('GEMINI_LIVE_MODEL="gemini-live-2.5-flash"', conteudo)
        self.assertIn('JARVIS_CIDADE="Campina Grande"', conteudo)  # o resto do .env fica
        self.assertIn("Pronto!", texto)
        os.environ.pop("GEMINI_API_KEY", None)

    def test_testador_explica_quando_nada_funciona(self):
        pasta = Path(tempfile.mkdtemp())
        env = pasta / ".env"
        env.write_text("")
        saida = io.StringIO()

        def cliente_ruim(chave, via_, timeout_ms=15000):
            erro = RECUSA_AQ if via_ == "studio" else Exception("403 SERVICE_DISABLED Vertex AI API has not been used")
            c = ClienteFalso(via_, recusa=erro)
            if via_ == "vertex":
                c.models = NS(list=lambda config=None: [], generate_content=lambda **kw: (_ for _ in ()).throw(erro))
            return c

        with patch.object(ga, "_arquivo_env", lambda: env), \
                patch("getpass.getpass", lambda prompt="": CHAVE_AQ), \
                patch.object(ga, "cliente", cliente_ruim), \
                patch.dict(os.environ, {"GEMINI_API_KEY": ""}), \
                contextlib.redirect_stdout(saida):
            codigo = ga.principal()
        texto = saida.getvalue()
        self.assertEqual(codigo, 1)
        self.assertIn("Vertex AI API", texto)
        self.assertIn("aiplatform.googleapis.com", texto)  # o link para ligar a API
        self.assertNotIn(CHAVE_AQ, texto)
        self.assertEqual(env.read_text(), "")  # não grava nada que não funcionou
        os.environ.pop("GEMINI_API_KEY", None)

    def test_testador_le_e_grava_env_gravado_pelo_console_do_windows(self):
        # O iniciador grava a cidade pelo console (cp850): "ã" vira o byte 0xC6, que não é UTF-8.
        pasta = Path(tempfile.mkdtemp())
        env = pasta / ".env"
        env.write_bytes(f'GEMINI_API_KEY="{CHAVE_AQ}"\r\nJARVIS_CIDADE="João Pessoa"\r\n'.encode("cp850"))
        saida = io.StringIO()
        with patch.object(ga, "_arquivo_env", lambda: env), \
                patch("getpass.getpass", lambda prompt="": ""), \
                patch.object(ga, "cliente", lambda chave, via_, timeout_ms=15000: ClienteFalso(via_)), \
                patch.dict(os.environ, {"GEMINI_LIVE_MODEL": ""}), \
                contextlib.redirect_stdout(saida):
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("JARVIS_GEMINI_VIA", None)
            codigo = ga.principal()
        texto = saida.getvalue()
        self.assertEqual(codigo, 0, texto)
        self.assertNotIn("Chave no .env: nenhuma", texto)  # a chave do .env foi lida
        self.assertIn("Chave no .env: começa com AQ.", texto)
        self.assertNotIn(CHAVE_AQ, texto)
        conteudo = env.read_bytes().decode("utf-8")  # regravado em UTF-8
        self.assertIn('JARVIS_GEMINI_VIA="vertex"', conteudo)
        self.assertIn('GEMINI_LIVE_MODEL="gemini-live-2.5-flash"', conteudo)
        self.assertIn('JARVIS_CIDADE="João Pessoa"', conteudo)  # o acento não estraga
        self.assertIn(f'GEMINI_API_KEY="{CHAVE_AQ}"', conteudo)

    def test_testador_avisa_quando_nao_consegue_gravar(self):
        pasta = Path(tempfile.mkdtemp())
        env = pasta / ".env"
        env.write_text("")
        saida = io.StringIO()

        def sem_permissao(*a, **kw):
            raise PermissionError("acesso negado")

        with patch.object(ga, "_arquivo_env", lambda: env), \
                patch("getpass.getpass", lambda prompt="": CHAVE_AQ), \
                patch.object(ga, "cliente", lambda chave, via_, timeout_ms=15000: ClienteFalso(via_)), \
                patch("core.env_arquivo.atualizar_env", sem_permissao), \
                patch.dict(os.environ, {"GEMINI_API_KEY": "", "GEMINI_LIVE_MODEL": ""}), \
                contextlib.redirect_stdout(saida):
            codigo = ga.principal()
        texto = saida.getvalue()
        self.assertEqual(codigo, 1, texto)
        self.assertIn("NÃO consegui gravar no arquivo .env", texto)
        self.assertNotIn("Gravei no .env", texto)
        self.assertNotIn(CHAVE_AQ, texto)

    def test_janela_do_testador_nao_fecha_sozinha_quando_da_erro(self):
        pedidos = []

        def quebra():
            raise UnicodeDecodeError("utf-8", b"\xc6", 0, 1, f"chave {CHAVE_AQ}")

        saida = io.StringIO()
        with patch.object(ga, "principal", quebra), \
                patch("builtins.input", lambda texto="": pedidos.append(texto) or ""), \
                contextlib.redirect_stdout(saida):
            codigo = ga.rodar_no_console()
        self.assertEqual(codigo, 1)
        self.assertEqual(len(pedidos), 1)  # ainda espera o Enter
        self.assertIn("Aperte Enter", pedidos[0])
        self.assertIn("UnicodeDecodeError", saida.getvalue())
        self.assertNotIn(CHAVE_AQ, saida.getvalue())  # a mensagem do erro (que pode ter a chave) não sai


if __name__ == "__main__":
    unittest.main()
