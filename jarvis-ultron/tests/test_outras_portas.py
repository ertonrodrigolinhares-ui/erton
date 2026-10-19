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
             "code": r"C:\Program Files\Microsoft VS Code\bin\code.cmd",
             "control": r"C:\Windows\System32\control.exe",
             # um caminho com a barra normal ou a invertida: o which do Windows acha o arquivo (e o Popen o rodaria)
             "c:/users/erton/downloads/instalar.bat": r"C:\Users\erton\Downloads\instalar.bat",
             "./x.bat": r"C:\Users\erton\x.bat",
             r"c:\users\erton\downloads\instalar.bat": r"C:\Users\erton\Downloads\instalar.bat",
             r".\x.bat": r"C:\Users\erton\x.bat"}


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
        # o menu Iniciar dos testes: duas pastas vazias (as de verdade, no PC do Erton, ficam de fora)
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.menu = {nome: Path(pasta.name, nome, "Microsoft", "Windows", "Start Menu", "Programs")
                     for nome in ("ProgramData", "APPDATA")}
        for alvo in (patch.object(oa, "_SYSTEM", "Windows"), patch.object(oa, "subprocess", self.sistema),
                     patch.object(oa, "shutil", NS(which=_which)),
                     patch.object(oa.os, "startfile", self.abrir, create=True),
                     patch.dict(os.environ, {nome: str(Path(pasta.name, nome)) for nome in self.menu}),
                     patch.object(oa.time, "sleep"), patch.dict(sys.modules, {"pyautogui": self.teclado})):
            alvo.start()
            self.addCleanup(alvo.stop)

    def atalho(self, onde, caminho):
        """Põe um atalho (.lnk) no menu Iniciar falso: onde = "ProgramData" (todos) ou "APPDATA" (o Erton)."""
        arquivo = self.menu[onde] / caminho
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_bytes(b"L\x00\x00\x00")
        return str(arquivo)

    def test_nunca_roda_comando_nem_programa_de_desligar(self):
        nomes = ("shutdown.exe /s /t 0", "x: & shutdown /r", "cmd /c shutdown /s", "notepad & shutdown /s",
                 "notepad.exe -s", "calc|shutdown", "%COMSPEC%", "notepad\nshutdown /s", r"C:\Windows\System32\shutdown.exe",
                 "shutdown", "Shutdown.EXE", "logoff", "rundll32 powrprof.dll,SetSuspendState",
                 "file:///C:/Users/erton/Desktop/x.bat", 'notepad" & "shutdown',
                 # caminho com a barra normal (o which acha o arquivo; só a regra da "/" o recusa)
                 "C:/Users/erton/Downloads/instalar.bat", "./x.bat",
                 # e com a barra invertida (só a regra dos sinais, que tem a "\", o recusa)
                 r"C:\Users\erton\Downloads\instalar.bat", r".\x.bat",
                 # caractere de controle, sem "/", sem " -" e sem um comando na primeira palavra (só a regra dos
                 # caracteres de controle o recusa): na busca do menu Iniciar, o "\n" viraria um Enter no meio
                 "PowerShel\nStop-Computer", "Bloco\tshutdown", "x\x1by",
                 # o "&" só vale entre espaços e depois de uma palavra que não é um comando
                 "cmd & shutdown", "x &shutdown", "x& shutdown",
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
        # nome com espaço, sem argumento: vai para a busca do menu Iniciar, como antes. Os aplicativos do
        # Windows com "&" no nome ("Movies & TV", o Filmes e TV) também: nada passa pelo shell
        for nome in ("Microsoft Store", "Movies & TV", "Snip & Sketch", "Solitaire & Casual Games"):
            with self.subTest(nome=nome):
                self.teclado.reset_mock()
                self.assertEqual(self.ferramenta("open_app", {"app_name": nome}), f"Opened {nome}.")
                self.assertEqual(self.teclado.method_calls,
                                 [call.press("win"), call.write(nome, interval=0.05), call.press("enter")])
        self.sistema.Popen.assert_not_called()

    def test_nome_conhecido_abre_mesmo_comecando_com_um_comando(self):
        # no PC do Erton o Git está no PATH (o Hermes instala), e "Git Bash" começa com "git": é um nome
        # conhecido (_APP_ALIASES), que abre pelo apelido fixo "git-bash", sem as palavras ditas irem para a
        # busca do menu Iniciar. Um nome desconhecido que começa com um comando, sem um atalho do menu Iniciar
        # com esse nome exato (aqui o menu Iniciar está vazio), continua recusado, e a resposta diz por quê
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

    def test_nome_que_comeca_com_um_comando_abre_pelo_atalho_do_menu_iniciar(self):
        # "Docker Desktop" começa com "docker", um comando no PATH: abre pelo atalho do menu Iniciar com o nome
        # exato (é ele que a busca abriria), sem argumento. Sem esse atalho, continua recusado, e nunca vai
        # para a busca do menu Iniciar (que rodaria "docker Desktop")
        programas = dict(PROGRAMAS, docker=r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
                         git=r"C:\Program Files\Git\cmd\git.exe", print=r"C:\Windows\System32\print.exe")
        docker = self.atalho("ProgramData", "Docker Desktop.lnk")
        git_gui = self.atalho("ProgramData", "Git/Git GUI.lnk")
        impressao = self.atalho("APPDATA", "Administrative Tools/Print Management.lnk")
        self.atalho("ProgramData", "PowerShell/PowerShell 7 (x64).lnk")  # outro nome: não vale para "PowerShell 7"
        with patch.object(oa, "shutil", NS(which=lambda nome: programas.get(nome.lower().removesuffix(".exe")))):
            for nome, atalho in (("Docker Desktop", docker), ("docker desktop", docker), ("Git GUI", git_gui),
                                 ("Print Management", impressao)):
                with self.subTest(nome=nome):
                    self.abrir.reset_mock()
                    self.assertEqual(self.ferramenta("open_app", {"app_name": nome}), f"Opened {nome}.")
                    self.abrir.assert_called_once_with(atalho)
            # o atalho tem de ter o nome inteiro: "Docker Desktop App", "PowerShell 7", "docker run x" e
            # "powershell Stop-Computer" continuam recusados
            for nome in ("Docker Desktop App", "PowerShell 7", "docker run x", "powershell Stop-Computer", "Docker"):
                with self.subTest(nome=nome):
                    resposta = self.ferramenta("open_app", {"app_name": nome})
                    if nome == "Docker":  # uma palavra só: o docker.exe, sem argumento, como antes
                        self.assertEqual(resposta, "Opened Docker.")
                        continue
                    self.assertTrue(resposta.startswith("Not opened"), resposta)
            self.assertEqual(self.abrir.call_count, 1)
            # se o atalho não abrir, o nome não vai para a busca do menu Iniciar
            self.abrir.side_effect = OSError("atalho quebrado")
            self.assertTrue(self.ferramenta("open_app", {"app_name": "Docker Desktop"}).startswith("Could not confirm"))
        self.assertEqual(self.teclado.method_calls, [])
        self.sistema.Popen.assert_called_once_with([programas["docker"]], stdout="nulo", stderr="nulo")

    def test_claude_abre_o_aplicativo_e_nunca_o_do_terminal(self):
        # o Instalar Claude.bat põe o claude.exe (o Claude Code de terminal) no PATH: "Claude" abria ele
        # escondido, sem janela, e "Claude Desktop" era recusado. Agora os dois abrem o aplicativo Claude, pelo
        # atalho do menu Iniciar ou, sem atalho, pela busca, e nunca pelo PATH
        programas = dict(PROGRAMAS, claude=r"C:\Users\Erton\.local\bin\claude.exe")
        with patch.object(oa, "shutil", NS(which=lambda nome: programas.get(nome.lower().removesuffix(".exe")))):
            for nome in ("Claude", "claude", "Claude Desktop", "Claude App"):
                with self.subTest(nome=nome, atalho=False):
                    self.teclado.reset_mock()
                    self.assertEqual(self.ferramenta("open_app", {"app_name": nome}), f"Opened {nome}.")
                    self.assertEqual(self.teclado.method_calls,
                                     [call.press("win"), call.write("Claude", interval=0.05), call.press("enter")])
            self.teclado.reset_mock()
            claude = self.atalho("APPDATA", "Anthropic/Claude.lnk")
            for nome in ("Claude", "Claude Desktop"):
                with self.subTest(nome=nome, atalho=True):
                    self.abrir.reset_mock()
                    self.assertEqual(self.ferramenta("open_app", {"app_name": nome}), f"Opened {nome}.")
                    self.abrir.assert_called_once_with(claude)
        self.assertEqual(self.teclado.method_calls, [])
        self.sistema.Popen.assert_not_called()

    def test_painel_de_controle_abre_o_control_exe(self):
        # "control" é o control.exe do Windows: "Control Panel" era recusado. O nome tem de ser inteiro: o
        # "NVIDIA Control Panel" não vira o Painel de Controle do Windows
        for nome in ("Control Panel", "Painel de Controle", "painel de controle"):
            with self.subTest(nome=nome):
                self.sistema.Popen.reset_mock()
                self.assertEqual(self.ferramenta("open_app", {"app_name": nome}), f"Opened {nome}.")
                self.sistema.Popen.assert_called_once_with([PROGRAMAS["control"]], stdout="nulo", stderr="nulo")
        self.sistema.Popen.reset_mock()
        self.assertEqual(self.ferramenta("open_app", {"app_name": "NVIDIA Control Panel"}), "Opened NVIDIA Control Panel.")
        self.sistema.Popen.assert_not_called()
        self.assertEqual(self.teclado.method_calls,
                         [call.press("win"), call.write("NVIDIA Control Panel", interval=0.05), call.press("enter")])

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

    def test_caminho_inteiro_sem_o_nome_tambem_nao_vale(self):
        # a declaração manda pôr o caminho inteiro em path, sem name ("Use action=open for a file path"): a trava
        # confere o nome do arquivo de verdade, e não o parâmetro name, que aqui fica vazio
        for nome in ("x.bat", "y.cmd", "atalho.lnk"):
            (self.pasta / nome).write_text("shutdown /s /t 0", encoding="utf-8")
            with self.subTest(acao="open", nome=nome):
                resposta = self.ferramenta("file_controller", {"action": "open", "path": str(self.pasta / nome)})
                self.assertTrue(resposta.startswith("Not opened"), resposta)
        for acao in ("write", "create_file"):
            for nome in ("z.bat", "z.cmd", "z.lnk"):
                with self.subTest(acao=acao, nome=nome):
                    resposta = self.ferramenta("file_controller", {"action": acao, "path": str(self.pasta / nome),
                                                                   "content": "shutdown /r"})
                    self.assertTrue(resposta.startswith("Not done"), resposta)
                    self.assertFalse((self.pasta / nome).exists())
        self.abrir.assert_not_called()
        # um arquivo comum pelo caminho inteiro continua
        self.assertEqual(self.ferramenta("file_controller", {"action": "write", "path": str(self.pasta / "nota.txt"),
                                                             "content": "oi"}), "Written to: nota.txt")
        self.assertEqual(self.ferramenta("file_controller", {"action": "open", "path": str(self.pasta / "nota.txt")}),
                         "Opened file: nota.txt")

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

    def test_copiar_ou_mover_um_programa_para_dentro_de_uma_pasta_nao_vale(self):
        # o destino é a PASTA (a Inicializar do Windows): o nome que conta é o do arquivo que chega lá (x.bat),
        # e não o da pasta. Um x.bat que já estava no PC não vai para a Inicializar, nem copiado nem movido
        (self.pasta / "x.bat").write_text("shutdown /s /t 0", encoding="utf-8")
        destino = self.pasta / "Inicializar"
        destino.mkdir()
        for acao in ("copy", "move"):
            with self.subTest(acao=acao):
                resposta = self.arquivo(acao, name="x.bat", destination=str(destino))
                self.assertTrue(resposta.startswith("Not done"), resposta)
                self.assertFalse((destino / "x.bat").exists())
        self.assertTrue((self.pasta / "x.bat").exists())
        self.assertEqual(list(destino.iterdir()), [])

    def test_o_que_o_pathext_roda_e_o_caminho_no_nome_novo(self):
        # o PATHEXT diz o que mais o Windows roda pelo nome (aqui, um .xyz): nem criar nem abrir
        with patch.dict(os.environ, {"PATHEXT": ".COM;.EXE;.BAT;.XYZ"}):
            self.assertTrue(self.arquivo("write", name="a.xyz", content="shutdown /s").startswith("Not done"))
            self.assertFalse((self.pasta / "a.xyz").exists())
            (self.pasta / "b.xyz").write_text("shutdown /s", encoding="utf-8")
            self.assertTrue(self.arquivo("open", name="b.xyz").startswith("Not opened"))
        # o nome novo com um caminho e a letra da unidade: renomear o levaria para a pasta Inicializar como .bat
        (self.pasta / "nota.txt").write_text("shutdown /s /t 0", encoding="utf-8")
        inicializar = "C:/Users/erton/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup/x.bat"
        for novo in (inicializar, inicializar.replace("/", "\\")):
            with self.subTest(novo=novo):
                self.assertTrue(self.arquivo("rename", name="nota.txt", new_name=novo).startswith("Not done"))
        self.assertTrue((self.pasta / "nota.txt").exists())
        self.abrir.assert_not_called()

    def test_arquivos_comuns_continuam(self):
        self.assertEqual(self.arquivo("write", name="nota.txt", content="oi"), "Written to: nota.txt")
        self.assertEqual(self.arquivo("open", name="nota.txt"), "Opened file: nota.txt")
        (self.pasta / "foto.png").write_bytes(b"png")
        self.assertEqual(self.arquivo("open", name="foto.png"), "Opened file: foto.png")
        self.assertEqual(self.arquivo("open"), f"Opened folder: {self.pasta.name}")
        self.assertIn("nota2.txt", self.arquivo("rename", name="nota.txt", new_name="nota2.txt"))
        self.assertEqual(len(self.abrir.call_args_list), 3)


class ListasEscritasAMaoTests(unittest.TestCase):
    """As listas das travas, escritas à mão aqui: os outros testes conferem só alguns nomes de cada uma, e tirar
    um nome abre uma porta (sem "slidetoshutdown", o open_app rodaria a tela de deslizar para desligar; sem
    ".jar", o file_controller abriria um programa Java). As listas podem crescer; tirar um nome só acontece de
    propósito, mudando este teste junto."""

    def test_programas_de_desligar_do_open_app(self):
        self.assertLessEqual({"shutdown", "logoff", "logout", "tsdiscon", "slidetoshutdown", "psshutdown",
                              "psshutdown64", "rundll32", "poweroff", "reboot", "halt", "gnome-session-quit"},
                             oa._DESLIGAM)

    def test_programas_scripts_e_atalhos_do_file_controller(self):
        self.assertLessEqual({
            ".exe", ".com", ".bat", ".cmd", ".ps1", ".psm1", ".psd1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
            ".msc", ".msi", ".msp", ".scr", ".pif", ".hta", ".cpl", ".lnk", ".url", ".reg", ".inf", ".scf", ".jar",
            ".py", ".pyw", ".pyz", ".pyc", ".appref-ms", ".application", ".settingcontent-ms", ".library-ms",
            ".sh", ".command", ".app", ".desktop", ".appimage", ".run",
        }, fc._PROGRAMAS)
        for extensao in fc._PROGRAMAS:
            with self.subTest(extensao=extensao), patch.dict(os.environ, {"PATHEXT": ""}):
                self.assertTrue(fc._e_programa(f"x{extensao}"))
                self.assertTrue(fc._e_programa(f"X{extensao.upper()}"))

    def test_sinais_do_cmd_do_open_app(self):
        for sinal in '&|<>^%"`\\' + "".join(map(chr, range(32))) + "\x7f":
            with self.subTest(sinal=sinal):
                self.assertTrue(oa._recusa(f"a{sinal}b", "Windows"), sinal)


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
