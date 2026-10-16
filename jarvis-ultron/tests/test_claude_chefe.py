import importlib.util
import json
import os
import stat
import sys
import tempfile
import textwrap
import threading
import time
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from core import claude_chefe as chefe

# Um "claude" de mentira: responde no mesmo formato JSON do Claude Code e anota como foi chamado.
FALSO = textwrap.dedent('''\
    #!{python}
    import json, os, sys
    pedido = sys.stdin.read()
    with open(os.environ["FAKE_CLAUDE_LOG"], "a", encoding="utf-8") as f:
        f.write(json.dumps({{"argv": sys.argv[1:], "pedido": pedido, "cwd": os.getcwd(),
                             "env": sorted(os.environ),
                             "mcp": os.environ.get("ENABLE_CLAUDEAI_MCP_SERVERS")}}) + "\\n")
    modo = os.environ.get("FAKE_CLAUDE_MODO", "ok")
    if modo == "demora":  # abre um "neto" (como o node.exe do claude.cmd) e não termina
        import subprocess, time
        subprocess.Popen([sys.executable, "-c",
                          "import sys, time; time.sleep(1.5); open(sys.argv[1], 'w').write('vivo')",
                          os.environ["FAKE_CLAUDE_NETO"]])
        time.sleep(30)
    def fim(texto, erro=False, subtipo="success", codigo=0):
        print(json.dumps({{"type": "result", "subtype": subtipo, "is_error": erro, "result": texto,
                           "session_id": "sessao-1", "permission_denials": []}}))
        sys.exit(codigo)
    if modo == "login":
        fim("Not logged in · Please run /login", erro=True, codigo=1)
    if modo == "limite":
        fim("You've hit your session limit · resets 3:45pm", erro=True, codigo=1)
    if modo == "turnos":
        fim("", erro=True, subtipo="error_max_turns", codigo=1)
    if modo == "lixo":
        print("isso nao e json"); sys.exit(2)
    if "PLANO APROVADO" in pedido:
        novo = os.environ.get("FAKE_CLAUDE_CODIGO")
        if novo is not None:
            open("modulo.py", "w", encoding="utf-8").write(novo)
        if os.environ.get("FAKE_CLAUDE_CRIA"):
            open("novo_arquivo.py", "w", encoding="utf-8").write("X = 1\\n")
        fim("FALA: Mudei o modulo.")
    fim("FALA: Achei três mudanças importantes.\\n\\n# Relatório\\n" + "Detalhe. " * 60)
''')


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.casa = self.tmp / "casa"
        bin_ = self.casa / ".local" / "bin"
        bin_.mkdir(parents=True)
        self.exe = bin_ / "claude"
        self.exe.write_text(FALSO.format(python=sys.executable), encoding="utf-8")
        self.exe.chmod(self.exe.stat().st_mode | stat.S_IEXEC)
        self.log = self.tmp / "chamadas.jsonl"
        self.jarvis_dir = self.tmp / "jarvis"
        (self.jarvis_dir / "tests").mkdir(parents=True)
        (self.jarvis_dir / "modulo.py").write_text("def soma(a, b):\n    return a + b\n", encoding="utf-8")
        (self.jarvis_dir / ".env").write_text("GEMINI_API_KEY=segredo\n", encoding="utf-8")
        self.patches = [
            patch.dict(os.environ, {"FAKE_CLAUDE_LOG": str(self.log), "JARVIS_CLAUDE_EXE": str(self.exe),
                                    "ANTHROPIC_API_KEY": "sk-ant-nao-usar", "GEMINI_API_KEY": "chave-do-jarvis",
                                    "JARVIS_CEREBRO": ""}),
            patch.object(chefe, "pasta_dados", lambda: self.casa / "Documents" / "Jarvis Ultron"),
            patch.object(chefe, "pasta_jarvis", lambda: self.jarvis_dir),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    def chamadas(self):
        if not self.log.exists():
            return []
        return [json.loads(l) for l in self.log.read_text(encoding="utf-8").splitlines() if l.strip()]


class RodarClaudeTests(Base):
    def test_tarefa_usa_a_assinatura_e_as_travas(self):
        resposta = chefe.fazer_tarefa("pesquise a reforma tributária para holdings")
        self.assertTrue(resposta.ok, resposta.erro)
        self.assertEqual(resposta.fala, "Achei três mudanças importantes.")
        chamada = self.chamadas()[0]
        argv = chamada["argv"]
        # o pedido vai pela entrada padrão, com as regras
        self.assertIn("pesquise a reforma tributária", chamada["pedido"])
        self.assertIn("Nunca publique", chamada["pedido"])
        self.assertNotIn("pesquise", " ".join(argv))
        # sem chave da API (senão cobra fora da assinatura) e sem as chaves do Jarvis
        self.assertNotIn("ANTHROPIC_API_KEY", chamada["env"])
        self.assertNotIn("GEMINI_API_KEY", chamada["env"])
        # trabalha na pasta dele, sem perguntar, e sem comandos nem conectores
        self.assertEqual(Path(chamada["cwd"]).resolve(), chefe.pasta_trabalho().resolve())
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "dontAsk")
        proibidas = argv[argv.index("--disallowedTools") + 1:]
        for nome in ("Bash", "PowerShell", "mcp__*"):
            self.assertIn(nome, proibidas)
        self.assertTrue(any(r.startswith("Read(") and r.endswith("/.env)") for r in proibidas))
        permitidas = argv[argv.index("--allowedTools") + 1:argv.index("--disallowedTools")]
        self.assertIn(f"Edit({chefe.regra_de_pasta(chefe.pasta_trabalho())}/**)", permitidas)
        self.assertFalse(any(p in ("Bash", "Edit") for p in permitidas))
        # lê (sem escrever) a pasta de dados do Jarvis
        self.assertEqual(Path(argv[argv.index("--add-dir") + 1]).resolve(), chefe.pasta_dados().resolve())

    def test_plano_nao_pode_editar(self):
        chefe.planejar("mude a cor do anel")
        argv = self.chamadas()[0]["argv"]
        permitidas = argv[argv.index("--allowedTools") + 1:argv.index("--disallowedTools")]
        self.assertFalse(any(p.startswith("Edit") for p in permitidas))
        self.assertEqual(Path(self.chamadas()[0]["cwd"]).resolve(), self.jarvis_dir.resolve())

    def test_continuar_usa_a_sessao(self):
        chefe.fazer_tarefa("e sobre ITCMD?", sessao="sessao-1")
        argv = self.chamadas()[0]["argv"]
        self.assertEqual(argv[argv.index("--resume") + 1], "sessao-1")

    def test_erros_viram_avisos_em_portugues(self):
        casos = {"login": "Instalar Claude", "limite": "limite do seu plano", "turnos": "partes menores",
                 "lixo": "isso nao e json"}
        for modo, esperado in casos.items():
            with patch.dict(os.environ, {"FAKE_CLAUDE_MODO": modo}):
                resposta = chefe.fazer_tarefa("oi")
            self.assertFalse(resposta.ok, modo)
            self.assertIn(esperado, resposta.erro, modo)
        with patch.dict(os.environ, {"FAKE_CLAUDE_MODO": "limite"}):
            self.assertIn("3:45pm", chefe.fazer_tarefa("oi").erro)

    def test_sem_claude_instalado(self):
        with patch.dict(os.environ, {"JARVIS_CLAUDE_EXE": ""}), patch.object(chefe.Path, "home", lambda: self.tmp), \
                patch.object(chefe.shutil, "which", return_value=None):
            resposta = chefe.fazer_tarefa("oi")
        self.assertIn("Instalar Claude", resposta.erro)

    def test_ignora_o_claude_desktop_da_loja(self):
        with patch.dict(os.environ, {"JARVIS_CLAUDE_EXE": ""}), patch.object(chefe.Path, "home", lambda: self.tmp), \
                patch.object(chefe.shutil, "which", return_value=r"C:\Users\E\AppData\Local\Microsoft\WindowsApps\Claude.exe"):
            self.assertIsNone(chefe.achar_claude())

    def test_regra_de_pasta_do_windows(self):
        with patch.object(chefe.Path, "resolve", lambda self: self), \
                patch.object(chefe.Path, "as_posix", lambda self: "C:/Users/Erton/Documents/Jarvis Ultron/Claude"):
            self.assertEqual(chefe.regra_de_pasta("x"), "//c/Users/Erton/Documents/Jarvis Ultron/Claude")

    def test_separar_fala(self):
        self.assertEqual(chefe.separar_fala("**FALA:** Pronto.\n\n# Detalhes\nabc"), ("Pronto.", "# Detalhes\nabc"))
        fala, resto = chefe.separar_fala("# Título\nPrimeira frase. Segunda frase. Terceira.")
        self.assertEqual(fala, "Título Primeira frase. Segunda frase.")


class MudarCodigoTests(Base):
    def _aplicar(self, codigo=None, falhas=(set(), set()), cria=False):
        env = {}
        if codigo is not None:
            env["FAKE_CLAUDE_CODIGO"] = codigo
        if cria:
            env["FAKE_CLAUDE_CRIA"] = "1"
        resultados = list(falhas)
        with patch.dict(os.environ, env), patch.object(chefe, "rodar_testes", side_effect=lambda pasta: resultados.pop(0)):
            return chefe.aplicar_plano("trocar soma por subtração", "sessao-1", "mude a soma")

    def test_mudanca_boa_fica_e_tem_backup(self):
        r = self._aplicar("def soma(a, b):\n    return a - b\n")
        self.assertTrue(r.ok, r.fala)
        self.assertIn("a - b", (self.jarvis_dir / "modulo.py").read_text(encoding="utf-8"))
        self.assertIn("1 arquivo", r.fala)
        backups = list(chefe.pasta_backups().glob("*.zip"))
        self.assertEqual(len(backups), 1)
        import zipfile
        with zipfile.ZipFile(backups[0]) as z:
            self.assertIn("a + b", z.read("modulo.py").decode())
            self.assertNotIn(".env", z.namelist())  # a chave nunca vai para o backup
        argv = self.chamadas()[0]["argv"]
        self.assertEqual(argv[argv.index("--resume") + 1], "sessao-1")

    def test_erro_de_sintaxe_desfaz(self):
        r = self._aplicar("def soma(a, b)\n    return a - b\n", falhas=(set(),))
        self.assertFalse(r.ok)
        self.assertIn("Desfiz", r.fala)
        self.assertIn("a + b", (self.jarvis_dir / "modulo.py").read_text(encoding="utf-8"))

    def test_teste_que_passava_e_quebrou_desfaz_e_apaga_o_criado(self):
        r = self._aplicar("def soma(a, b):\n    return 0\n", falhas=({"tests/x.py::velho"}, {"tests/x.py::velho", "tests/x.py::soma"}),
                          cria=True)
        self.assertFalse(r.ok)
        self.assertIn("tests/x.py::soma", r.fala)
        self.assertIn("a + b", (self.jarvis_dir / "modulo.py").read_text(encoding="utf-8"))
        self.assertFalse((self.jarvis_dir / "novo_arquivo.py").exists())
        self.assertEqual(chefe.mudancas(chefe.fotografar(self.jarvis_dir), chefe.fotografar(self.jarvis_dir)), [])

    def test_falha_antiga_nao_impede(self):
        r = self._aplicar("def soma(a, b):\n    return b + a\n", falhas=({"tests/x.py::velho"}, {"tests/x.py::velho"}))
        self.assertTrue(r.ok, r.fala)

    def test_claude_sem_mudar_nada(self):
        r = self._aplicar(None, falhas=(set(),))
        self.assertFalse(r.ok)
        self.assertIn("sem mudar", r.fala)


class RodarTestesDeVerdadeTests(unittest.TestCase):
    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp())
        (self.pasta / "tests").mkdir()
        (self.pasta / "tests" / "__init__.py").write_text("", encoding="utf-8")
        (self.pasta / "tests" / "test_a.py").write_text(textwrap.dedent('''\
            import unittest
            class A(unittest.TestCase):
                def test_bom(self):
                    self.assertTrue(True)
                def test_ruim(self):
                    self.assertTrue(False)
            '''), encoding="utf-8")

    def test_com_pytest(self):
        if importlib.util.find_spec("pytest") is None:
            self.skipTest("pytest não instalado")
        self.assertEqual(chefe.rodar_testes(self.pasta), {"tests/test_a.py::A::test_ruim"})

    def test_com_unittest(self):
        with patch.object(chefe.importlib.util, "find_spec", return_value=None):
            falhas = chefe.rodar_testes(self.pasta)
        self.assertEqual(len(falhas), 1)
        self.assertIn("test_ruim", next(iter(falhas)))


def _plugin():
    spec = importlib.util.spec_from_file_location("auto_claude", RAIZ / "automacoes" / "claude_tarefas.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class JarvisFalso:
    def __init__(self, fala=""):
        self._current_input_transcript = self._last_input_transcript = fala
        self.avisos, self.logs = [], []
        self.ui = NS(write_log=self.logs.append)

    def anunciar(self, texto, titulo="Lembrete"):
        self.avisos.append(texto)


def _esperar():
    for t in threading.enumerate():
        if t.name.startswith("Claude"):
            t.join(10)


class FerramentaClaudeTests(Base):
    def setUp(self):
        super().setUp()
        self.m = _plugin()
        self.abrir = patch.object(self.m, "_abrir")
        self.abrir.start()

    def tearDown(self):
        self.abrir.stop()
        super().tearDown()

    def test_tarefa_em_segundo_plano_salva_relatorio_e_avisa(self):
        jarvis = JarvisFalso()
        r = self.m.executar({"request": "pesquise holdings"}, jarvis)
        self.assertIn("background", r)
        _esperar()
        self.assertIn("Achei três mudanças importantes.", jarvis.avisos[0])
        relatorios = list((chefe.pasta_trabalho() / "Relatorios").glob("*.md"))
        self.assertEqual(len(relatorios), 1)
        # continuar a conversa usa a mesma sessão
        self.m.executar({"request": "e o ITCMD?", "continue_last": True}, jarvis)
        _esperar()
        argv = self.chamadas()[1]["argv"]
        self.assertEqual(argv[argv.index("--resume") + 1], "sessao-1")

    def test_modo_privado_nao_manda_nada(self):
        with patch.dict(os.environ, {"JARVIS_CEREBRO": "gemma"}):
            r = self.m.executar({"request": "analise os clientes"}, JarvisFalso())
        self.assertIn("Private mode", r)
        self.assertEqual(self.chamadas(), [])

    def test_codigo_plano_ok_e_aplica(self):
        jarvis = JarvisFalso("Jarvis, pede pro Claude mudar a soma, pode fazer")
        with patch.dict(os.environ, {"FAKE_CLAUDE_CODIGO": "def soma(a, b):\n    return a - b\n"}), \
                patch.object(chefe, "rodar_testes", return_value=set()):
            self.m.executar({"request": "mude a soma", "kind": "codigo"}, jarvis)
            _esperar()
            self.assertIn("plano do Claude está pronto", jarvis.avisos[0])
            self.assertIn("a + b", (self.jarvis_dir / "modulo.py").read_text(encoding="utf-8"))
            # o "pode fazer" dito junto com o pedido não vale
            r = self.m.executar({"request": "mude a soma", "kind": "codigo", "confirm": True}, jarvis)
            self.assertIn("Not confirmed", r)
            # resposta sem ok claro não vale
            jarvis._current_input_transcript = "hmm, e se der errado?"
            r = self.m.executar({"request": "mude a soma", "kind": "codigo", "confirm": True}, jarvis)
            self.assertIn("Not confirmed", r)
            # agora sim
            jarvis._current_input_transcript = "ok, pode fazer"
            r = self.m.executar({"request": "mude a soma", "kind": "codigo", "confirm": True}, jarvis)
            self.assertIn("Approved", r)
            _esperar()
        self.assertIn("a - b", (self.jarvis_dir / "modulo.py").read_text(encoding="utf-8"))
        self.assertIn("Pronto", jarvis.avisos[-1])
        # o mesmo ok não aplica de novo
        r = self.m.executar({"request": "mude a soma", "kind": "codigo", "confirm": True}, jarvis)
        self.assertIn("Not confirmed", r)

    def test_confirmar_sem_plano_nao_faz_nada(self):
        r = self.m.executar({"request": "mude", "kind": "codigo", "confirm": True}, JarvisFalso("ok, pode fazer"))
        self.assertIn("Not confirmed", r)
        self.assertEqual(self.chamadas(), [])

    def test_uma_tarefa_por_vez(self):
        self.assertTrue(self.m._ocupado.acquire(blocking=False))
        try:
            r = self.m.executar({"request": "pesquise"}, JarvisFalso())
        finally:
            self.m._ocupado.release()
        self.assertIn("still working", r)

    def test_carrega_como_ferramenta(self):
        from core.automacoes import carregar_ferramentas

        self.assertIn("claude_task", carregar_ferramentas(RAIZ / "automacoes").ferramentas)


def _permitidas_e_proibidas(argv):
    i, j = argv.index("--allowedTools"), argv.index("--disallowedTools")
    return argv[i + 1:j], argv[j + 1:]


class TravasDeLeituraEConectoresTests(Base):
    """Sem leitura solta (as senhas do Hermes ficam em %LOCALAPPDATA%) e sem conectores."""

    def test_nenhum_modo_le_fora_das_pastas_dele(self):
        local = self.tmp / "AppData" / "Local"
        perfil = local / "hermes" / "profiles" / "jarvis"
        with patch.dict(os.environ, {"LOCALAPPDATA": str(local), "HERMES_JARVIS_HOME": str(perfil)}):
            chefe.fazer_tarefa("pesquise")
            chefe.planejar("mude a cor")
            with patch.object(chefe, "rodar_testes", return_value=set()):
                chefe.aplicar_plano("plano", None, "mude")
        chamadas = self.chamadas()
        self.assertEqual(len(chamadas), 3)
        for chamada in chamadas:
            argv = chamada["argv"]
            permitidas, proibidas = _permitidas_e_proibidas(argv)
            for solta in ("Read", "Glob", "Grep"):
                self.assertNotIn(solta, permitidas)
            leituras = [p for p in permitidas if p.startswith("Read(")]
            self.assertTrue(leituras and all(p.endswith("/**)") for p in leituras), leituras)
            self.assertIn("Read(~/AppData/**)", proibidas)
            self.assertIn(f"Read({chefe.regra_de_pasta(local / 'hermes')}/**)", proibidas)
            self.assertIn(f"Read({chefe.regra_de_pasta(perfil)}/**)", proibidas)
            self.assertIn(f"Edit({chefe.regra_de_pasta(self.jarvis_dir)}/.mcp.json)", proibidas)
            # conectores: o Claude abre sem nenhum servidor MCP ("mcp__*" sozinho não bloqueava nada)
            self.assertIn("--strict-mcp-config", argv)
            self.assertEqual(chamada["mcp"], "false")
        tarefa, plano, _aplicar = (_permitidas_e_proibidas(c["argv"])[0] for c in chamadas)
        self.assertIn(f"Read({chefe.regra_de_pasta(chefe.pasta_dados())}/**)", tarefa)
        self.assertEqual([p for p in plano if p.startswith("Read(")],
                         [f"Read({chefe.regra_de_pasta(self.jarvis_dir)}/**)"])


class ForaDaFotoTests(Base):
    """O Claude não muda o que o backup não cobre, e o que já existia nunca é apagado."""

    def test_claude_nao_muda_o_que_o_backup_nao_cobre(self):
        with patch.object(chefe, "rodar_testes", return_value=set()):
            chefe.aplicar_plano("plano", None, "mude")
        _permitidas, proibidas = _permitidas_e_proibidas(self.chamadas()[0]["argv"])
        raiz = chefe.regra_de_pasta(self.jarvis_dir)
        for regra in (f"Edit({raiz}/**/.*/**)", f"Edit({raiz}/**/venv/**)", f"Edit({raiz}/**/tmp/**)",
                      f"Edit({raiz}/**/*.zip)", f"Edit({raiz}/**/*.log)", f"Edit({raiz}/core/claude_chefe.py)"):
            self.assertIn(regra, proibidas)

    def test_arquivo_grande_que_encolheu_nao_e_apagado(self):
        grande = self.jarvis_dir / "dados" / "grande.bin"
        grande.parent.mkdir()
        grande.write_bytes(b"x" * (chefe.LIMITE_BACKUP + 10))
        antes = chefe.fotografar(self.jarvis_dir)
        self.assertIn("dados/grande.bin", antes)
        backup = chefe.fazer_backup(self.jarvis_dir, antes)
        grande.write_bytes(b"pequeno")
        (self.jarvis_dir / "novo.py").write_text("X = 1\n", encoding="utf-8")
        self.assertIn("dados/grande.bin", chefe.mudancas(antes, chefe.fotografar(self.jarvis_dir)))
        chefe.restaurar(self.jarvis_dir, backup, antes)
        self.assertTrue(grande.exists())  # já existia: nunca é apagado
        self.assertFalse((self.jarvis_dir / "novo.py").exists())


class DesfazerSoOQueEDoClaudeTests(Base):
    def test_o_que_mudou_depois_do_claude_fica_como_esta(self):
        do_erton = self.jarvis_dir / "automacoes" / "minha_nova.py"
        criado = self.jarvis_dir / "novo_arquivo.py"
        rodadas = []

        def testes(pasta):
            rodadas.append(pasta)
            if len(rodadas) == 2:  # enquanto os testes de depois rodam, o Erton salva coisas dele
                do_erton.parent.mkdir(exist_ok=True)
                do_erton.write_text("# do Erton\n", encoding="utf-8")
                criado.write_text("X = 2  # o Erton mexeu depois do Claude\n", encoding="utf-8")
                return {"tests/x.py::soma"}
            return set()

        with patch.dict(os.environ, {"FAKE_CLAUDE_CODIGO": "def soma(a, b):\n    return 0\n",
                                     "FAKE_CLAUDE_CRIA": "1"}), \
                patch.object(chefe, "rodar_testes", side_effect=testes):
            r = chefe.aplicar_plano("trocar", None, "mude a soma")
        self.assertFalse(r.ok)
        self.assertIn("a + b", (self.jarvis_dir / "modulo.py").read_text(encoding="utf-8"))
        self.assertEqual(do_erton.read_text(encoding="utf-8"), "# do Erton\n")
        self.assertIn("o Erton mexeu", criado.read_text(encoding="utf-8"))
        self.assertIn("novo_arquivo.py", r.fala)
        copias = list(chefe.pasta_backups().glob("jarvis-desfeito-*.zip"))
        self.assertEqual(len(copias), 1)  # a versão desfeita fica guardada: nada se perde
        with zipfile.ZipFile(copias[0]) as z:
            self.assertIn("return 0", z.read("modulo.py").decode())


class MudancaInterrompidaTests(Base):
    """O Jarvis fechou, o cérebro foi religado ou caiu no meio de uma mudança do Claude no código."""

    class Morreu(BaseException):
        """Como o os._exit/kill: o fio some sem rodar mais nada."""

    def _quebrar_e_morrer(self, *args, **kwargs):
        self.durante = (chefe.aplicando(), chefe._anotacao().is_file())
        (self.jarvis_dir / "modulo.py").write_text("def soma(a, b)\n    return a -\n", encoding="utf-8")
        (self.jarvis_dir / "pela_metade.py").write_text("X = (\n", encoding="utf-8")
        raise self.Morreu()

    def _interromper(self):
        with patch.object(chefe, "rodar", side_effect=self._quebrar_e_morrer), \
                patch.object(chefe, "rodar_testes", return_value=set()):
            with self.assertRaises(self.Morreu):
                chefe.aplicar_plano("plano", None, "mude a soma")

    def _voltou(self):
        self.assertIn("a + b", (self.jarvis_dir / "modulo.py").read_text(encoding="utf-8"))
        self.assertFalse((self.jarvis_dir / "pela_metade.py").exists())

    def test_desfaz_na_proxima_abertura_e_avisa_uma_vez(self):
        self._interromper()
        self.assertEqual(self.durante, (True, True))
        self.assertTrue(chefe._anotacao().is_file())
        aviso = chefe.desfazer_interrompida()
        self.assertIn("desfiz", aviso)
        self._voltou()
        with zipfile.ZipFile(next(chefe.pasta_backups().glob("jarvis-desfeito-*.zip"))) as z:
            self.assertIn("pela_metade.py", z.namelist())  # a versão pela metade fica guardada
        registro = next((chefe.pasta_trabalho() / "Mudancas").glob("*.md")).read_text(encoding="utf-8")
        self.assertIn("DESFEITO", registro)
        self.assertEqual(chefe.desfazer_interrompida(), aviso)  # vale até ser contado ao Erton
        chefe.esquecer_interrompida()
        self.assertEqual(chefe.desfazer_interrompida(), "")
        self.assertFalse(chefe._anotacao().exists())

    def test_iniciar_jarvis_desfaz_antes_de_abrir(self):
        import io

        self._interromper()
        with patch("sys.stdout", new_callable=io.StringIO) as saida:
            chefe._principal(["--desfazer-interrompida"])
        self.assertIn("desfiz", saida.getvalue())
        self._voltou()
        bat = (RAIZ / "Iniciar Jarvis Ultron.bat").read_text(encoding="utf-8")
        self.assertLess(bat.index("-m core.claude_chefe --desfazer-interrompida"), bat.index('python.exe" main.py'))

    def test_cerebro_novo_desfaz_antes_de_importar_o_main(self):
        import inspect

        from core import processo_cerebro

        self._interromper()
        processo_cerebro.desfazer_mudanca_interrompida()
        self._voltou()
        fonte = inspect.getsource(processo_cerebro.principal)
        self.assertLess(fonte.index("desfazer_mudanca_interrompida()"), fonte.index("import main"))

    def test_cerebro_conta_ao_erton(self):
        import main

        self._interromper()
        avisos = []
        jarvis = NS(anunciar=lambda texto, titulo="": avisos.append((titulo, texto)))
        main._contar_mudanca_desfeita(jarvis, espera=0)
        for t in threading.enumerate():
            if t.name == "ClaudeDesfeita":
                t.join(5)
        self._voltou()
        self.assertEqual(avisos[0][0], "Claude")
        self.assertIn("desfiz", avisos[0][1])
        self.assertFalse(chefe._anotacao().exists())

    def test_erro_inesperado_no_meio_desfaz_na_hora(self):
        def quebrar(*args, **kwargs):
            (self.jarvis_dir / "modulo.py").write_text("quebrado\n", encoding="utf-8")
            raise RuntimeError("falhou")

        with patch.object(chefe, "rodar", side_effect=quebrar), patch.object(chefe, "rodar_testes", return_value=set()):
            with self.assertRaises(RuntimeError):
                chefe.aplicar_plano("plano", None, "mude")
        self.assertIn("a + b", (self.jarvis_dir / "modulo.py").read_text(encoding="utf-8"))
        self.assertFalse(chefe._anotacao().exists())
        self.assertFalse(chefe.aplicando())

    def test_mudanca_que_terminou_nao_e_desfeita_depois(self):
        with patch.dict(os.environ, {"FAKE_CLAUDE_CODIGO": "def soma(a, b):\n    return a - b\n"}), \
                patch.object(chefe, "rodar_testes", return_value=set()):
            self.assertTrue(chefe.aplicar_plano("plano", None, "mude").ok)
        self.assertFalse(chefe._anotacao().exists())
        self.assertEqual(chefe.desfazer_interrompida(), "")
        self.assertIn("a - b", (self.jarvis_dir / "modulo.py").read_text(encoding="utf-8"))
        self.assertFalse(chefe.aplicando())


class TrocaDeModoComOClaudeMudandoTests(unittest.TestCase):
    def test_nao_religa_o_cerebro_no_meio_da_mudanca(self):
        import main

        class UI:
            remota = True

            def __init__(s):
                s.logs, s.trocas, s.muted = [], [], False

            def write_log(s, t):
                s.logs.append(t)

        ui = UI()
        ui.trocar_cerebro = ui.trocas.append
        jarvis = object.__new__(main.JarvisLive)
        jarvis.ui, jarvis._cerebro_nome, jarvis.avisos = ui, "gemini", []
        jarvis._falar_aviso = jarvis.avisos.append
        with patch("core.cerebro_gemma.modelo_instalado", return_value=True):
            with chefe._aplicando:
                jarvis._trocar_cerebro("gemma")
            self.assertEqual(ui.trocas, [])
            self.assertIn("Claude", jarvis.avisos[0])
            jarvis._trocar_cerebro("gemma")  # terminou: agora troca
        self.assertEqual(ui.trocas, ["gemma"])


class AutoconsertoDuranteAMudancaTests(unittest.TestCase):
    def test_nao_renomeia_automacao_enquanto_o_claude_muda_o_codigo(self):
        spec = importlib.util.spec_from_file_location("auto_conserto", RAIZ / "automacoes" / "autoconserto.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        pasta = Path(tempfile.mkdtemp())
        (pasta / "foo.py").write_text("def x(:\n", encoding="utf-8")
        with patch("core.automacoes.carregar_ferramentas", return_value=NS(erros=[("foo.py", "invalid syntax")])), \
                patch("core.automacoes.pasta_padrao", return_value=pasta):
            with chefe._aplicando:
                self.assertEqual(m._desligar_automacao_com_defeito(), "")
            self.assertTrue((pasta / "foo.py").exists())
            self.assertIn("foo.py", m._desligar_automacao_com_defeito())
        self.assertTrue((pasta / "_foo.py").exists())


class TempoEsgotadoTests(Base):
    def test_encerra_tambem_o_que_o_claude_abriu(self):
        neto = self.tmp / "neto.txt"
        inicio = time.monotonic()
        with patch.dict(os.environ, {"FAKE_CLAUDE_MODO": "demora", "FAKE_CLAUDE_NETO": str(neto)}):
            r = chefe.rodar("oi", list(chefe.LEITURA), chefe.preparar_pasta(), tempo=0.5)
        self.assertLess(time.monotonic() - inicio, 10)
        self.assertIn("parei a tarefa", r.erro)
        time.sleep(2.5)
        self.assertFalse(neto.exists())  # o "neto" morreu junto: não seguiu trabalhando

    def test_estrutura_do_job_do_windows(self):
        import ctypes

        if ctypes.sizeof(ctypes.c_void_p) != 8:
            self.skipTest("conta feita para 64 bits")
        self.assertEqual(ctypes.sizeof(chefe._estruturas_do_job()), 144)  # JOBOBJECT_EXTENDED_LIMIT_INFORMATION


class TestesSemMexerNoErtonTests(unittest.TestCase):
    def test_testes_rodam_numa_copia_sem_os_arquivos_do_erton(self):
        if importlib.util.find_spec("pytest") is None:
            self.skipTest("pytest não instalado")
        pasta, casa = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        (pasta / "tests").mkdir()
        (pasta / "tests" / "__init__.py").write_text("", encoding="utf-8")
        (pasta / ".env").write_text("GEMINI_API_KEY=segredo\n", encoding="utf-8")
        (pasta / "memory").mkdir()
        (pasta / "memory" / "__init__.py").write_text("", encoding="utf-8")
        (pasta / "memory" / "historico.py").write_text("ITENS = []\n", encoding="utf-8")
        (pasta / "memory" / "task_history.json").write_text("[1]", encoding="utf-8")
        (pasta / "tests" / "test_b.py").write_text(textwrap.dedent('''\
            import unittest
            from pathlib import Path
            RAIZ = Path(__file__).resolve().parents[1]
            class B(unittest.TestCase):
                def test_escreve(self):
                    from memory import historico  # o código da pasta memory vai junto
                    (Path.home() / "tema.json").write_text("vermelho")
                    (RAIZ / "memory" / "task_history.json").write_text("[1, 2]")
                    self.assertFalse((RAIZ / ".env").exists())
                def test_ruim(self):
                    self.assertTrue(False)
            '''), encoding="utf-8")
        with patch.dict(os.environ, {"HOME": str(casa), "USERPROFILE": str(casa)}):
            falhas = chefe.rodar_testes(pasta)
        self.assertEqual(falhas, {"tests/test_b.py::B::test_ruim"})
        self.assertFalse((casa / "tema.json").exists())
        self.assertEqual((pasta / "memory" / "task_history.json").read_text(encoding="utf-8"), "[1]")


class InstaladorDoClaudeTests(unittest.TestCase):
    SCRIPT = RAIZ / "claude" / "instalar_claude.ps1"

    def test_so_ascii(self):
        self.SCRIPT.read_bytes().decode("ascii")  # o PowerShell 5.1 lê sem BOM como ANSI

    def test_tira_a_chave_antes_de_conferir_o_login(self):
        texto = self.SCRIPT.read_text(encoding="ascii")
        login = texto.index("(Logado $exe)")
        self.assertLess(texto.index("$env:ANTHROPIC_API_KEY = $null"), login)
        self.assertLess(texto.index("$env:ANTHROPIC_AUTH_TOKEN = $null"), login)

    def test_caminho_gravado_no_env_volta_igual(self):
        from dotenv import dotenv_values
        import io

        texto = self.SCRIPT.read_text(encoding="ascii")
        corpo = texto[texto.index("function Definir-Env"):texto.index("function Atualizar-Path")]
        self.assertIn(".Replace('\\', '\\\\').Replace('\"', '\\\"')", corpo)
        caminho = r"C:\Users\Erton\.local\bin\claude.exe"  # "\b" sem escape vira outra letra
        gravado = 'JARVIS_CLAUDE_EXE="' + caminho.replace("\\", "\\\\").replace('"', '\\"') + '"\n'
        self.assertEqual(dotenv_values(stream=io.StringIO(gravado))["JARVIS_CLAUDE_EXE"], caminho)
        exemplo = next(linha for linha in (RAIZ / ".env.example").read_text(encoding="utf-8").splitlines()
                       if "JARVIS_CLAUDE_EXE=" in linha)
        lido = dotenv_values(stream=io.StringIO(exemplo.lstrip("# ")))["JARVIS_CLAUDE_EXE"]
        self.assertEqual(lido, r"C:\Users\voce\.local\bin\claude.exe")

    def test_caminho_ja_estragado_no_env_ainda_e_achado(self):
        pasta = Path(tempfile.mkdtemp()) / "local\\bin"  # no Linux a barra invertida vale como letra
        pasta.mkdir()
        (pasta / "claude").write_text("", encoding="utf-8")
        estragado = str(pasta / "claude").replace("\\b", "\b")  # como o .env antigo era lido
        with patch.dict(os.environ, {"JARVIS_CLAUDE_EXE": f'"{estragado}"'}):
            self.assertEqual(chefe.achar_claude(), str(pasta / "claude"))

    def test_definir_env_de_verdade(self):
        import shutil
        import subprocess

        from dotenv import dotenv_values

        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if not powershell:
            self.skipTest("sem PowerShell neste PC")
        texto = self.SCRIPT.read_text(encoding="ascii")
        funcao = texto[texto.index("function Definir-Env"):texto.index("function Atualizar-Path")]
        pasta = Path(tempfile.mkdtemp())
        roteiro = pasta / "t.ps1"
        roteiro.write_text(f"$envArq = '{pasta / '.env'}'\n$utf8 = New-Object System.Text.UTF8Encoding $false\n"
                           f"{funcao}\nDefinir-Env 'JARVIS_CLAUDE_EXE' 'C:\\Users\\Erton\\.local\\bin\\claude.exe'\n",
                           encoding="ascii")
        subprocess.run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(roteiro)],
                       capture_output=True, timeout=120, check=True)
        self.assertEqual(dotenv_values(pasta / ".env")["JARVIS_CLAUDE_EXE"], r"C:\Users\Erton\.local\bin\claude.exe")


if __name__ == "__main__":
    unittest.main()
