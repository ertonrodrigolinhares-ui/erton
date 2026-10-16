import importlib.util
import json
import os
import stat
import sys
import tempfile
import textwrap
import threading
import unittest
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
                             "env": sorted(os.environ)}}) + "\\n")
    modo = os.environ.get("FAKE_CLAUDE_MODO", "ok")
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


if __name__ == "__main__":
    unittest.main()
