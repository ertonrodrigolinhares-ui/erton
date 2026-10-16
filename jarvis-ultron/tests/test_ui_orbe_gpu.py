import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import ui_orbe_gpu as gpu


class PermissaoDaPlacaDeVideoTests(unittest.TestCase):
    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp())
        self.patches = [patch.object(gpu, "PASTA", self.pasta),
                        patch.object(gpu, "TESTANDO", self.pasta / "orbe_gpu_testando"),
                        patch.object(gpu, "FALHOU", self.pasta / "orbe_gpu_falhou")]
        for p in self.patches:
            p.start()
        from PyQt6.QtGui import QGuiApplication
        self.plataforma = patch.object(QGuiApplication, "platformName", staticmethod(lambda: "xcb"))
        self.plataforma.start()

    def tearDown(self):
        self.plataforma.stop()
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.pasta, ignore_errors=True)

    def test_ligada_por_padrao(self):
        with patch.dict(os.environ, {"JARVIS_ORBE_GPU": ""}):
            self.assertTrue(gpu.gpu_permitida())

    def test_desligada_pelo_env(self):
        with patch.dict(os.environ, {"JARVIS_ORBE_GPU": "0"}):
            self.assertFalse(gpu.gpu_permitida())

    def test_ultima_abertura_caiu_ao_ligar_a_placa(self):
        gpu.TESTANDO.write_text("ligando")
        with patch.dict(os.environ, {"JARVIS_ORBE_GPU": ""}):
            self.assertFalse(gpu.gpu_permitida())
            self.assertTrue(gpu.FALHOU.exists())        # lembra para as próximas aberturas
            self.assertFalse(gpu.TESTANDO.exists())
            self.assertFalse(gpu.gpu_permitida())

    def test_forcar_tenta_mesmo_depois_de_falhar(self):
        gpu.FALHOU.write_text("falhou")
        with patch.dict(os.environ, {"JARVIS_ORBE_GPU": "forcar"}):
            self.assertTrue(gpu.gpu_permitida())

    def test_tela_de_teste_sem_placa_de_video(self):
        self.plataforma.stop()
        from PyQt6.QtGui import QGuiApplication
        with patch.object(QGuiApplication, "platformName", staticmethod(lambda: "offscreen")):
            self.assertFalse(gpu.gpu_permitida())
        self.plataforma.start()


JANELA = textwrap.dedent("""
    import os, sys
    os.environ["HOME"] = sys.argv[1]
    sys.path.insert(0, sys.argv[2]); os.chdir(sys.argv[2])
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication
    app = QApplication([])
    import ui_orbe_gpu
    if sys.argv[3] == "quebrado":
        ui_orbe_gpu.FRAGMENTOS = "isto não é um programa de placa de vídeo"
    import ui
    win = ui.MainWindow("face.png"); win.resize(1000, 640)
    ov = getattr(win, "_overlay", None)
    if ov: ov.hide()
    win.move(0, 0); win.show()
    def fim():
        img = app.primaryScreen().grabWindow(0, 0, 0, 1000, 640).toImage()
        hud = win.hud
        cx, cy = 500, 320
        R = min(hud.width(), hud.height()) * 0.34
        brilho = max(img.pixelColor(int(cx + R * dx), int(cy + R * dy)).lightness()
                     for dx in [i / 20 - 1.3 for i in range(53)] for dy in (0.0,))
        camada = getattr(hud, "_orbe_gpu", None)
        print("CAMADA", "ativa" if camada is not None and camada.ativo else "nao")
        print("BRILHO_NO_ANEL", brilho)
        app.quit()
    QTimer.singleShot(2500, fim)
    app.exec()
""")


@unittest.skipUnless(shutil.which("xvfb-run"), "precisa de uma tela virtual com OpenGL (xvfb-run)")
class PlacaDeVideoDeVerdadeTests(unittest.TestCase):
    """Abre a janela do Jarvis numa tela virtual com OpenGL e confere o anel na tela de verdade."""

    def _abrir(self, modo):
        casa = tempfile.mkdtemp()
        script = Path(casa) / "janela.py"
        script.write_text(JANELA, encoding="utf-8")
        env = dict(os.environ, QT_QPA_PLATFORM="xcb", JARVIS_ORBE_GPU="1")
        r = subprocess.run(["xvfb-run", "-a", "-s", "-screen 0 1280x800x24", sys.executable, str(script),
                            casa, str(RAIZ), modo], capture_output=True, text=True, timeout=120, env=env)
        saida = r.stdout + r.stderr
        falhou = (Path(casa) / ".jarvis" / "orbe_gpu_falhou").exists()
        testando = (Path(casa) / ".jarvis" / "orbe_gpu_testando").exists()
        shutil.rmtree(casa, ignore_errors=True)
        return r.returncode, saida, falhou, testando

    def _valor(self, saida, chave):
        for linha in saida.splitlines():
            if linha.startswith(chave + " "):
                return linha.split(" ", 1)[1]
        self.fail(f"{chave} não apareceu:\n{saida[-2000:]}")

    def test_anel_desenhado_pela_placa_de_video(self):
        codigo, saida, falhou, testando = self._abrir("normal")
        self.assertEqual(codigo, 0, saida[-2000:])
        self.assertEqual(self._valor(saida, "CAMADA"), "ativa")
        self.assertGreater(int(self._valor(saida, "BRILHO_NO_ANEL")), 120)  # os fios aparecem na tela
        self.assertFalse(falhou)
        self.assertFalse(testando)  # desenhou: a marca de teste some

    def test_desenho_quebrado_volta_sozinho_ao_desenho_normal(self):
        codigo, saida, falhou, _ = self._abrir("quebrado")
        self.assertEqual(codigo, 0, saida[-2000:])  # a janela não fechou
        self.assertEqual(self._valor(saida, "CAMADA"), "nao")
        self.assertGreater(int(self._valor(saida, "BRILHO_NO_ANEL")), 120)  # o desenho normal assumiu
        self.assertTrue(falhou)  # e lembra para não tentar de novo


if __name__ == "__main__":
    unittest.main()
