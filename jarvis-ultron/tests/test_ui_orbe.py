import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QWidget

import ui
import ui_orbe


class _Janela(QWidget):
    def __init__(self):
        super().__init__()
        self.hud = ui.HudCanvas("face.png", parent=self)
        self.hud.resize(900, 600)


class OrbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        os.environ.pop("JARVIS_VISUAL", None)
        self.win = _Janela()
        self.ctl = ui_orbe.instalar(self.win)
        self.pedidos = []
        self.ctl._pedido.connect(lambda: self.pedidos.append(1))

    def test_desenha_em_todos_os_estados(self):
        for estado, falando in [("LISTENING", False), ("SPEAKING", True), ("THINKING", False), ("MUTED", False)]:
            self.win.hud.state, self.win.hud.speaking = estado, falando
            self.win.hud.muted = estado == "MUTED"
            px = QPixmap(self.win.hud.size())
            self.win.hud.render(px)
            self.assertFalse(px.isNull())

    def test_bom_dia_do_usuario_dispara(self):
        self.ctl.ver_texto("You: Bom dia, Jarvis!")
        self.ctl.ver_texto("You: BOM DIA")
        self.assertEqual(len(self.pedidos), 2)

    def test_outras_falas_nao_disparam(self):
        self.ctl.ver_texto("Jarvis: Bom dia, senhor.")
        self.ctl.ver_texto("You: boa tarde")
        self.ctl.ver_texto("You: o bom diálogo")
        self.assertEqual(self.pedidos, [])

    def test_classico_desliga(self):
        os.environ["JARVIS_VISUAL"] = "classico"
        try:
            self.assertIsNone(ui_orbe.instalar(_Janela()))
        finally:
            os.environ.pop("JARVIS_VISUAL", None)


class CenaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_cena_cobre_a_janela_e_alterna_com_f2(self):
        os.environ.pop("JARVIS_VISUAL", None)
        os.environ.pop("JARVIS_CENA", None)
        win = ui.MainWindow("face.png")
        try:
            cena = win._orbe.cena
            self.assertIsNotNone(cena)
            self.assertIs(win.hud.parentWidget(), cena)
            cena.alternar()                      # F2: volta para a tela antiga
            self.assertFalse(cena.isVisible())
            self.assertIsNot(win.hud.parentWidget(), cena)
            cena.alternar()                      # F2 de novo: volta para a cena
            self.assertIs(win.hud.parentWidget(), cena)
        finally:
            win.close()
            win.deleteLater()

    def test_canal_mostra_as_falas(self):
        win = ui.MainWindow("face.png")
        try:
            falas = []
            win._orbe.cena.fala.connect(lambda quem, txt: falas.append((quem, txt)))
            win._orbe.ver_texto("You: que horas são?")
            win._orbe.ver_texto("Jarvis: São dez horas.")
            win._orbe.ver_texto("SYS: conectado")
            self.assertEqual(falas, [("VOCÊ", "que horas são?"), ("JARVIS", "São dez horas.")])
        finally:
            win.close()
            win.deleteLater()


if __name__ == "__main__":
    unittest.main()
