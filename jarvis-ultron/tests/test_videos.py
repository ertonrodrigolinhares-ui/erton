import importlib.util
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


def _modulo():
    spec = importlib.util.spec_from_file_location("auto_videos", RAIZ / "automacoes" / "videos.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class JarvisFalso:
    def __init__(self, fala=""):
        self._current_input_transcript = fala
        self._last_input_transcript = fala
        self.avisos, self.logs = [], []
        self.ui = NS(write_log=self.logs.append)

    def _falar_aviso(self, texto):
        self.avisos.append(texto)


def _esperar_video():
    for t in threading.enumerate():
        if t.name == "VideoVeo":
            t.join(5)


class OkAntesDoVideoTests(unittest.TestCase):
    def setUp(self):
        self.m = _modulo()
        self.pedido = {"description": "a triathlete crossing the finish line in Hawaii at sunset", "seconds": 8}

    def test_primeiro_mostra_o_preco_e_nao_faz_nada(self):
        with patch.object(self.m, "gerar") as gerar:
            r = self.m.executar(dict(self.pedido), JarvisFalso())
        self.assertIn("US$ 0.96", r)  # 8 s x US$ 0,12 (rápido)
        self.assertIn("R$", r)
        gerar.assert_not_called()

    def test_confirmar_sem_ok_do_usuario_nao_faz(self):
        with patch.object(self.m, "gerar") as gerar:
            self.m.executar(dict(self.pedido), JarvisFalso())
            r = self.m.executar(dict(self.pedido, confirm=True), JarvisFalso("hmm, quanto fica mesmo?"))
            _esperar_video()
        self.assertIn("Not confirmed", r)
        gerar.assert_not_called()

    def test_confirmar_sem_ter_mostrado_o_preco_nao_faz(self):
        with patch.object(self.m, "gerar") as gerar:
            r = self.m.executar(dict(self.pedido, confirm=True), JarvisFalso("ok, pode fazer"))
            _esperar_video()
        self.assertIn("Not confirmed", r)
        gerar.assert_not_called()

    def test_ok_para_outro_video_nao_vale(self):
        with patch.object(self.m, "gerar") as gerar:
            self.m.executar(dict(self.pedido), JarvisFalso())
            r = self.m.executar(dict(self.pedido, seconds=4, confirm=True), JarvisFalso("ok, pode fazer"))
            _esperar_video()
        self.assertIn("Not confirmed", r)
        gerar.assert_not_called()

    def test_com_ok_faz_em_segundo_plano_abre_e_avisa(self):
        jarvis = JarvisFalso("ok, pode fazer")
        with patch.object(self.m, "gerar", return_value=Path("/tmp/video.mp4")) as gerar, \
                patch.object(self.m, "_abrir") as abrir:
            self.m.executar(dict(self.pedido), JarvisFalso())
            r = self.m.executar(dict(self.pedido, confirm=True), jarvis)
            _esperar_video()
        self.assertIn("background", r)
        gerar.assert_called_once()
        abrir.assert_called_once_with(Path("/tmp/video.mp4"))
        self.assertIn("pronto", jarvis.avisos[0])
        # o mesmo ok não serve para um segundo vídeo
        with patch.object(self.m, "gerar") as gerar2:
            r2 = self.m.executar(dict(self.pedido, confirm=True), jarvis)
        self.assertIn("Not confirmed", r2)
        gerar2.assert_not_called()

    def test_pode_fazer_dito_junto_com_o_pedido_nao_vale(self):
        """O ok tem que vir numa fala nova, depois de o Erton ouvir o preço."""
        jarvis = JarvisFalso("faz um vídeo de um triatleta no Havaí, pode fazer")
        with patch.object(self.m, "gerar") as gerar:
            self.m.executar(dict(self.pedido), jarvis)
            r = self.m.executar(dict(self.pedido, confirm=True), jarvis)
            _esperar_video()
        self.assertIn("Not confirmed", r)
        gerar.assert_not_called()

    def test_erro_do_google_vira_aviso_em_portugues(self):
        jarvis = JarvisFalso("ok, pode fazer")
        with patch.object(self.m, "gerar", side_effect=RuntimeError("403 billing account not enabled")):
            self.m.executar(dict(self.pedido), JarvisFalso())
            self.m.executar(dict(self.pedido, confirm=True), jarvis)
            _esperar_video()
        self.assertIn("faturamento", jarvis.avisos[0])


class Operacao:
    def __init__(self, voltas, video):
        self.voltas, self.video = voltas, video

    @property
    def done(self):
        return self.voltas <= 0

    @property
    def result(self):
        return NS(generated_videos=[NS(video=self.video)])

    error = None


class VideoFalso:
    uri = None
    video_bytes = b"mp4"

    def save(self, caminho):
        Path(caminho).write_bytes(self.video_bytes)


class ClienteVeo:
    def __init__(self, nomes, inexistentes=()):
        self.nomes, self.inexistentes, self.pedidos = nomes, set(inexistentes), []
        self.models = NS(list=lambda config=None: [NS(name=f"models/{n}") for n in self.nomes],
                         generate_videos=self._gerar)
        self.operations = NS(get=self._andar)

    def _gerar(self, model, source, config):
        self.pedidos.append((model, config))
        if model in self.inexistentes:
            raise Exception(f"404 NOT_FOUND {model}")
        return Operacao(2, VideoFalso())

    def _andar(self, operacao):
        operacao.voltas -= 1
        return operacao


class GerarTests(unittest.TestCase):
    def setUp(self):
        self.m = _modulo()
        self.casa = tempfile.mkdtemp()

    def test_escolhe_o_veo_rapido_mais_novo_e_salva(self):
        cliente = ClienteVeo(["veo-3.0-fast-generate-001", "veo-3.1-fast-generate-preview", "veo-3.1-generate-preview"])
        with patch.object(self.m, "pasta_videos", lambda: Path(self.casa)):
            arquivo = self.m.gerar("a runner", 8, "rapido", True, cliente=cliente, dormir=lambda s: None)
        self.assertTrue(arquivo.exists())
        modelo, config = cliente.pedidos[0]
        self.assertEqual(modelo, "veo-3.1-fast-generate-preview")
        self.assertEqual(config.aspect_ratio, "9:16")
        self.assertEqual(config.duration_seconds, 8)

    def test_modelo_que_nao_existe_tenta_o_proximo(self):
        cliente = ClienteVeo(["veo-3.1-generate-preview", "veo-3.1-generate-001"], inexistentes={"veo-3.1-generate-preview"})
        with patch.object(self.m, "pasta_videos", lambda: Path(self.casa)):
            arquivo = self.m.gerar("a runner", 4, "maximo", False, cliente=cliente, dormir=lambda s: None)
        self.assertTrue(arquivo.exists())
        self.assertEqual([p[0] for p in cliente.pedidos], ["veo-3.1-generate-preview", "veo-3.1-generate-001"])

    def test_carrega_como_ferramenta_do_jarvis(self):
        from core.automacoes import carregar_ferramentas

        carga = carregar_ferramentas(RAIZ / "automacoes")
        self.assertIn("generate_video", carga.ferramentas)
        self.assertNotIn("videos.py", carga.na_tela)


if __name__ == "__main__":
    unittest.main()
