"""Fotos de como o Jarvis é HOJE (Etapa 1 do docs/PLANO-REORGANIZACAO.md).

Uma foto guarda o que nenhuma mudança pode alterar sem querer:
  - o texto e a ordem das declarações das ferramentas (TOOL_DECLARATIONS): o Gemini escolhe a
    ferramenta por esse texto. Foto em tests/dados/declaracoes_antes.json;
  - as listas de política: FERRAMENTAS_NUVEM_IA, CLOUD_SAFE_ACTIONS, RESERVA_FERRAMENTAS_ESSENCIAIS e o
    "mutating" do _execute_tool_batch (o que roda em fila num lote). Foto em tests/dados/politicas_antes.json;
  - os métodos da JarvisLive, os nomes que outros arquivos usam e os nomes da ponte entre a tela e o
    cérebro (core/ponte.py);
  - a resposta padrão de cada ferramenta nativa quando a ação não devolve nada ("Done."...);
  - as ferramentas herdadas desligadas de propósito na Etapa 3 (DESLIGADAS): não são oferecidas, o
    prompt não as cita e, chamadas mesmo assim, respondem "desligada" sem tocar na ação.

Mudou de propósito numa etapa do plano? Atualize a foto no MESMO commit e só no que mudou:
    python tests/test_contratos.py --gravar-fotos
regrava os dois .json (confira no "git diff" que só mudou o que devia); os métodos, os nomes e as
respostas padrão ficam nas listas deste arquivo, editadas à mão.

As regras que nunca podem quebrar, nem de propósito (modo privado, "ok", chaves), ficam no
tests/test_invariantes.py, com a base delas escrita à mão lá: o --gravar-fotos não a muda. O mapa das
travas está no core/SEGURANCA.md."""

import asyncio
import json
import os
import re
import sys
import time
import types
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

DADOS = RAIZ / "tests" / "dados"
FOTO_DECLARACOES = DADOS / "declaracoes_antes.json"
FOTO_POLITICAS = DADOS / "politicas_antes.json"

SOBRE_POLITICAS = (
    "Foto das listas de política do main.py (Etapa 1 da reorganização). Só muda de propósito, numa etapa "
    "do docs/PLANO-REORGANIZACAO.md, no mesmo commit da mudança: python tests/test_contratos.py --gravar-fotos. "
    "'mutating' = ferramentas que o _execute_tool_batch roda em fila (conferido pelo comportamento). "
    "'AUTOMACOES_NUVEM_IA' = automações da pasta com USA_IA_NUVEM = True (o test_invariantes confere que "
    "nenhuma perde a marca)."
)
# as listas que têm de ficar IGUAIS à foto (a das automações só pode crescer: test_invariantes)
POLITICAS_IGUAIS = ("FERRAMENTAS_NUVEM_IA", "CLOUD_SAFE_ACTIONS", "RESERVA_FERRAMENTAS_ESSENCIAIS", "mutating")


# ======================================================================= como as fotos são tiradas

def declaracoes_de_hoje() -> list:
    """TOOL_DECLARATIONS como o Gemini recebe (texto e ordem)."""
    import main

    return json.loads(json.dumps(main.TOOL_DECLARATIONS, ensure_ascii=False))


def ler_foto(arquivo: Path):
    return json.loads(arquivo.read_text(encoding="utf-8"))


def em_fila(nomes) -> list[str]:
    """As ferramentas que o _execute_tool_batch roda em fila, uma depois da outra (o "mutating").
    Conferido pelo comportamento, não pelo texto: num lote com duas chamadas da mesma ferramenta, conta
    quantas ficam abertas ao mesmo tempo. Assim a foto continua valendo se a lista mudar de lugar."""
    import main

    jarvis = object.__new__(main.JarvisLive)
    fila = []
    for nome in sorted(set(nomes)):
        abertas, maximo = [0], [0]

        async def executar(chamada, abertas=abertas, maximo=maximo):
            abertas[0] += 1
            maximo[0] = max(maximo[0], abertas[0])
            await asyncio.sleep(0)
            abertas[0] -= 1
            return chamada.name

        jarvis._execute_tool = executar
        asyncio.run(jarvis._execute_tool_batch([NS(name=nome), NS(name=nome)]))
        if maximo[0] == 1:
            fila.append(nome)
    return fila


def _nomes_da_foto() -> set[str]:
    try:
        foto = ler_foto(FOTO_POLITICAS)
    except (OSError, ValueError):
        return set()
    return {nome for lista in foto.values() if isinstance(lista, list) for nome in lista}


def politicas_de_hoje() -> dict:
    import main

    automacoes = main.carregar_automacoes().ferramentas
    # o "mutating" é conferido em toda ferramenta conhecida, inclusive as que saírem da lista do Gemini
    candidatos = ({d.get("name") for d in main.TOOL_DECLARATIONS} | set(automacoes)
                  | set(main.FERRAMENTAS_NUVEM_IA) | set(main.CLOUD_SAFE_ACTIONS)
                  | set(main.JarvisLive.RESERVA_FERRAMENTAS_ESSENCIAIS) | _nomes_da_foto())
    return {
        "_sobre": SOBRE_POLITICAS,
        "FERRAMENTAS_NUVEM_IA": sorted(main.FERRAMENTAS_NUVEM_IA),
        "CLOUD_SAFE_ACTIONS": sorted(main.CLOUD_SAFE_ACTIONS),
        "RESERVA_FERRAMENTAS_ESSENCIAIS": sorted(main.JarvisLive.RESERVA_FERRAMENTAS_ESSENCIAIS),
        "mutating": em_fila(candidatos),
        "AUTOMACOES_NUVEM_IA": sorted(nome for nome, a in automacoes.items() if getattr(a, "usa_ia_nuvem", False)),
    }


def gravar_fotos() -> None:
    """Regrava os dois .json com o código de agora (só numa mudança de propósito)."""
    FOTO_DECLARACOES.write_text(json.dumps(declaracoes_de_hoje(), ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
    FOTO_POLITICAS.write_text(json.dumps(politicas_de_hoje(), ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")


# ======================================================================= o que outros arquivos usam

# Métodos da JarvisLive (main.py). Só muda de propósito (ex.: a Etapa 5 apaga o set_tour_active).
METODOS_DA_JARVISLIVE = frozenset({
    "__init__", "_announce_startup", "_ativar_modo_reserva", "_autodiagnostico", "_avisar_o_que_para",
    "_avisar_se_nao_enviou", "_avisar_sem_ouvido", "_aviso_de_escuta", "_build_config", "_chamada_fechada",
    "_checar_pedido_de_modo", "_complete_self_quit_after_audio", "_definir_modo_escuta",
    "_desativar_modo_reserva", "_encerrar_fim_do_teste", "_entregar_resultado_hermes", "_escutar_reserva",
    "_esquecer_sessao_ao_sair", "_executar_ferramenta_reserva", "_execute_tool", "_execute_tool_batch",
    "_falar_aviso", "_falar_avisos_guardados", "_falar_com_voz_externa", "_falar_no_pc", "_falar_reserva",
    "_falar_resultado_ultron", "_ferramentas_da_reserva", "_force_complete_self_quit",
    "_garantir_loop_reserva", "_geekie_pendencias", "_get_current_voice", "_guardar_ate_conectar",
    "_hermes_sem_travar", "_idioma_voz", "_iniciar_lembretes_geekie", "_intercept_ui_tool_call",
    "_is_explicit_self_quit_transcript", "_ligar_cerebro_gemma", "_listen_audio", "_mandar_textos_esperando",
    "_mark_self_quit_farewell_received", "_microfone_mandou_audio", "_mostrar_selo", "_mostrar_volume",
    "_notificar_na_tela", "_nova_fala", "_on_text_command", "_pedido_de_cerebro", "_pedido_de_ultron",
    "_play_audio", "_pode_falar_agora", "_preparar_automacoes", "_queue_self_quit_after_farewell",
    "_receive_audio", "_recusar_troca", "_responder_pela_reserva", "_send_realtime", "_speak_vision_result",
    "_suspender", "_trava_avisos", "_trava_da_fala", "_trava_textos", "_troca_pela_voz_indisponivel",
    "_trocar_cerebro", "_verificar_lembretes_geekie", "_voltar_da_suspensao", "_wait_before_reconnect",
    "anunciar", "request_shutdown", "rodar_automacao_ultron", "run", "send_audio_chunk", "send_text",
    "set_speaking", "set_tour_active", "speak", "speak_error", "update_voice",
})

# Nomes da JarvisLive que outros arquivos chamam (e quem chama). Não podem sumir nem mudar de nome.
USADOS_POR_OUTROS_ARQUIVOS = {
    "anunciar": "automacoes/videos.py, claude_tarefas.py e lembretes.py; core/hermes_ponte.py",
    "_falar_aviso": "automacoes/videos.py e claude_tarefas.py",
    "_hermes_sem_travar": "automacoes/rotinas.py",
    "rodar_automacao_ultron": "automacoes/painel_ultron.py e core/ponte.py",
    "_ativar_modo_reserva": "automacoes/autoconserto.py",
    "_definir_modo_escuta": "automacoes/autoconserto.py",
}
# Funções do main.py que outros arquivos importam.
FUNCOES_DO_MAIN = {
    "rodar_cerebro": "core/processo_cerebro.py (main.rodar_cerebro) e core/ponte.py",
    "carregar_automacoes": "automacoes/painel_ultron.py (from main import carregar_automacoes)",
}

# A ponte entre a tela e o cérebro (core/ponte.py): os 29 métodos da tela que o cérebro chama e os
# avisos da tela para o cérebro. A JarvisUI (ui.py) e a UIRemota atendem por estes nomes.
METODOS_TELA = frozenset({
    "write_log", "set_state", "set_voice_level", "set_muted_threadsafe", "set_listening_status",
    "start_speaking", "stop_speaking", "sync_voice_display",
    "show_subtitle", "clear_subtitle", "start_subtitle_hold",
    "show_vision_preview", "hide_vision_preview",
    "show_research_progress", "update_research_progress", "finish_research_progress",
    "hide_research_progress",
    "show_presentation_progress", "update_presentation_progress", "finish_presentation_progress",
    "hide_presentation_progress",
    "show_toast", "show_tool_progress", "hide_tool_progress",
    "set_theme", "set_graphics_quality", "handle_ui_command", "toggle_compact_mode", "notificar",
})
CHAMADAS_DO_CEREBRO = ("on_text_command", "on_voice_change", "on_name_change",
                       "on_tts_provider_change", "on_quit_requested")


# ======================================================================= respostas padrão

# Resposta de cada ferramenta nativa quando a ação (falsa) não devolve nada: (ferramenta, argumentos,
# resposta). Quem não tem texto padrão devolve o que a ação devolveu (aqui, None). Estes textos voltam
# para o Gemini e ficam em inglês. Toda ferramenta declarada tem de estar aqui (o save_memory tem teste próprio).
# As desligadas na Etapa 3 (DESLIGADAS, mais abaixo) saíram daqui de propósito: respondem "desligada".
RESPOSTAS_PADRAO = (
    ("open_app", {"app_name": "Spotify"}, "Opened Spotify."),
    ("web_search", {"query": "x"}, "Done."),
    ("listening_mode", {"mode": "chamada"}, None),
    ("school_tasks", {}, None),
    ("self_diagnosis", {}, None),
    ("hermes_agent", {"request": "x"}, None),
    ("approve_publication", {"kind": "redes", "details": "x"}, None),
    ("suspend_listening", {"minutes": 5}, None),
    ("generate_image", {"prompt": "x"}, None),
    ("weather_report", {"city": "João Pessoa"}, "Weather delivered."),
    ("email_control", {"action": "inbox"}, "Email action completed."),
    ("reminder", {}, "Reminder set."),
    ("youtube_video", {"action": "play"}, "Done."),
    ("media_control", {}, "Done."),
    ("screen_process", {}, "Vision module activated. Stay completely silent — vision module will speak directly."),
    ("computer_settings", {}, "Done."),
    ("browser_control", {}, "Done."),
    ("file_controller", {"action": "list"}, "Done."),
    ("desktop_control", {}, "Done."),
    ("flight_finder", {}, "Done."),
    ("graphics_quality", {"quality": "low"}, "JARVIS graphics quality changed to low."),
    ("jarvis_ui_control", {"action": "open_settings"}, "JARVIS interface action completed: open settings."),
    ("jarvis_ui_control", {"action": "change_theme", "theme": "platinum"}, "JARVIS theme changed to platinum."),
    ("jarvis_ui_control", {"action": "change_graphics_quality", "graphics_quality": "high"},
     "JARVIS graphics quality changed to high."),
    ("deep_research", {}, "Deep research preference requested."),
    ("create_presentation", {}, "Presentation preference requested."),
    ("task_status", {"action": "all"}, "{}"),
    ("task_status", {"action": "cancel", "task_id": "t1"}, "Task t1 could not be cancelled."),
    ("task_status", {"task_id": "t1"}, "Task t1 was not found."),
    ("file_processor", {"file_path": "a.txt"}, "Done."),
    ("ferramenta_que_nao_existe", {}, "Unknown tool: ferramenta_que_nao_existe"),
)

# A ação falsa de cada ferramenta: ("main", nome no main.py), ("jarvis", método da JarvisLive) ou
# ("modulo", "módulo.função"). O teste confere que ela foi mesmo chamada (nenhum passa por engano).
ACAO = {
    "open_app": ("main", "open_app"), "web_search": ("main", "web_search_action"),
    "weather_report": ("main", "weather_action"),
    "email_control": ("main", "email_control"), "reminder": ("main", "reminder"),
    "youtube_video": ("main", "youtube_video"), "media_control": ("main", "media_control"),
    "screen_process": ("main", "screen_process"), "computer_settings": ("main", "computer_settings"),
    "browser_control": ("main", "browser_control"), "file_controller": ("main", "file_controller"),
    "desktop_control": ("main", "desktop_control"),
    "flight_finder": ("main", "flight_finder"),
    "deep_research": ("main", "request_deep_research"), "create_presentation": ("main", "request_presentation"),
    "file_processor": ("main", "file_processor"),
    "listening_mode": ("jarvis", "_definir_modo_escuta"), "school_tasks": ("jarvis", "_geekie_pendencias"),
    "self_diagnosis": ("jarvis", "_autodiagnostico"), "hermes_agent": ("jarvis", "_hermes_sem_travar"),
    "suspend_listening": ("jarvis", "_suspender"),
    "approve_publication": ("modulo", "core.hermes_ponte.aprovar_e_executar"),
    "generate_image": ("modulo", "core.modelos.gerar_imagem"),
    "task_status": ("fila", None),
    "graphics_quality": ("tela", "set_graphics_quality"), "jarvis_ui_control": ("tela", None),
}
ASSINCRONAS = {"_geekie_pendencias", "_hermes_sem_travar"}

# Ferramentas herdadas DESLIGADAS de propósito na Etapa 3 (decisão do Erton: agiam sem o "ok" dele
# conferido no código, ou ele não usa), com os módulos das ações delas, que nem podem ser usados quando
# alguém chama a ferramenta. Escrita à mão, e não lida do main.FERRAMENTAS_DESLIGADAS: tirar um nome
# daqui é religar a ferramenta, e isso só acontece de propósito.
DESLIGADAS = {
    "send_message": ("actions.send_message",),
    "prepare_message_reply": ("actions.send_message",),
    "check_messages": ("actions.message_monitor", "actions.send_message"),
    "agent_task": ("agent.executor", "agent.planner"),
    "code_helper": ("actions.code_helper",),
    "dev_agent": ("actions.dev_agent",),
    "computer_control": ("actions.computer_control",),
    "game_updater": ("actions.game_updater",),
}


class UIFalsa:
    """O mínimo da tela que o _execute_tool usa; guarda o que foi pedido."""

    def __init__(self):
        self.muted = False
        self.current_file = None
        self.eventos = []

    def write_log(self, texto):
        self.eventos.append(("log", texto))

    def set_state(self, estado):
        self.eventos.append(("estado", estado))

    def set_graphics_quality(self, qualidade):
        self.eventos.append(("graficos", qualidade))

    def set_theme(self, tema):
        self.eventos.append(("tema", tema))

    def handle_ui_command(self, acao):
        self.eventos.append(("tela", acao))


class FilaFalsa:
    """Imita a fila de tarefas (agent/task_queue.py) sem rodar nada."""

    def __init__(self):
        self.submit = Mock(return_value="t1")
        self.get_all_statuses = Mock(return_value={})
        self.cancel = Mock(return_value=False)
        self.get_status = Mock(return_value=None)


def acoes_do_main() -> list[str]:
    """As ações das ferramentas nativas no main.py (carregadas só na hora de usar: _lazy_action)."""
    import main

    return sorted(nome for nome, valor in vars(main).items()
                  if getattr(valor, "__qualname__", "") == "_lazy_action.<locals>.invoke")


def rodar_ferramenta(nome: str, args: dict, *, privado: bool = False):
    """Chama o _execute_tool de verdade com TODAS as ações trocadas por falsas que não devolvem nada.
    Devolve (resposta, falsas, ui)."""
    import main

    ui = UIFalsa()
    jarvis = object.__new__(main.JarvisLive)
    jarvis.ui = jarvis.client = ui
    jarvis.cloud_safe = False
    jarvis.speak_error = Mock()
    fila = FilaFalsa()
    falsas = {"fila": fila, "speak_error": jarvis.speak_error}
    with ExitStack() as pilha:
        pilha.enter_context(patch.dict(os.environ, {"JARVIS_CEREBRO": "gemma" if privado else "gemini",
                                                    "JARVIS_QA_MODE": "0"}))
        for acao in acoes_do_main():
            falsas[acao] = pilha.enter_context(patch.object(main, acao, Mock(return_value=None)))
        for metodo in ("_definir_modo_escuta", "_geekie_pendencias", "_autodiagnostico",
                       "_hermes_sem_travar", "_suspender"):
            falsa = AsyncMock(return_value=None) if metodo in ASSINCRONAS else Mock(return_value=None)
            setattr(jarvis, metodo, falsa)
            falsas[metodo] = falsa
        for alvo in ("core.hermes_ponte.aprovar_e_executar", "core.modelos.gerar_imagem",
                     "core.hermes_ponte.perguntar"):
            falsas[alvo] = pilha.enter_context(patch(alvo, Mock(return_value=None)))
        pilha.enter_context(patch("agent.task_queue.get_queue", return_value=fila))
        falsas["update_memory"] = pilha.enter_context(patch.object(main, "update_memory"))
        resposta = asyncio.run(jarvis._execute_tool(NS(id="1", name=nome, args=dict(args))))
    return resposta, falsas, ui


class ModuloProibido(types.ModuleType):
    """Fica no lugar do módulo da ação de uma ferramenta desligada: anota e falha se alguém o usar."""

    def __init__(self, nome: str, usados: list):
        super().__init__(nome)
        self._usados = usados

    def __getattr__(self, nome):
        if nome.startswith("__"):
            raise AttributeError(nome)
        self._usados.append(f"{self.__name__}.{nome}")
        raise AssertionError(f"{self.__name__}.{nome} foi usado por uma ferramenta desligada")


def _chamadas(falsas: dict) -> list[str]:
    """As ações falsas (de rodar_ferramenta) que foram chamadas."""
    chamadas = [nome for nome, falsa in falsas.items() if nome != "fila" and falsa.called]
    fila = falsas["fila"]
    chamadas += [f"fila.{nome}" for nome in ("submit", "get_all_statuses", "cancel", "get_status")
                 if getattr(fila, nome).called]
    return chamadas


def _esperar_chamada(falsa, segundos: float = 3.0) -> None:
    """A visão (screen_process) roda num fio: espera a ação falsa ser chamada."""
    limite = time.monotonic() + segundos
    while not falsa.called and time.monotonic() < limite:
        time.sleep(0.01)


# ======================================================================= testes

class FotosTests(unittest.TestCase):
    def test_declaracoes_iguais_a_foto(self):
        foto = ler_foto(FOTO_DECLARACOES)
        hoje = declaracoes_de_hoje()
        self.assertEqual([d.get("name") for d in hoje], [d.get("name") for d in foto],
                         "a lista ou a ordem das ferramentas que o Gemini vê mudou")
        for atual, antes in zip(hoje, foto):
            self.assertEqual(atual, antes, f"o texto da declaração de {antes.get('name')} mudou")

    def test_politicas_iguais_a_foto(self):
        foto = ler_foto(FOTO_POLITICAS)
        hoje = politicas_de_hoje()
        for lista in POLITICAS_IGUAIS:
            entrou = sorted(set(hoje[lista]) - set(foto[lista]))
            saiu = sorted(set(foto[lista]) - set(hoje[lista]))
            self.assertEqual(hoje[lista], foto[lista], f"{lista} mudou: entrou {entrou}, saiu {saiu}")

    def test_lista_do_gemini_tem_as_fixas_e_depois_as_automacoes(self):
        # (cópia do tests/test_phase1_decoupling.py, que sai junto com o servidor)
        import main

        base = len(main.TOOL_DECLARATIONS)
        todas = main.get_tool_declarations()
        self.assertEqual(todas[:base], main.TOOL_DECLARATIONS)
        self.assertEqual({d["name"] for d in todas[base:]}, set(main.carregar_automacoes().ferramentas))


class NomesTests(unittest.TestCase):
    def test_metodos_da_jarvislive_iguais_a_foto(self):
        import inspect

        import main

        hoje = {nome for nome, valor in vars(main.JarvisLive).items()
                if inspect.isfunction(valor) or isinstance(valor, (staticmethod, classmethod, property))}
        self.assertEqual(hoje, METODOS_DA_JARVISLIVE,
                         f"sumiram {sorted(METODOS_DA_JARVISLIVE - hoje)}; apareceram {sorted(hoje - METODOS_DA_JARVISLIVE)}")

    def test_nomes_que_outros_arquivos_usam(self):
        import main

        for nome, quem in USADOS_POR_OUTROS_ARQUIVOS.items():
            self.assertTrue(callable(getattr(main.JarvisLive, nome, None)), f"JarvisLive.{nome} (usado por {quem})")
        for nome, quem in FUNCOES_DO_MAIN.items():
            self.assertTrue(callable(getattr(main, nome, None)), f"main.{nome} (usado por {quem})")

    def test_nomes_da_ponte_entre_a_tela_e_o_cerebro(self):
        from core import ponte

        self.assertEqual(len(METODOS_TELA), 29)
        self.assertEqual(ponte.METODOS_TELA, METODOS_TELA)
        self.assertEqual(ponte.CHAMADAS_DO_CEREBRO, CHAMADAS_DO_CEREBRO)


class RespostasPadraoTests(unittest.TestCase):
    def test_toda_ferramenta_declarada_tem_resposta_na_foto(self):
        import main

        na_foto = {nome for nome, _, _ in RESPOSTAS_PADRAO} | {"save_memory"}
        declaradas = {d["name"] for d in main.TOOL_DECLARATIONS}
        self.assertEqual(declaradas - na_foto, set())

    def test_resposta_padrao_de_cada_ferramenta(self):
        for nome, args, esperada in RESPOSTAS_PADRAO:
            with self.subTest(ferramenta=nome, args=args):
                resposta, falsas, ui = rodar_ferramenta(nome, args)
                self.assertEqual(resposta.name, nome)
                self.assertEqual(resposta.response, {"result": esperada})
                tipo, alvo = ACAO.get(nome, (None, None))
                if tipo in ("main", "jarvis", "modulo"):
                    falsa = falsas[alvo]
                    _esperar_chamada(falsa)
                    self.assertTrue(falsa.called, f"{nome} não chegou à ação {alvo}")
                elif tipo == "fila" and alvo:
                    self.assertTrue(getattr(falsas["fila"], alvo).called, nome)
                elif tipo == "tela":
                    self.assertTrue(any(e[0] in ("graficos", "tema", "tela") for e in ui.eventos), nome)
                falsas["speak_error"].assert_not_called()

    def test_save_memory_grava_e_responde_ok_em_silencio(self):
        resposta, falsas, _ = rodar_ferramenta("save_memory", {"category": "notes", "key": "k", "value": "v"})
        self.assertEqual(resposta.response, {"result": "ok", "silent": True})
        falsas["update_memory"].assert_called_once_with({"notes": {"k": {"value": "v"}}})

    def test_automacao_da_pasta_devolve_o_texto_da_automacao(self):
        import main

        automacao = NS(executar=Mock(return_value=None), usa_ia_nuvem=False)
        with patch.object(main, "carregar_automacoes", return_value=NS(ferramentas={"automacao_de_teste": automacao})):
            resposta, _, _ = rodar_ferramenta("automacao_de_teste", {"x": 1})
        self.assertEqual(resposta.response, {"result": "None"})
        automacao.executar.assert_called_once()

    def test_acao_que_falha_vira_texto_de_falha_e_aviso(self):
        import main

        jarvis = object.__new__(main.JarvisLive)
        jarvis.ui = jarvis.client = UIFalsa()
        jarvis.cloud_safe = False
        with patch.dict(os.environ, {"JARVIS_CEREBRO": "gemini", "JARVIS_QA_MODE": "0"}), \
                patch.object(main, "web_search_action", side_effect=RuntimeError("caiu a rede")):
            jarvis.speak_error = Mock()
            resposta = asyncio.run(jarvis._execute_tool(NS(id="1", name="web_search", args={"query": "x"})))
        self.assertEqual(resposta.response, {"result": "Tool 'web_search' failed: caiu a rede"})
        jarvis.speak_error.assert_called_once()


class DesligadasTests(unittest.TestCase):
    """Etapa 3: as ferramentas herdadas que agiam sem o "ok" do Erton saíram da lista do Gemini. Chamadas
    mesmo assim (um nome antigo, o modelo inventando), respondem "desligada" e não chamam nada."""

    def test_nenhuma_desligada_e_oferecida_ao_gemini_nem_a_reserva(self):
        import main

        oferecidas = main.get_tool_declarations()
        self.assertEqual({d["name"] for d in oferecidas} & set(DESLIGADAS), set())
        self.assertEqual(set(main.JarvisLive.RESERVA_FERRAMENTAS_ESSENCIAIS) & set(DESLIGADAS), set())
        self.assertEqual(set(main.CLOUD_SAFE_ACTIONS) & set(DESLIGADAS), set())  # nem no modo servidor
        # nem o texto de outra ferramenta manda o Gemini para uma delas
        texto = json.dumps(oferecidas, ensure_ascii=False)
        self.assertEqual({nome for nome in DESLIGADAS if re.search(rf"\b{nome}\b", texto)}, set())
        self.assertLessEqual(set(DESLIGADAS), set(main.FERRAMENTAS_DESLIGADAS))

    def test_prompt_nao_cita_ferramenta_que_nao_existe(self):
        import main

        prompt = (RAIZ / "core" / "prompt.txt").read_text(encoding="utf-8")
        existem = {d["name"] for d in main.get_tool_declarations()}
        # o que já foi ferramenta: as desligadas e os nomes das listas de política (que as guardam)
        ja_foram = set(DESLIGADAS) | set(main.FERRAMENTAS_NUVEM_IA) | set(main.CLOUD_SAFE_ACTIONS) | _nomes_da_foto()
        citadas = set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", prompt))
        self.assertEqual((citadas & ja_foram) - existem, set())
        # cada linha "ferramenta: quando usar" fala de uma ferramenta que existe
        self.assertEqual(set(re.findall(r"^([a-z]+(?:_[a-z]+)+):", prompt, re.M)) - existem, set())

    def test_chamar_uma_desligada_responde_e_nao_chama_nada(self):
        import main

        usados = []
        proibidos = {modulo: ModuloProibido(modulo, usados) for modulos in DESLIGADAS.values() for modulo in modulos}
        args = {"receiver": "Ana", "message_text": "oi", "platform": "WhatsApp", "action": "send", "goal": "x"}
        for nome in sorted(DESLIGADAS):
            with self.subTest(ferramenta=nome):
                with patch.dict(sys.modules, proibidos):
                    resposta, falsas, ui = rodar_ferramenta(nome, args)
                self.assertEqual(resposta.response, {"result": main.resposta_de_desligada(nome)})
                self.assertIn(f"Tool '{nome}'", resposta.response["result"])
                self.assertIn("is turned off", resposta.response["result"])
                self.assertEqual(usados, [])
                self.assertEqual(_chamadas(falsas), [])
                self.assertIn(("log", f"SYS: ⛔ {nome} está desligada no Jarvis."), ui.eventos)

    def test_automacao_com_nome_de_desligada_nao_carrega(self):
        # o nome de uma desligada continua reservado: um automacoes/send_message.py não volta a ser oferecido
        import tempfile

        import core.automacoes
        import main

        guardadas = main._AUTOMACOES
        with tempfile.TemporaryDirectory() as pasta:
            for nome in DESLIGADAS:
                (Path(pasta) / f"{nome}.py").write_text(
                    f'FERRAMENTA = {{"name": "{nome}", "description": "x"}}\n'
                    'def executar(args, jarvis):\n    return "enviada"\n', encoding="utf-8")
            try:
                with patch.object(core.automacoes, "pasta_padrao", return_value=Path(pasta)):
                    carga = main.carregar_automacoes(recarregar=True)
                    oferecidas = {d["name"] for d in main.get_tool_declarations()}
            finally:
                main._AUTOMACOES = guardadas
        self.assertEqual(carga.ferramentas, {})
        self.assertEqual(sorted(a for a, _ in carga.erros), sorted(f"{nome}.py" for nome in DESLIGADAS))
        self.assertTrue(all("já existe no Jarvis" in erro for _, erro in carga.erros))
        self.assertEqual(oferecidas & set(DESLIGADAS), set())

    def test_reserva_nao_manda_mensagem(self):
        # o Groq e a outra empresa (core/reserva_outra.py usa as mesmas INSTRUCOES) têm o browser_control,
        # que digita e aperta Enter: o texto delas não pode dar a entender que, com um "ok", podem enviar
        from core.reserva_groq import INSTRUCOES

        self.assertNotIn("envie mensagens", INSTRUCOES)
        self.assertIn("Você não envia, não lê nem responde mensagens", INSTRUCOES)
        self.assertIn("não tente pelo navegador nem digitando", INSTRUCOES)
        self.assertIn("modo reserva (Groq)", INSTRUCOES)  # o core/reserva_outra.py troca o nome por aqui

    def test_digitar_pelo_computer_settings_continua_sem_ok_e_esta_no_mapa(self):
        # o computer_control saiu, mas o computer_settings continua oferecido ao Gemini e, pelo _execute_tool
        # de verdade, escreve na janela da frente e aperta qualquer tecla (Enter inclusive), sem o "ok" do
        # core/aprovacao.py e sem conferir o campo de texto. Enquanto for assim, o mapa das travas tem de
        # contar essa porta; quem a fechar atualiza o core/SEGURANCA.md e este teste no mesmo commit
        import actions.computer_settings as cs
        import main

        self.assertIn("computer_settings", {d["name"] for d in main.get_tool_declarations()})
        jarvis = object.__new__(main.JarvisLive)
        jarvis.ui = jarvis.client = UIFalsa()
        jarvis.cloud_safe = False
        jarvis.speak_error = Mock()
        teclado = Mock()
        respostas = []
        with patch.dict(os.environ, {"JARVIS_CEREBRO": "gemini", "JARVIS_QA_MODE": "0"}), \
                patch.object(cs, "_PYAUTOGUI", True), patch.object(cs, "pyautogui", teclado, create=True), \
                patch.object(cs, "_PYPERCLIP", False):
            for args in ({"action": "type_text", "value": "oi Ana", "press_enter": "true"},
                         {"action": "press_key", "value": "enter"}):
                chamada = NS(id="1", name="computer_settings", args=args)
                respostas.append(asyncio.run(jarvis._execute_tool(chamada)).response["result"])
        self.assertEqual(respostas, ["Typed: oi Ana", "Pressed: enter"])
        teclado.write.assert_called_once_with("oi Ana", interval=0.03)
        self.assertEqual([c.args for c in teclado.press.call_args_list], [("enter",), ("enter",)])
        mapa = (RAIZ / "core" / "SEGURANCA.md").read_text(encoding="utf-8")
        secao = mapa[mapa.index("## 1."):mapa.index("## 2.")]
        pendencias = [re.sub(r"\s+", " ", trecho) for trecho in secao.split("\n\n")
                      if trecho.startswith("**Pendência") and "`computer_settings`" in trecho]
        self.assertEqual(len(pendencias), 1, "o core/SEGURANCA.md não conta que o computer_settings digita sem o ok")
        for nome in ("`type_text`", "`press_enter`", "`press_key`", "`core/aprovacao.py`", "`core/prompt.txt`"):
            self.assertIn(nome, pendencias[0])

    def test_prompt_nao_promete_conferir_o_campo_de_texto(self):
        # quem conferia se a janela da frente era um campo de texto (actions/safe_text_entry.py) e recusava
        # era o computer_control e as mensagens, desligados; o computer_settings digita onde estiver o
        # cursor. O prompt não pode prometer ao Gemini uma conferência (e uma recusa) que nenhuma ferramenta
        # ligada faz, e a regra de digitar tem de continuar fechada
        import main

        prompt = (RAIZ / "core" / "prompt.txt").read_text(encoding="utf-8")
        ligadas = {d["name"] for d in main.get_tool_declarations()}
        conferem = {arquivo.stem for arquivo in (RAIZ / "actions").glob("*.py")
                    if re.search(r"^from actions\.safe_text_entry import", arquivo.read_text(encoding="utf-8"), re.M)}
        self.assertEqual(conferem & ligadas, set())
        self.assertNotIn("verified text field", prompt)
        self.assertNotIn("if the tool refuses, tell the user", prompt)
        regra = next(linha for linha in prompt.splitlines() if linha.startswith("Typing safety:"))
        for trecho in ("computer_settings", "only when the user explicitly asks", "never in a chat or messaging app",
                       "Enter", "never work around it with key presses, paste, or another typing tool"):
            self.assertIn(trecho, regra)


if __name__ == "__main__":
    if "--gravar-fotos" in sys.argv:
        gravar_fotos()
        print(f"Fotos regravadas: {FOTO_DECLARACOES.name} e {FOTO_POLITICAS.name}. Confira no git diff.")
    else:
        unittest.main()
