import contextlib
import io
import os
import sys
import tempfile
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
        self.assertEqual(os.environ.get("JARVIS_GEMINI_VIA"), "vertex")

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

    def test_caminho_normal_continua_exigindo_modelo_de_voz(self):
        from core.live_model import pick_live_model

        cliente = NS(models=NS(list=lambda: [NS(name="models/gemini-2.5-flash", supported_actions=["generateContent"])]))
        with patch.dict(os.environ, {"JARVIS_GEMINI_VIA": "", "GEMINI_LIVE_MODEL": ""}):
            with self.assertRaises(RuntimeError):
                pick_live_model(cliente, Path("/nao/existe.json"))


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


if __name__ == "__main__":
    unittest.main()
