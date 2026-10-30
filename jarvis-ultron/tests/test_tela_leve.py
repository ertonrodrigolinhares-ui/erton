"""Etapa 6 da reorganização: a tela mais leve.

O que o Erton sente no PC com o Jarvis aberto, garantido aqui:
- importar o ui.py não cria fio nenhum (antes, um fio lia o sistema a cada 1,5 s desde a importação);
- a tela antiga, a Cena (tela azul) e a tela Stark leem CPU e memória da mesma fonte (core/metricas.py);
- com a Cena na frente, os relógios da tela antiga (hora, medidores, grade de agentes) e da Stark ficam
  parados: ninguém vê esses painéis;
- o anel continua pulsando com a voz (o _nivel_suave do HudCanvas), mas a esfera antiga, que o anel
  substituiu, não é mais animada por baixo dele.

As janelas de teste nunca usam a chave de verdade nem gravam nas configurações do Erton (igual ao
tests/test_tela_contratos.py)."""

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

import ui  # noqa: E402
import ui_orbe  # noqa: E402
import ui_stark  # noqa: E402
from core import metricas  # noqa: E402

RETRATO = {"cpu": 37.0, "mem": 51.0, "disco": 63.0, "net": 0.5, "gpu": -1.0, "tmp": -1.0}


class _CofreVazio:
    def get(self, _chave):
        return None


class ImportarUiNaoTrabalhaTests(unittest.TestCase):
    def test_importar_o_ui_nao_cria_fio_nenhum(self):
        codigo = ("import os, sys, threading; os.environ['QT_QPA_PLATFORM'] = 'offscreen'; "
                  "sys.path.insert(0, %r); antes = threading.active_count(); import ui; "
                  "print(threading.active_count() - antes)" % str(RAIZ))
        saida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=120,
                               cwd=str(RAIZ))
        self.assertEqual(saida.returncode, 0, saida.stderr)
        self.assertEqual(saida.stdout.strip().splitlines()[-1], "0")


class MesmaFonteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_tela_antiga_le_do_core_metricas(self):
        with patch.object(metricas, "ler", return_value=dict(RETRATO)):
            self.assertEqual(ui._get_metrics()["cpu"], 37.0)

    def test_stark_le_cpu_e_memoria_do_core_metricas(self):
        sistema = ui_stark.Sistema()
        with patch.object(metricas, "ler", return_value=dict(RETRATO)):
            dados = sistema.atualizar()
        self.assertEqual((dados["cpu"], dados["ram"]), (37.0, 51.0))
        self.assertIn("disco_pct", dados)  # o resto (disco, rede, bateria) continua sendo lido aqui


class _JanelaDeTeste:
    """Uma MainWindow sem chave, sem cofre e com as configurações numa pasta temporária."""

    def __enter__(self):
        self._pasta = tempfile.TemporaryDirectory()
        pasta = Path(self._pasta.name)
        self._trocas = [
            patch.dict(os.environ),
            patch.object(ui, "UI_SETTINGS_FILE", pasta / "settings.json"),
            patch.object(ui, "API_FILE", pasta / "api_keys.json"),
            patch.object(ui, "get_secret_store", return_value=_CofreVazio()),
            patch.object(ui, "BASE_DIR", pasta),
            patch.object(ui.MainWindow, "_setup_system_tray", lambda self: None),
        ]
        for troca in self._trocas:
            troca.start()
        for nome in ("JARVIS_VISUAL", "JARVIS_CENA", "JARVIS_TELA", "GEMINI_API_KEY"):
            os.environ.pop(nome, None)
        self.janela = ui.MainWindow("face.png")
        self.janela.show()
        QApplication.instance().processEvents()
        return self.janela

    def __exit__(self, *_):
        self.janela.hide()
        self.janela.deleteLater()
        QApplication.instance().processEvents()
        for troca in reversed(self._trocas):
            troca.stop()
        self._pasta.cleanup()


class CenaNaFrenteParaOsRelogiosTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_relogios_da_tela_antiga_param_com_a_cena_na_frente_e_voltam_com_f2(self):
        with _JanelaDeTeste() as janela:
            cena = janela._orbe.cena
            self.assertTrue(cena.ativa and cena.isVisible())
            self.assertTrue(ui._tela_antiga_parada(janela))
            self.assertTrue(ui._tela_antiga_parada(janela._agent_grid))
            janela._clock_lbl.setText("PARADO")
            janela._bar_cpu.set_value(1.0, "PARADO")
            with patch.object(ui, "_get_metrics", return_value=dict(RETRATO)) as leitura:
                janela._tick_clock()
                janela._update_metrics()
            self.assertEqual(janela._clock_lbl.text(), "PARADO")
            self.assertEqual(janela._bar_cpu._text, "PARADO")
            self.assertEqual(leitura.call_count, 0)  # nem o sistema é lido para o painel escondido

            cena.alternar()  # F2: a tela antiga aparece, e os relógios andam
            try:
                self.assertFalse(ui._tela_antiga_parada(janela))
                with patch.object(ui, "_get_metrics", return_value=dict(RETRATO)):
                    janela._tick_clock()
                    janela._update_metrics()
                self.assertNotEqual(janela._clock_lbl.text(), "PARADO")
                self.assertEqual(janela._bar_cpu._text, "37%")
            finally:
                cena.alternar()
            self.assertTrue(ui._tela_antiga_parada(janela))

    def test_grade_de_agentes_nao_anima_atras_da_cena(self):
        with _JanelaDeTeste() as janela:
            grade = janela._agent_grid
            antes = grade._tick
            grade._animate()
            self.assertEqual(grade._tick, antes)
            janela._orbe.cena.alternar()  # F2: tela antiga na frente...
            janela._set_command_center(True, announce=False)  # ...com o Command Center aberto...
            janela._left_stack.setCurrentIndex(1)  # ...na aba dos agentes: aí sim a grade aparece
            try:
                self.assertFalse(ui._tela_antiga_parada(grade))
                grade._animate()
                self.assertEqual(grade._tick, antes + 1)
            finally:
                janela._set_command_center(False, announce=False)
                janela._orbe.cena.alternar()

    def test_janela_escondida_na_bandeja_tambem_para(self):
        with _JanelaDeTeste() as janela:
            janela._orbe.cena.alternar()
            try:
                self.assertFalse(ui._tela_antiga_parada(janela))
                janela.hide()
                self.assertTrue(ui._tela_antiga_parada(janela))
                janela.show()
            finally:
                janela._orbe.cena.alternar()

    def test_tela_stark_nao_le_o_sistema_atras_da_cena(self):
        with patch.dict(os.environ, {"JARVIS_TEMA_STARK": "1"}), _JanelaDeTeste() as janela:
            stark = getattr(janela, "_tela_stark", None)
            if stark is None:
                self.skipTest("a tela Stark não está ligada nesta configuração")
            self.assertTrue(stark._coberta())
            with patch.object(stark.sistema, "atualizar", side_effect=AssertionError("leu o sistema")):
                stark._a_cada_segundo()
            janela._orbe.cena.alternar()
            try:
                self.assertFalse(stark._coberta())
            finally:
                janela._orbe.cena.alternar()


class _Janela(QWidget):
    def __init__(self):
        super().__init__()
        self.hud = ui.HudCanvas("face.png", parent=self)
        self.hud.resize(600, 400)


class EsferaAntigaParadaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        os.environ.pop("JARVIS_VISUAL", None)
        self.win = _Janela()
        self.ctl = ui_orbe.instalar(self.win)
        self.hud = self.win.hud
        self.hud._tmr.stop()  # os passos são dados à mão nos testes
        self.win.show()  # escondida, a economia não redesenha (e não marca _quadro_novo)
        QApplication.instance().processEvents()

    def tearDown(self):
        self.win.hide()
        self.win.deleteLater()
        QApplication.instance().processEvents()

    def test_anel_continua_pulsando_com_a_voz(self):
        self.hud.speaking = True
        self.hud.nivel_voz, self.hud.nivel_voz_em = 1.0, time.time()
        for _ in range(5):
            self.hud._step()
        self.assertGreater(self.hud._nivel_suave, 0.5)
        self.hud.nivel_voz_em = 0.0  # a voz parou: o nível desce suave
        for _ in range(5):
            self.hud._step()
        self.assertLess(self.hud._nivel_suave, 0.5)
        self.assertTrue(self.hud._quadro_novo)

    def test_esfera_antiga_nao_e_animada_quando_o_anel_existe(self):
        self.assertIsNotNone(self.hud._orbe)
        foto = (self.hud._rotation_y, list(self.hud._ring_angles), self.hud._scale, self.hud._brightness,
                [list(n) for n in self.hud._nodes], self.hud._blink_tick, self.hud._lattice_angle)
        for _ in range(10):
            self.hud._step()
        self.assertEqual(foto, (self.hud._rotation_y, list(self.hud._ring_angles), self.hud._scale,
                                self.hud._brightness, [list(n) for n in self.hud._nodes], self.hud._blink_tick,
                                self.hud._lattice_angle))
        self.assertEqual(self.hud._pulses, [])

    def test_sem_o_anel_a_esfera_antiga_anima_como_sempre(self):
        os.environ["JARVIS_VISUAL"] = "classico"
        try:
            win = _Janela()
            self.assertIsNone(ui_orbe.instalar(win))
            hud = win.hud
            hud._tmr.stop()
            antes = hud._rotation_y
            for _ in range(3):
                hud._step()
            self.assertNotEqual(hud._rotation_y, antes)
        finally:
            os.environ.pop("JARVIS_VISUAL", None)


if __name__ == "__main__":
    unittest.main()
