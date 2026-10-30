"""Etapa 8 da reorganização: tudo o que o Erton vê em português, com as frases fixas num lugar só.

- textos em inglês que já saíram não podem voltar ao ui.py, aos .ps1 nem aos .bat;
- core/frases.py: frase() nunca dá erro, e as constantes antigas são apelidos das frases de lá;
- o nome da janela é um só para a tela e para a trava do computer_settings (nunca digitar nela)."""

import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from core import frases  # noqa: E402

# O que não pode voltar (Etapa 8). Cada um já foi texto da tela, de um .ps1 ou de um .bat.
PROIBIDOS = (
    "Quit JARVIS", "Toggle Mute", "Show JARVIS", "INITIALISATION REQUIRED", "INITIALISE SYSTEMS",
    "VERIFYING WITH GEMINI", "Remember API key", "VOICE SELECTION", "IDENTITY PROTOCOL", "ENTER YOUR NAME",
    "KEYBOARD SHORTCUTS", "VISION LINK", "EXECUTING", "is thinking", "Processing request", "Tool error",
    "RUNNING IN THE BACKGROUND", "Report ready", "ALL SYSTEMS NOMINAL", "J.A.R.V.I.S — MARK XXXIX",
    "Drop file here", "default to Sir",
)
ARQUIVOS = ("ui.py", "gemma/instalar_gemma.ps1", "gemma/voltar_gemini.ps1", "claude/instalar_claude.ps1",
            "hermes/instalar_hermes.ps1", "Instalar voz local.bat", "Iniciar Jarvis Ultron.bat")


class TextosEmPortuguesTests(unittest.TestCase):
    def test_nenhum_texto_proibido_voltou(self):
        for nome in ARQUIVOS:
            texto = (RAIZ / nome).read_text(encoding="utf-8", errors="replace")
            for proibido in PROIBIDOS:
                with self.subTest(arquivo=nome, texto=proibido):
                    self.assertNotIn(proibido, texto)

    def test_ps1_continuam_so_em_ascii(self):
        for nome in ARQUIVOS:
            if nome.endswith((".ps1", ".bat")):
                (RAIZ / nome).read_bytes().decode("ascii")  # PowerShell 5.1 e cmd.exe leem assim


class FrasesTests(unittest.TestCase):
    def test_frase_com_chave_desconhecida_devolve_a_propria_chave(self):
        self.assertEqual(frases.frase("chave_que_nao_existe"), "chave_que_nao_existe")

    def test_frase_preenche_os_campos_e_nao_quebra_com_campo_faltando(self):
        self.assertEqual(frases.frase("erro_na_ferramenta", ferramenta="web_search"), "Erro na ferramenta web_search")
        self.assertEqual(frases.frase("erro_na_ferramenta"), "Erro na ferramenta {ferramenta}")
        self.assertEqual(frases.frase("erro_na_ferramenta", outra="x"), "Erro na ferramenta {ferramenta}")

    def test_todas_as_frases_estao_em_portugues_e_sem_empresa(self):
        for chave, texto in frases.FRASES.items():
            with self.subTest(chave=chave):
                self.assertTrue(texto.strip(), chave)
                for ingles in (" the ", " is ", " not ", "JARVIS is"):
                    self.assertNotIn(ingles, texto)

    def test_constantes_antigas_sao_apelidos_das_frases(self):
        import importlib.util

        import main
        from core import cerebro_gemma, hermes_ponte

        spec = importlib.util.spec_from_file_location("videos_frases", RAIZ / "automacoes" / "videos.py")
        videos = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(videos)  # a pasta automacoes não é pacote: carrega como o Jarvis carrega

        self.assertEqual(main.AVISO_MODO_PRIVADO, frases.frase("modo_privado_nuvem"))
        self.assertEqual(videos.AVISO_MODO_PRIVADO, frases.frase("modo_privado_video"))
        self.assertNotEqual(main.AVISO_MODO_PRIVADO, videos.AVISO_MODO_PRIVADO)  # dois avisos, de propósito
        self.assertEqual(cerebro_gemma.AVISO_SEM_WHISPER, frases.frase("sem_whisper"))
        self.assertEqual(cerebro_gemma.AVISO_WHISPER_FALHOU, frases.frase("whisper_falhou"))
        self.assertEqual(hermes_ponte.DEMOROU, frases.frase("hermes_demorou"))
        self.assertEqual(hermes_ponte.SEM_HERMES, frases.frase("sem_hermes"))

    def test_nome_da_janela_e_um_so_para_a_tela_e_para_a_trava_do_teclado(self):
        import actions.computer_settings as cs

        self.assertEqual(frases.TITULO_DA_JANELA, "Jarvis Ultron")
        self.assertEqual(cs.TITULO_DO_JARVIS, frases.TITULO_DA_JANELA)
        self.assertIn('self.setWindowTitle(frase("titulo_janela"))', (RAIZ / "ui.py").read_text(encoding="utf-8"))

    def test_menu_do_icone_em_portugues(self):
        ui = (RAIZ / "ui.py").read_text(encoding="utf-8")
        for chave in ("menu_mostrar", "menu_silenciar", "menu_sair"):
            self.assertIn(f'QAction(frase("{chave}"), self)', ui)
        self.assertEqual(frases.frase("menu_sair"), "Sair do Jarvis")


if __name__ == "__main__":
    unittest.main()
