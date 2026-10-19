"""Regras do Jarvis que nunca podem quebrar (Etapa 1 do docs/PLANO-REORGANIZACAO.md).

Diferente das fotos (tests/test_contratos.py), estas regras não mudam nem de propósito: se uma etapa
fizer uma delas falhar, a etapa está errada. O mapa de onde fica cada trava e qual teste a protege
está no core/SEGURANCA.md.

  - modo privado: cada ferramenta que usa IA na nuvem é recusada ANTES de chegar à ação (também as
    regras por argumento e as automações com USA_IA_NUVEM); a reserva não oferece nenhuma delas;
  - a lista de nuvem (FERRAMENTAS_NUVEM_IA) só cresce enquanto a ferramenta existir;
  - a ORDEM das travas no começo do _execute_tool: servidor (cloud_safe) → modo privado → Jarvis pronto
    → modo QA → desligar o Jarvis → save_memory (que não grava no modo privado);
  - um "ok" antigo não aprova publicação nem vídeo;
  - a chave do Gemini nunca vai para o config/api_keys.json (nem aparece no registro da tela);
  - num lote do Gemini, o que muda algo roda em fila e na ordem.

Também guarda as conferências de segurança que ficavam em testes ligados ao servidor (o
test_phase1_decoupling, a reserva do test_cerebro_gemma e o lote do test_qa_system), para não se
perderem quando o servidor for guardado (Etapa 11). As do servidor saem junto com os ramos cloud_safe
(Etapa 14)."""

import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

from core.aprovacao import nova_fala  # noqa: E402
from test_contratos import FOTO_POLITICAS, UIFalsa, acoes_do_main, em_fila, ler_foto  # noqa: E402

# As ferramentas que só agem no PC (cópia da LOCAL_MACHINE_ONLY_ACTIONS de hoje, que a Etapa 5 apaga do
# main.py): o modo servidor nunca pode oferecê-las.
AGEM_NO_PC = frozenset({"computer_control", "open_app", "file_controller", "media_control",
                        "desktop_control", "computer_settings"})


def _jarvis(ui=None):
    """Uma JarvisLive sem abrir nada (sem microfone, sem Gemini, sem fios)."""
    import main

    jarvis = object.__new__(main.JarvisLive)
    jarvis.ui = jarvis.client = ui or UIFalsa()
    jarvis.cloud_safe = False
    jarvis.speak_error = Mock()
    jarvis._current_input_transcript = ""
    jarvis._last_input_transcript = ""
    jarvis._last_input_transcript_at = 0.0
    return jarvis


def _chamar(jarvis, nome, args=None):
    return asyncio.run(jarvis._execute_tool(NS(id="1", name=nome, args=dict(args or {})))).response


def _existentes() -> set[str]:
    """Ferramentas que o Jarvis ainda conhece: declaradas ao Gemini, automações da pasta ou citadas
    nas listas de política (uma ferramenta desligada de propósito continua nas listas)."""
    import main

    return ({d["name"] for d in main.TOOL_DECLARATIONS} | set(main.carregar_automacoes().ferramentas)
            | set(main.FERRAMENTAS_NUVEM_IA) | set(main.CLOUD_SAFE_ACTIONS)
            | set(main.JarvisLive.RESERVA_FERRAMENTAS_ESSENCIAIS))


def _esperar_fio(nome: str) -> None:
    for fio in threading.enumerate():
        if fio.name == nome:
            fio.join(5)


class JarvisFalso:
    """Imita o JarvisLive nas aprovações: conta as falas do Erton (o "ok" só vale numa fala nova)."""

    def __init__(self, fala=""):
        self._fala_n, self._fala_texto = 0, ""
        self.avisos, self.logs = [], []
        self.ui = NS(write_log=self.logs.append)
        if fala:
            self.falar(fala)

    def falar(self, texto):
        nova_fala(self, texto)

    def _falar_aviso(self, texto):
        self.avisos.append(texto)


# ======================================================================= modo privado

class ModoPrivadoTests(unittest.TestCase):
    def _sem_chegar_a_nada(self, pilha, jarvis):
        """Troca tudo o que vem depois da trava do modo privado por falsas que falham se chamadas."""
        import main

        nada = AssertionError("passou da trava do modo privado")
        falsas = [pilha.enter_context(patch.object(main, acao, Mock(side_effect=nada))) for acao in acoes_do_main()]
        for alvo in ("core.hermes_ponte.perguntar", "core.hermes_ponte.aprovar_e_executar",
                     "core.modelos.gerar_imagem", "agent.task_queue.get_queue", "core.qa_mode.guard_tool_call"):
            falsas.append(pilha.enter_context(patch(alvo, Mock(side_effect=nada))))
        for automacao in main.carregar_automacoes().ferramentas.values():
            falsas.append(pilha.enter_context(patch.object(automacao, "executar", Mock(side_effect=nada))))
        for metodo in ("_intercept_ui_tool_call", "_hermes_sem_travar", "_geekie_pendencias", "_autodiagnostico"):
            falsa = Mock(side_effect=nada)
            setattr(jarvis, metodo, falsa)
            falsas.append(falsa)
        return falsas

    def _recusa(self, nome, args=None):
        import main

        jarvis = _jarvis()
        with ExitStack() as pilha:
            pilha.enter_context(patch.dict(os.environ, {"JARVIS_CEREBRO": "gemma", "JARVIS_QA_MODE": "0"}))
            falsas = self._sem_chegar_a_nada(pilha, jarvis)
            resposta = _chamar(jarvis, nome, args)
        self.assertEqual(resposta, {"result": main.AVISO_MODO_PRIVADO}, nome)
        self.assertNotIn(("estado", "THINKING"), jarvis.ui.eventos, f"{nome} passou da trava")
        self.assertTrue(all(not f.called for f in falsas), f"{nome} chegou a uma ação")
        self.assertTrue(any("🔒" in texto for tipo, texto in jarvis.ui.eventos if tipo == "log"), nome)

    def test_cada_ferramenta_de_nuvem_e_recusada_antes_da_acao(self):
        import main

        foto = set(ler_foto(FOTO_POLITICAS)["FERRAMENTAS_NUVEM_IA"]) & _existentes()
        for nome in sorted(set(main.FERRAMENTAS_NUVEM_IA) | foto):
            with self.subTest(ferramenta=nome):
                self._recusa(nome)

    def test_regras_por_argumento_tambem_sao_recusadas(self):
        self._recusa("youtube_video", {"action": "summarize", "url": "x"})  # o resumo é feito pelo Gemini
        self._recusa("school_tasks", {"refresh": True})  # ler o Geekie de novo é trabalho do Hermes

    def test_automacoes_de_nuvem_sao_recusadas(self):
        import main

        de_nuvem = [nome for nome, a in main.carregar_automacoes().ferramentas.items() if a.usa_ia_nuvem]
        self.assertTrue(de_nuvem)
        for nome in de_nuvem:
            with self.subTest(automacao=nome):
                self._recusa(nome, {"description": "cliente Fulano", "confirm": True})

    def test_reserva_do_modo_privado_nao_oferece_nada_de_nuvem(self):
        # (cópia do tests/test_cerebro_gemma.py: a lista que vai para o Gemma e o Groq)
        import main

        jarvis = _jarvis()

        def nomes(cerebro):
            jarvis._reserva_ferramentas = None
            with patch.dict(os.environ, {"JARVIS_CEREBRO": cerebro, "JARVIS_RESERVA_FERRAMENTAS": "1"}):
                ferramentas, executar = jarvis._ferramentas_da_reserva()
            self.assertEqual(executar, jarvis._executar_ferramenta_reserva)  # roda pelo mesmo _execute_tool
            return {f["function"]["name"] for f in ferramentas}

        automacoes = main.carregar_automacoes().ferramentas
        proibidas = (set(main.FERRAMENTAS_NUVEM_IA) | set(ler_foto(FOTO_POLITICAS)["FERRAMENTAS_NUVEM_IA"])
                     | {"save_memory"} | {n for n, a in automacoes.items() if a.usa_ia_nuvem})
        privado = nomes("gemma")
        self.assertTrue(privado)
        self.assertEqual(privado & proibidas, set())
        self.assertIn("web_search", nomes("gemini"))  # fora do modo privado, a reserva tem a pesquisa


class ListaDeNuvemTests(unittest.TestCase):
    def test_lista_de_nuvem_so_cresce_enquanto_a_ferramenta_existir(self):
        import main

        foto = set(ler_foto(FOTO_POLITICAS)["FERRAMENTAS_NUVEM_IA"])
        saiu = foto - set(main.FERRAMENTAS_NUVEM_IA)
        self.assertEqual(saiu & _existentes(), set(),
                         "só sai da FERRAMENTAS_NUVEM_IA a ferramenta que deixou de existir")

    def test_automacao_de_nuvem_nao_perde_a_marca(self):
        import main

        automacoes = main.carregar_automacoes().ferramentas
        for nome in ler_foto(FOTO_POLITICAS)["AUTOMACOES_NUVEM_IA"]:
            if nome in automacoes:
                self.assertTrue(automacoes[nome].usa_ia_nuvem, f"{nome} perdeu o USA_IA_NUVEM = True")


# ======================================================================= ordem das travas

class OrdemDasTravasTests(unittest.TestCase):
    """cloud_safe → modo privado → Jarvis pronto → modo QA → desligar o Jarvis → save_memory."""

    def _ambiente(self, pilha, privado=False, qa=False):
        pilha.enter_context(patch.dict(os.environ, {"JARVIS_CEREBRO": "gemma" if privado else "gemini",
                                                    "JARVIS_QA_MODE": "1" if qa else "0"}))

    def test_servidor_vem_antes_de_tudo(self):
        import main

        ui = UIFalsa()
        ui.operational_ready = False
        jarvis = _jarvis(ui)
        jarvis.cloud_safe = True
        with ExitStack() as pilha:
            self._ambiente(pilha, privado=True, qa=True)
            pilha.enter_context(patch("core.qa_mode.guard_tool_call", side_effect=AssertionError("QA")))
            resposta = _chamar(jarvis, "hermes_agent", {"request": "x"})
        self.assertIn("unavailable in cloud-safe mode", resposta["result"])
        self.assertNotEqual(resposta["result"], main.AVISO_MODO_PRIVADO)
        self.assertEqual(ui.eventos, [])

    def test_modo_privado_vem_antes_do_jarvis_pronto_e_do_qa(self):
        import main

        ui = UIFalsa()
        ui.operational_ready = False
        jarvis = _jarvis(ui)
        with ExitStack() as pilha:
            self._ambiente(pilha, privado=True, qa=True)
            pilha.enter_context(patch("core.qa_mode.guard_tool_call", side_effect=AssertionError("QA")))
            self.assertEqual(_chamar(jarvis, "web_search", {"query": "x"})["result"], main.AVISO_MODO_PRIVADO)

    def test_jarvis_pronto_vem_antes_do_qa(self):
        ui = UIFalsa()
        ui.operational_ready = False
        jarvis = _jarvis(ui)
        with ExitStack() as pilha:
            self._ambiente(pilha, qa=True)
            pilha.enter_context(patch("core.qa_mode.guard_tool_call", side_effect=AssertionError("QA")))
            self.assertIn("Startup sequence active", _chamar(jarvis, "send_message", {"receiver": "Ana"})["result"])
        self.assertNotIn(("estado", "THINKING"), ui.eventos)

    def test_qa_vem_antes_de_desligar_o_jarvis_e_da_memoria(self):
        import main
        from core.qa_mode import QAGuardDecision

        jarvis = _jarvis()
        jarvis._intercept_ui_tool_call = Mock(side_effect=AssertionError("desligar antes do QA"))
        with ExitStack() as pilha:
            self._ambiente(pilha, qa=True)
            pilha.enter_context(patch("core.qa_mode.guard_tool_call", return_value=QAGuardDecision(False, "teste")))
            gravar = pilha.enter_context(patch.object(main, "update_memory"))
            for nome, args in (("jarvis_ui_control", {"action": "quit_jarvis"}),
                               ("save_memory", {"category": "notes", "key": "k", "value": "v"})):
                self.assertEqual(_chamar(jarvis, nome, args)["result"], "QA SAFETY BLOCK: teste", nome)
        gravar.assert_not_called()
        self.assertNotIn(("estado", "THINKING"), jarvis.ui.eventos)

    def test_desligar_o_jarvis_so_com_pedido_claro_antes_de_qualquer_ferramenta(self):
        jarvis = _jarvis()
        with ExitStack() as pilha:
            self._ambiente(pilha)
            resposta = _chamar(jarvis, "jarvis_ui_control", {"action": "quit_jarvis"})
        self.assertIn("Ignored an unverified shutdown request", resposta["result"])
        self.assertFalse(any(tipo == "tela" for tipo, _ in jarvis.ui.eventos))  # nada chegou à tela

    def test_save_memory_nao_grava_no_modo_privado(self):
        import main

        jarvis = _jarvis()
        with ExitStack() as pilha:
            self._ambiente(pilha, privado=True)
            gravar = pilha.enter_context(patch.object(main, "update_memory"))
            resposta = _chamar(jarvis, "save_memory", {"category": "relationships", "key": "cliente", "value": "deve"})
        self.assertEqual(resposta, {"result": "Memória não é gravada no modo privado.", "silent": True})
        gravar.assert_not_called()


# ======================================================================= o "ok" do Erton

def _modulo_videos():
    """O automacoes/videos.py carregado do zero (o estado do preço não vaza de outro teste)."""
    spec = importlib.util.spec_from_file_location("auto_videos_invariantes", RAIZ / "automacoes" / "videos.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class OkAntigoTests(unittest.TestCase):
    def setUp(self):
        from core import hermes_ponte

        hermes_ponte._proposta.clear()
        self.addCleanup(hermes_ponte._proposta.clear)

    def test_ok_antigo_nao_aprova_publicacao(self):
        from core import hermes_ponte

        aprovar = hermes_ponte.aprovar_e_executar
        post = "post da corrida no Instagram"
        with patch.object(hermes_ponte, "configurado", return_value=True), \
                patch.object(hermes_ponte, "_publicar") as publicar:
            # o "ok" dito ANTES de ouvir a proposta não vale
            jarvis = JarvisFalso("ok, pode publicar")
            aprovar("redes", post, jarvis, False)
            self.assertIn("Não registrei aprovação", aprovar("redes", post, jarvis, True))
            # o "ok" dado a uma proposta não vale para outra
            jarvis = JarvisFalso("prepara o post da corrida")
            aprovar("redes", post, jarvis, False)
            jarvis.falar("ok, pode publicar")
            self.assertIn("Não registrei aprovação", aprovar("redes", "outro post", jarvis, True))
            _esperar_fio("HermesPublicar")
            publicar.assert_not_called()
            # controle: um "ok" claro numa fala NOVA, depois da proposta, vale; e vale uma vez só
            jarvis = JarvisFalso("prepara o post da corrida")
            aprovar("redes", post, jarvis, False)
            jarvis.falar("ok, pode publicar")
            self.assertIn("Aprovado", aprovar("redes", post, jarvis, True))
            _esperar_fio("HermesPublicar")
            publicar.assert_called_once()
            self.assertIn("Não registrei aprovação", aprovar("redes", post, jarvis, True))
        publicar.assert_called_once()

    def test_ok_antigo_nao_aprova_video(self):
        videos = _modulo_videos()
        pedido = {"description": "a triathlete crossing the finish line in Hawaii", "seconds": 8}
        with patch.dict(os.environ, {"JARVIS_CEREBRO": "gemini"}), \
                patch.object(videos, "gerar", return_value=Path("video.mp4")) as gerar, \
                patch.object(videos, "_abrir"):
            # o "ok" dito ANTES de ouvir o preço não vale
            jarvis = JarvisFalso("ok, pode fazer")
            videos.executar(dict(pedido), jarvis)
            self.assertIn("Not confirmed", videos.executar(dict(pedido, confirm=True), jarvis))
            # o "ok" dado ao preço de um vídeo não vale para outro
            jarvis = JarvisFalso("faz um vídeo de um triatleta")
            videos.executar(dict(pedido), jarvis)
            jarvis.falar("ok, pode fazer")
            self.assertIn("Not confirmed", videos.executar(dict(pedido, seconds=4, confirm=True), jarvis))
            _esperar_fio("VideoVeo")
            gerar.assert_not_called()
            # controle: um "ok" claro numa fala NOVA, depois do preço, vale; e vale uma vez só
            jarvis = JarvisFalso("faz um vídeo de um triatleta")
            videos.executar(dict(pedido), jarvis)
            jarvis.falar("ok, pode fazer")
            self.assertIn("background", videos.executar(dict(pedido, confirm=True), jarvis))
            _esperar_fio("VideoVeo")
            gerar.assert_called_once()
            self.assertIn("Not confirmed", videos.executar(dict(pedido, confirm=True), jarvis))
        gerar.assert_called_once()


# ======================================================================= chaves

class ChaveTests(unittest.TestCase):
    def _configurar(self, pasta: Path, chave: str, verificada: str, lembrar: bool, reserva: bool = False):
        import ui

        logs = []
        cofre = Mock()
        overlay = NS(_verified_key=verificada, _modo_reserva=reserva, _modo_gemma=False, hide=lambda: None)
        janela = NS(_overlay=overlay, _log=NS(append_log=logs.append), _ready=False,
                    _apply_state=lambda estado: None, _show_voice_select_then_name=lambda: None)
        with patch.object(ui, "BASE_DIR", pasta), patch.object(ui, "CONFIG_DIR", pasta / "config"), \
                patch.object(ui, "API_FILE", pasta / "config" / "api_keys.json"), \
                patch.object(ui, "get_secret_store", return_value=cofre), \
                patch.dict(os.environ, {"GEMINI_API_KEY": "", "JARVIS_GEMINI_VIA": "studio"}):
            ui.MainWindow._on_setup_done(janela, chave, "windows", lembrar)
        return cofre, logs

    def _pasta(self) -> Path:
        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        pasta = Path(temporaria.name)
        (pasta / "config").mkdir()
        # um api_keys.json antigo que ainda guardava a chave em texto
        (pasta / "config" / "api_keys.json").write_text(json.dumps({"gemini_api_key": "AIza-antiga"}), encoding="utf-8")
        (pasta / ".env").write_text('GEMINI_API_KEY="AIza-velha"\n', encoding="utf-8")
        return pasta

    def test_chave_nunca_vai_para_o_api_keys_json(self):
        chave = "AIza" + "e" * 35
        for lembrar in (True, False):
            with self.subTest(lembrar=lembrar):
                pasta = self._pasta()
                cofre, logs = self._configurar(pasta, chave, chave, lembrar)
                api = (pasta / "config" / "api_keys.json").read_text(encoding="utf-8")
                self.assertNotIn(chave, api)
                self.assertNotIn("gemini_api_key", api)
                self.assertFalse(any(chave in linha for linha in logs), "a chave apareceu no registro")
                # vai para o cofre do Windows só se ele marcou; para o .env, porque foi aceita
                if lembrar:
                    cofre.set.assert_called_once_with("gemini_api_key", chave)
                else:
                    cofre.set.assert_not_called()
                self.assertIn(chave, (pasta / ".env").read_text(encoding="utf-8"))

    def test_chave_nao_verificada_nao_vai_para_lugar_nenhum(self):
        chave = "AIza" + "f" * 35
        pasta = self._pasta()
        env_antes = (pasta / ".env").read_text(encoding="utf-8")
        cofre, logs = self._configurar(pasta, chave, "AIza" + "g" * 35, True)
        cofre.set.assert_not_called()
        self.assertEqual((pasta / ".env").read_text(encoding="utf-8"), env_antes)
        self.assertNotIn(chave, (pasta / "config" / "api_keys.json").read_text(encoding="utf-8"))
        self.assertFalse(any(chave in linha for linha in logs))

    def test_chave_recusada_pela_reserva_nao_e_guardada(self):
        chave = "AIza" + "h" * 35
        pasta = self._pasta()
        env_antes = (pasta / ".env").read_text(encoding="utf-8")
        cofre, _ = self._configurar(pasta, chave, "", True, reserva=True)
        cofre.set.assert_not_called()
        self.assertEqual((pasta / ".env").read_text(encoding="utf-8"), env_antes)
        self.assertNotIn(chave, (pasta / "config" / "api_keys.json").read_text(encoding="utf-8"))


# ======================================================================= lote do Gemini

def _rodar_lote(nomes):
    """Roda um lote pelo _execute_tool_batch de verdade; devolve (resultados, quantas abertas no máximo)."""
    import main

    jarvis = object.__new__(main.JarvisLive)
    abertas, maximo = [0], [0]

    async def executar(chamada):
        abertas[0] += 1
        maximo[0] = max(maximo[0], abertas[0])
        await asyncio.sleep(0)
        abertas[0] -= 1
        return chamada.name

    jarvis._execute_tool = executar
    resultados = asyncio.run(jarvis._execute_tool_batch([NS(name=nome) for nome in nomes]))
    return resultados, maximo[0]


class LoteDoGeminiTests(unittest.TestCase):
    # (cópia do tests/test_qa_system.py: o lote que muda algo continua em fila)
    def test_o_que_muda_algo_roda_em_fila_e_na_ordem(self):
        existentes = _existentes()
        fila_de_hoje = set(em_fila(existentes))
        for nome in ler_foto(FOTO_POLITICAS)["mutating"]:
            if nome not in existentes:
                continue  # a ferramenta deixou de existir
            with self.subTest(ferramenta=nome):
                self.assertIn(nome, fila_de_hoje, "o 'mutating' só pode crescer")
                resultados, maximo = _rodar_lote(["web_search", nome, "weather_report"])
                self.assertEqual(resultados, ["web_search", nome, "weather_report"])
                self.assertEqual(maximo, 1)

    def test_lote_so_de_leitura_roda_junto_e_na_ordem(self):
        resultados, maximo = _rodar_lote(["weather_report", "web_search"])
        self.assertEqual(resultados, ["weather_report", "web_search"])
        self.assertEqual(maximo, 2)


# ======================================================================= servidor (cloud_safe)

class ClienteFalso:
    """O mínimo do contrato JarvisClient para abrir a JarvisLive no modo servidor."""

    def __init__(self):
        self.on_text_command = None
        self.muted = False
        self.current_file = None
        self._voice_combo = None
        self.eventos = []

    def write_log(self, texto):
        self.eventos.append(("log", texto))

    def set_state(self, estado):
        self.eventos.append(("estado", estado))

    def show_subtitle(self, texto):
        self.eventos.append(("legenda", texto))

    def clear_subtitle(self):
        self.eventos.append(("legenda", None))

    def set_theme(self, tema):
        self.eventos.append(("tema", tema))

    def set_graphics_quality(self, qualidade):
        self.eventos.append(("graficos", qualidade))

    def sync_voice_display(self, voz):
        self.eventos.append(("voz", voz))

    def handle_ui_command(self, acao):
        self.eventos.append(("tela", acao))


class ServidorTests(unittest.TestCase):
    # (cópia do tests/test_phase1_decoupling.py, que sai junto com o servidor)
    def test_modo_servidor_so_oferece_a_lista_liberada(self):
        import main

        jarvis = main.JarvisLive(ClienteFalso(), cloud_safe=True)
        nomes = {d["name"] for d in jarvis.tool_declarations}
        self.assertTrue(nomes)
        self.assertLessEqual(nomes, set(main.CLOUD_SAFE_ACTIONS))
        self.assertEqual(nomes & AGEM_NO_PC, set())

    def test_modo_servidor_recusa_o_resto_sem_tocar_na_tela(self):
        import main

        cliente = ClienteFalso()
        jarvis = main.JarvisLive(cliente, cloud_safe=True)
        resto = (({d["name"] for d in main.TOOL_DECLARATIONS} | set(main.carregar_automacoes().ferramentas))
                 - set(main.CLOUD_SAFE_ACTIONS))
        for nome in sorted(resto | AGEM_NO_PC):
            with self.subTest(ferramenta=nome):
                resposta = _chamar(jarvis, nome)
                self.assertIn("unavailable in cloud-safe mode", resposta["result"])
        self.assertEqual(cliente.eventos, [])


if __name__ == "__main__":
    unittest.main()
