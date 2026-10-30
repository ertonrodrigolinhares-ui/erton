"""Etapa 7 da reorganização: nada some atrás do anel.

A Cena (tela azul) cobre a janela inteira. O que abre por cima dela tem de continuar por cima depois de
mudar o tamanho da janela, e o que o Jarvis está fazendo (pesquisa, apresentação, ferramenta rodando) tem
de aparecer nela, não escondido atrás. As janelas de teste nunca usam a chave de verdade nem gravam nas
configurações do Erton (igual ao tests/test_tela_contratos.py)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from PyQt6.QtCore import QPoint  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

import ui  # noqa: E402


class _CofreVazio:
    def get(self, _chave):
        return None


class _Janela:
    """MainWindow de teste: sem chave, cofre vazio, configurações numa pasta temporária, 1280x800."""

    def __init__(self, largura: int = 1280, altura: int = 800):
        self._tamanho = (largura, altura)

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
        self.janela.resize(*self._tamanho)
        self.janela.show()
        self.eventos()
        return self.janela

    def eventos(self):
        for _ in range(5):
            QApplication.instance().processEvents()

    def __exit__(self, *_):
        self.janela.hide()
        self.janela.deleteLater()
        self.eventos()
        for troca in reversed(self._trocas):
            troca.stop()
        self._pasta.cleanup()


def _centrada(janela, w) -> bool:
    cw = janela.centralWidget()
    return (w.x(), w.y()) == ((cw.width() - w.width()) // 2, (cw.height() - w.height()) // 2)


def _no_meio_aparece(janela, w) -> bool:
    """O widget no centro de w é w mesmo (ou um filho dele), e não a cena que cobre a janela."""
    alvo = janela.centralWidget().childAt(w.geometry().center())
    return alvo is w or w.isAncestorOf(alvo)


class JanelasPorCimaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_tela_da_chave_nasce_no_centro_e_por_cima_da_cena(self):
        # o defeito anotado na Etapa 2: a tela da chave nascia a (90, 30), calculada com a janela ainda 640x480
        with _Janela() as janela:
            chave = janela._overlay
            self.assertIsNotNone(chave)
            self.assertTrue(chave.isVisible())
            self.assertTrue(_centrada(janela, chave), (chave.x(), chave.y()))
            self.assertTrue(_no_meio_aparece(janela, chave))

    def test_ajustes_atalhos_e_avisos_ficam_por_cima_depois_de_mudar_o_tamanho(self):
        with _Janela() as janela:
            janela._overlay.hide()
            janela._show_settings()
            janela._toggle_shortcuts_overlay()
            janela._show_toast("Aviso de teste", "info", duration=60000)
            _Janela.eventos(self)
            janelas = janela.janelas_por_cima()
            self.assertIn(janela._settings_overlay, janelas)
            self.assertIn(janela._shortcuts_overlay, janelas)
            self.assertTrue(any(isinstance(w, ui.ToastNotification) for w in janelas))
            self.assertNotIn(janela._overlay, janelas)  # escondida: não entra

            janela.resize(1100, 700)
            _Janela.eventos(self)
            for w in (janela._settings_overlay, janela._shortcuts_overlay):
                with self.subTest(janela=w.__class__.__name__):
                    self.assertTrue(_centrada(janela, w), (w.x(), w.y()))
            # na frente da cena (que cobre a janela inteira) e um do outro conforme a ordem da lista
            self.assertTrue(_no_meio_aparece(janela, janela._shortcuts_overlay))
            aviso = next(w for w in janelas if isinstance(w, ui.ToastNotification))
            self.assertTrue(_no_meio_aparece(janela, aviso))

    def test_janelinha_arrastada_nao_e_recentrada_mas_continua_na_frente(self):
        with _Janela() as janela:
            janela._overlay.hide()
            janela._show_settings()
            ajustes = janela._settings_overlay
            ajustes.move(QPoint(30, 40))
            ajustes._has_user_position = True  # o que o arrastar com o mouse marca
            janela.resize(1100, 700)
            _Janela.eventos(self)
            self.assertEqual((ajustes.x(), ajustes.y()), (30, 40))
            self.assertTrue(_no_meio_aparece(janela, ajustes))

    def test_a_cena_traz_a_lista_inteira_ao_mudar_de_tamanho(self):
        with _Janela() as janela:
            cena = janela._orbe.cena
            janela._overlay.hide()
            janela._show_settings()
            with patch.object(janela, "janelas_por_cima", wraps=janela.janelas_por_cima) as lista:
                cena._trazer_janelas()
            self.assertEqual(lista.call_count, 1)
            # a cena, redesenhada por cima (raise_), não esconde os Ajustes
            cena.raise_()
            cena._trazer_janelas()
            self.assertTrue(_no_meio_aparece(janela, janela._settings_overlay))


if __name__ == "__main__":
    unittest.main()
