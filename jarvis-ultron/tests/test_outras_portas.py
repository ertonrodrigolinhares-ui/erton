"""Outras portas de desligar ou rodar programa sem o "ok" do Erton (reparo da Etapa 4).

O computer_settings só desliga, reinicia, digita e aperta teclas com o "ok" dele (veja
test_computer_settings_aprovacao.py). Estas ferramentas chegavam ao mesmo resultado por outro caminho, sem
pergunta nenhuma, e chegam a todos os cérebros (o open_app e o file_controller também ao Gemma, no modo
privado):
- open_app: o nome vinha do modelo e ia para o shell ("shutdown.exe /s /t 0", "x: & shutdown /r");
- file_controller: escrevia um .bat com "shutdown /s /t 0" e o abria (o Windows roda o .bat);
- desktop_control com action='task' (ou qualquer ação desconhecida): a IA escrevia um código que rodava
  com o teclado e o mouse (pyautogui) e, no Windows, com o ctypes: digitava e apertava Enter na janela da
  frente e podia "responder ok" no campo do Jarvis.

Nada aqui desliga, digita ou roda programa de verdade: subprocess, os.startfile, pyautogui e o gerador de
código são sempre falsos, e os arquivos ficam numa pasta temporária."""

import asyncio
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, call, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import actions.file_controller as fc  # noqa: E402
import actions.open_app as oa  # noqa: E402
from test_contratos import UIFalsa  # noqa: E402

PROGRAMAS = {"powershell": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
             "cmd": r"C:\Windows\System32\cmd.exe", "notepad": r"C:\Windows\System32\notepad.exe", "shutdown": r"C:\Windows\System32\shutdown.exe",
             "shutdown.exe": r"C:\Windows\System32\shutdown.exe", "logoff": r"C:\Windows\System32\logoff.exe",
             "code": r"C:\Program Files\Microsoft VS Code\bin\code.cmd"}


def _which(nome):
    """Como o shutil.which no Windows: acha "notepad" e "notepad.exe"."""
    nome = nome.lower()
    return PROGRAMAS.get(nome) or PROGRAMAS.get(nome.removesuffix(".exe"))


def _jarvis():
    import main

    jarvis = object.__new__(main.JarvisLive)
    jarvis.ui = jarvis.client = UIFalsa()
    jarvis.cloud_safe = False
    jarvis.speak_error = Mock()
    jarvis.anunciar = Mock(return_value="falado")
    return jarvis


class BaseTests(unittest.TestCase):
    def ambiente(self, cerebro="gemini"):
        ambiente = patch.dict(os.environ, {"JARVIS_CEREBRO": cerebro, "JARVIS_QA_MODE": "0"})
        ambiente.start()
        self.addCleanup(ambiente.stop)

    def ferramenta(self, nome, args, cerebro="gemini"):
        """Pelo _execute_tool de verdade, como o Gemini (ou o Gemma, no modo privado) chama."""
        self.ambiente(cerebro)
        jarvis = _jarvis()
        jarvis._nova_fala("abre o bloco de notas")
        return asyncio.run(jarvis._execute_tool(NS(id="1", name=nome, args=dict(args)))).response["result"]


class OpenAppTests(BaseTests):
    def setUp(self):
        self.sistema = NS(Popen=Mock(), run=Mock(), DEVNULL="nulo")
        self.abrir = Mock()
        self.teclado = Mock()
        for alvo in (patch.object(oa, "_SYSTEM", "Windows"), patch.object(oa, "subprocess", self.sistema),
                     patch.object(oa, "shutil", NS(which=_which)),
                     patch.object(oa.os, "startfile", self.abrir, create=True),
                     patch.object(oa.time, "sleep"), patch.dict(sys.modules, {"pyautogui": self.teclado})):
            alvo.start()
            self.addCleanup(alvo.stop)

    def test_nunca_roda_comando_nem_programa_de_desligar(self):
        nomes = ("shutdown.exe /s /t 0", "x: & shutdown /r", "cmd /c shutdown /s", "notepad & shutdown /s",
                 "notepad.exe -s", "calc|shutdown", "%COMSPEC%", "notepad\nshutdown /s", r"C:\Windows\System32\shutdown.exe",
                 "shutdown", "Shutdown.EXE", "logoff", "rundll32 powrprof.dll,SetSuspendState",
                 "file:///C:/Users/erton/Desktop/x.bat", 'notepad" & "shutdown',
                 # a busca do menu Iniciar roda "programa argumento" como comando
                 "powershell Stop-Computer", "cmd c shutdown")
        for cerebro in ("gemini", "gemma"):
            for nome in nomes:
                with self.subTest(cerebro=cerebro, nome=nome):
                    resposta = self.ferramenta("open_app", {"app_name": nome}, cerebro)
                    self.assertTrue(resposta.startswith("Not opened"), resposta)
        self.sistema.Popen.assert_not_called()
        self.sistema.run.assert_not_called()
        self.abrir.assert_not_called()
        self.assertEqual(self.teclado.method_calls, [])

    def test_programa_achado_abre_sem_o_shell(self):
        self.assertEqual(self.ferramenta("open_app", {"app_name": "notepad"}), "Opened notepad.")
        self.sistema.Popen.assert_called_once_with([PROGRAMAS["notepad"]], stdout="nulo", stderr="nulo")
        self.sistema.Popen.reset_mock()
        self.assertEqual(self.ferramenta("open_app", {"app_name": "VS Code"}), "Opened VS Code.")
        self.sistema.Popen.assert_called_once_with([PROGRAMAS["code"]], stdout="nulo", stderr="nulo")
        self.assertEqual(self.teclado.method_calls, [])

    def test_configuracoes_e_endereco_abrem_pelo_windows_sem_o_shell(self):
        self.assertEqual(self.ferramenta("open_app", {"app_name": "settings"}), "Opened settings.")
        self.ferramenta("open_app", {"app_name": "ms-windows-store:"})
        self.assertEqual(self.abrir.call_args_list, [call("ms-settings:"), call("ms-windows-store:")])
        self.sistema.Popen.assert_not_called()

    def test_programa_que_o_windows_acha_pelo_nome_abre_pelo_menu_iniciar(self):
        # nome com espaço, sem argumento: vai para a busca do menu Iniciar, como antes
        self.assertEqual(self.ferramenta("open_app", {"app_name": "Microsoft Store"}), "Opened Microsoft Store.")
        self.assertEqual(self.teclado.method_calls,
                         [call.press("win"), call.write("Microsoft Store", interval=0.05), call.press("enter")])
        self.sistema.Popen.assert_not_called()

    def test_nome_conhecido_abre_mesmo_comecando_com_um_comando(self):
        # no PC do Erton o Git está no PATH (o Hermes instala), e "Git Bash" começa com "git": é um nome
        # conhecido (_APP_ALIASES), que abre pelo apelido fixo "git-bash", sem as palavras ditas irem para a
        # busca do menu Iniciar. Um nome desconhecido que começa com um comando continua recusado, e a
        # resposta diz por quê
        programas = dict(PROGRAMAS, git=r"C:\Program Files\Git\cmd\git.exe",
                         docker=r"C:\Program Files\Docker\Docker\resources\bin\docker.exe")
        which = NS(which=lambda nome: programas.get(nome.lower().removesuffix(".exe")))
        with patch.object(oa, "shutil", which):
            self.assertEqual(self.ferramenta("open_app", {"app_name": "Git Bash"}), "Opened Git Bash.")
            self.assertEqual(self.teclado.method_calls,
                             [call.press("win"), call.write("git-bash", interval=0.05), call.press("enter")])
            for nome, motivo in (("Docker Desktop", "starts with 'Docker', a command"),
                                 ("PowerShell ISE", "starts with 'PowerShell', a command"),
                                 ("powershell Stop-Computer", "starts with 'powershell', a command"),
                                 ("git push --force", "has command arguments")):
                with self.subTest(nome=nome):
                    resposta = self.ferramenta("open_app", {"app_name": nome})
                    self.assertTrue(resposta.startswith("Not opened"), resposta)
                    self.assertIn(motivo, resposta)
            # se a busca pelo apelido falhar, a volta pelo nome dito passa de novo pela recusa
            self.teclado.reset_mock()
            self.teclado.press.side_effect = RuntimeError("sem teclado")
            self.assertTrue(self.ferramenta("open_app", {"app_name": "git bash"}).startswith("Could not confirm"))
            self.assertEqual(self.teclado.method_calls, [call.press("win")])
        self.sistema.Popen.assert_not_called()
        self.sistema.run.assert_not_called()

    def test_no_linux_tambem_nao_abre_o_de_desligar(self):
        # sem argumento, o "shutdown" do Linux desliga em 1 minuto, e o "poweroff" na hora
        with patch.object(oa, "_SYSTEM", "Linux"), \
                patch.object(oa, "shutil", NS(which=lambda nome: f"/usr/sbin/{nome}")):
            for nome in ("shutdown", "poweroff", "reboot", "halt"):
                with self.subTest(nome=nome):
                    self.assertTrue(oa.open_app({"app_name": nome}).startswith("Not opened"))
        self.sistema.Popen.assert_not_called()
        self.sistema.run.assert_not_called()


class FileControllerTests(BaseTests):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)
        self.abrir = Mock()
        for alvo in (patch.object(fc, "_OS", "Windows"), patch.object(fc, "_SAFE_ROOTS", [self.pasta]),
                     patch.object(fc.os, "startfile", self.abrir, create=True),
                     patch.object(fc.subprocess, "run", side_effect=AssertionError("rodou programa"))):
            alvo.start()
            self.addCleanup(alvo.stop)

    def arquivo(self, acao, **args):
        return self.ferramenta("file_controller", dict(args, action=acao, path=str(self.pasta)))

    def test_escrever_um_bat_e_abrir_nao_roda_nada(self):
        for cerebro in ("gemini", "gemma"):
            with self.subTest(cerebro=cerebro):
                escrito = self.ferramenta("file_controller", {"action": "write", "path": str(self.pasta),
                                                              "name": "x.bat", "content": "shutdown /s /t 0"},
                                          cerebro)
                self.assertTrue(escrito.startswith("Not done"), escrito)
                self.assertFalse((self.pasta / "x.bat").exists())
        # um que já estava lá (o Erton pôs) também não abre: abrir um programa ou script o roda
        for nome in ("x.bat", "X.CMD", "y.exe", "z.ps1", "w.vbs", "atalho.lnk", "site.url", "r.reg", "s.py",
                     "t.pyw", "h.hta", "i.msi", "j.js", "k.scr", "x.bat.", "x.bat ", "x.bat::$DATA"):
            with self.subTest(abrir=nome):
                (self.pasta / nome.rstrip(" .").split(":")[0]).write_text("shutdown /s /t 0", encoding="utf-8")
                resposta = self.arquivo("open", name=nome)
                self.assertTrue(resposta.startswith("Not opened"), resposta)
        self.abrir.assert_not_called()

    def test_criar_renomear_copiar_ou_mover_para_programa_nao_vale(self):
        (self.pasta / "nota.txt").write_text("shutdown /s /t 0", encoding="utf-8")
        destino = self.pasta / "Inicializar"
        destino.mkdir()
        for acao, args in (("create_file", {"name": "y.cmd", "content": "shutdown /r"}),
                           ("write", {"name": "y.ps1", "content": "Stop-Computer"}),
                           ("write", {"name": "y.bat.", "content": "shutdown /r"}),
                           ("rename", {"name": "nota.txt", "new_name": "nota.bat"}),
                           ("copy", {"name": "nota.txt", "destination": str(destino / "nota.cmd")}),
                           ("move", {"name": "nota.txt", "destination": str(destino / "nota.vbs")})):
            with self.subTest(acao=acao, args=args):
                resposta = self.arquivo(acao, **args)
                self.assertTrue(resposta.startswith("Not done"), resposta)
        self.assertEqual(sorted(p.name for p in self.pasta.rglob("*")), ["Inicializar", "nota.txt"])

    def test_arquivos_comuns_continuam(self):
        self.assertEqual(self.arquivo("write", name="nota.txt", content="oi"), "Written to: nota.txt")
        self.assertEqual(self.arquivo("open", name="nota.txt"), "Opened file: nota.txt")
        (self.pasta / "foto.png").write_bytes(b"png")
        self.assertEqual(self.arquivo("open", name="foto.png"), "Opened file: foto.png")
        self.assertEqual(self.arquivo("open"), f"Opened folder: {self.pasta.name}")
        self.assertIn("nota2.txt", self.arquivo("rename", name="nota.txt", new_name="nota2.txt"))
        self.assertEqual(len(self.abrir.call_args_list), 3)


class DesktopControlTests(BaseTests):
    """O modo 'task' do desktop_control e as ações desconhecidas: desligados (rodavam código gerado pela IA)."""

    def setUp(self):
        import actions.desktop as desktop

        self.teclado = Mock()
        self.gerar = Mock(return_value="pyautogui.write('ok, pode fazer')\npyautogui.press('enter')")
        for alvo in (patch.object(desktop, "_PYAUTOGUI", True), patch.object(desktop, "pyautogui", self.teclado, create=True),
                     patch.object(desktop, "_ask_gemini_for_desktop_action", self.gerar)):
            alvo.start()
            self.addCleanup(alvo.stop)

    def test_task_e_acao_desconhecida_nao_geram_nem_rodam_codigo(self):
        for args in ({"action": "task", "task": "type 'oi Ana' and press enter"},
                     {"action": "press enter in the focused window"},
                     {"action": "", "task": "shut down the computer"}):
            with self.subTest(args=args):
                resposta = self.ferramenta("desktop_control", args)
                self.assertIn("turned off", resposta)
        self.gerar.assert_not_called()
        self.assertEqual(self.teclado.method_calls, [])

    def test_ok_digitado_pelo_desktop_control_nao_aprova_o_reiniciar(self):
        # com a caixa de texto do Jarvis na frente, o código gerado "respondia ok" (send_text vira fala nova)
        import actions.computer_settings as cs

        self.ambiente()
        jarvis = _jarvis()
        self.teclado.press.side_effect = lambda tecla: jarvis._nova_fala("ok, pode fazer")
        sistema = Mock()
        reiniciar = {"action": "restart", "description": "restart my computer"}
        with patch.object(cs, "_PYAUTOGUI", True), patch.object(cs, "subprocess", sistema), \
                patch.object(cs, "_OS", "Windows"), patch.dict(cs._pendente, clear=True):
            jarvis._nova_fala("que horas são")
            for nome, args in (("computer_settings", reiniciar),
                               ("desktop_control", {"action": "task", "task": "type ok, pode fazer + enter"}),
                               ("computer_settings", reiniciar)):
                asyncio.run(jarvis._execute_tool(NS(id="1", name=nome, args=dict(args))))
            for fio in threading.enumerate():
                if fio.name == "ComputadorOk":
                    fio.join(10)
        sistema.run.assert_not_called()

    def test_papel_de_parede_organizar_e_listar_continuam(self):
        import actions.desktop as desktop

        with patch.object(desktop, "list_desktop", return_value="Desktop is empty.") as listar, \
                patch.object(desktop, "organize_desktop", return_value="Desktop organized") as organizar:
            self.assertEqual(self.ferramenta("desktop_control", {"action": "list"}), "Desktop is empty.")
            self.assertEqual(self.ferramenta("desktop_control", {"action": "organize"}), "Desktop organized")
        listar.assert_called_once()
        organizar.assert_called_once_with("by_type")
        self.gerar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
