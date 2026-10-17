"""O LEIA-ME e o VERSAO.txt são o manual do Erton (não é programador): o que eles prometem precisa bater
com o código. Cada teste aqui guarda uma promessa que estava errada na conferência final."""

import os
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

LEIA_ME = (RAIZ / "LEIA-ME.md").read_text(encoding="utf-8")
VERSAO = (RAIZ / "VERSAO.txt").read_text(encoding="utf-8")


def _uma_linha(texto: str) -> str:
    return re.sub(r"\s+", " ", texto)


def _secao(titulo: str) -> str:
    """Texto de uma seção do LEIA-ME (do título até o próximo título do mesmo nível ou acima)."""
    inicio = LEIA_ME.index(titulo)
    nivel = len(titulo) - len(titulo.lstrip("#"))
    resto = LEIA_ME[inicio + len(titulo):]
    fim = re.search(r"^#{1,%d} " % nivel, resto, re.M)
    return _uma_linha(resto[:fim.start()] if fim else resto)


class LeiaMeBateComOCodigoTests(unittest.TestCase):
    def test_reserva_groq_executa_as_tarefas(self):
        # main.RESERVA_FERRAMENTAS_ESSENCIAIS manda e-mail, Hermes, agentes... ao Groq
        import main

        self.assertTrue({"email_control", "hermes_agent", "agent_task"} <= main.JarvisLive.RESERVA_FERRAMENTAS_ESSENCIAIS)
        texto = _uma_linha(LEIA_ME)
        self.assertNotIn("mas não usa as ferramentas", texto)
        self.assertIn("executa as tarefas principais", texto)
        self.assertIn("JARVIS_RESERVA_FERRAMENTAS=0", texto)

    def test_o_x_da_janela_so_esconde_o_jarvis(self):
        secao = _secao("## Tela e cérebro separados")
        self.assertNotIn("Fechando a janela, o cérebro fecha junto", secao)
        self.assertIn("continua ouvindo", secao)
        self.assertIn("Quit JARVIS", secao)
        claude = _secao("## Claude como chefe de tarefas")
        self.assertNotIn("valem quando você reabrir o Jarvis", claude)
        self.assertIn("Quit JARVIS", claude)

    def test_modo_privado_avisa_da_voz_da_microsoft(self):
        # main._falar_reserva manda o texto para a voz da internet sem JARVIS_VOZ_PRIVADA=1
        secao = _secao("### Modo privado por voz")
        self.assertNotIn("nada mais vai para a nuvem", secao)
        self.assertIn("JARVIS_VOZ_PRIVADA=1", secao)
        linha = _uma_linha(VERSAO[VERSAO.index("- Modo privado por voz"):VERSAO.index("- Vídeos com IA")])
        self.assertNotIn("(nada vai para a nuvem)", linha)
        self.assertIn("JARVIS_VOZ_PRIVADA=1", linha)

    def test_selo_do_modo_privado_so_na_tela_azul(self):
        secao = _secao("### Modo privado por voz")
        self.assertIn("tela antiga", secao)
        self.assertIn("🔒 Modo privado ligado", secao)  # a linha que core/ponte.py escreve ao trocar

    def test_trocar_a_chave_nao_manda_apagar_o_env(self):
        # o iniciador recria o .env só com a chave, o Groq e a cidade: o modo privado e o Hermes somem
        secao = _secao("## Trocar a chave do Gemini")
        self.assertNotIn("apague o arquivo", secao)
        self.assertIn("Testar chave do Gemini", secao)
        self.assertIn("Não apague o `.env`", secao)
        for perdido in ("modo privado", "Hermes"):
            self.assertIn(perdido, secao)

    def test_travas_do_claude_contam_o_modo_de_mudar_o_codigo(self):
        # planejar() lê e _aplicar_e_conferir() lê e muda a pasta do programa do Jarvis
        travas = _uma_linha(LEIA_ME[LEIA_ME.index("Travas (no código"):LEIA_ME.index("No **modo privado** nada vai para o Claude")])
        self.assertNotIn("fora das pastas dele, não lê nada", travas)
        self.assertIn("Nas **tarefas**", travas)
        self.assertIn("pasta do programa do Jarvis", travas)
        linha = _uma_linha(VERSAO[VERSAO.index("- Claude como chefe"):VERSAO.index("- Modo privado por voz")])
        self.assertIn("Nas tarefas, ele só escreve", linha)
        self.assertIn("lê e muda a pasta do programa", linha)


class FecharNoXTests(unittest.TestCase):
    def test_aviso_da_bandeja_em_portugues_diz_que_continua_ouvindo(self):
        import ui

        bandeja = MagicMock()
        bandeja.isVisible.return_value = True
        janela = SimpleNamespace(_tray=bandeja, _force_quit=False, _vision_preview=None, hide=MagicMock())
        evento = MagicMock()
        ui.MainWindow.closeEvent(janela, evento)
        evento.ignore.assert_called_once()
        janela.hide.assert_called_once()
        titulo, texto = bandeja.showMessage.call_args[0][:2]
        self.assertIn("continua ouvindo", texto)
        self.assertIn("Quit JARVIS", texto)
        self.assertNotIn("Running in background", titulo + texto)


if __name__ == "__main__":
    unittest.main()
