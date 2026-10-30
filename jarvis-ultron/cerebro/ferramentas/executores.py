"""Os executores das ferramentas nativas do Jarvis (Etapa 14 da reorganização; a tabela nasceu na 13).

Cada ferramenta é uma função `async def _ex_<nome>(jarvis, args)` que faz exatamente o que o ramo
"elif name == ..." do _execute_tool fazia, inclusive o texto padrão. As ações (open_app, web_search_action...)
são carregadas só na hora de usar (_lazy_action) e lidas deste módulo na hora da chamada: os testes que as
trocam por falsas fazem patch em cerebro.ferramentas.executores.<ação>.

As travas do começo do _execute_tool (modo privado -> Jarvis pronto -> modo QA -> interceptar desligar ->
save_memory) ficam no main.py e não passam por aqui. O save_memory também fica lá (regra própria do modo privado).
Este módulo não lê o .env nem cria cliente do Gemini ao ser importado.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import threading
from pathlib import Path


def _lazy_action(module_name: str, attribute: str):
    """Keep desktop-only dependencies out of headless API process startup."""

    def invoke(*args, **kwargs):
        action = getattr(importlib.import_module(module_name), attribute)
        return action(*args, **kwargs)

    invoke.__name__ = attribute
    return invoke


# As ações das ferramentas nativas, carregadas só na hora de usar (as bibliotecas do PC não entram
# ao importar o cérebro).
file_processor = _lazy_action("actions.file_processor", "file_processor")
flight_finder = _lazy_action("actions.flight_finder", "flight_finder")
open_app = _lazy_action("actions.open_app", "open_app")
weather_action = _lazy_action("actions.weather_report", "weather_action")
email_control = _lazy_action("actions.email_control", "email_control")
reminder = _lazy_action("actions.reminder", "reminder")
computer_settings = _lazy_action("actions.computer_settings", "computer_settings")
screen_process = _lazy_action("actions.screen_processor", "screen_process")
youtube_video = _lazy_action("actions.youtube_video", "youtube_video")
media_control = _lazy_action("actions.media_control", "media_control")
desktop_control = _lazy_action("actions.desktop", "desktop_control")
browser_control = _lazy_action("actions.browser_control", "browser_control")
file_controller = _lazy_action("actions.file_controller", "file_controller")
web_search_action = _lazy_action("actions.web_search", "web_search")
request_presentation = _lazy_action("actions.presentation_maker", "request_presentation")
request_deep_research = _lazy_action("actions.deep_research", "request_deep_research")


async def _ex_weather_report(jarvis, args):
    r = await asyncio.to_thread(lambda: weather_action(parameters=args, player=jarvis.ui))
    return r or "Weather delivered."


async def _ex_web_search(jarvis, args):
    r = await asyncio.to_thread(lambda: web_search_action(parameters=args, player=jarvis.ui))
    return r or "Done."


async def _ex_browser_control(jarvis, args):
    r = await asyncio.to_thread(lambda: browser_control(parameters=args, player=jarvis.ui))
    return r or "Done."


async def _ex_media_control(jarvis, args):
    r = await asyncio.to_thread(lambda: media_control(parameters=args, response=None, player=jarvis.ui))
    return r or "Done."


async def _ex_youtube_video(jarvis, args):
    r = await asyncio.to_thread(lambda: youtube_video(parameters=args, response=None, player=jarvis.ui))
    return r or "Done."


async def _ex_open_app(jarvis, args):
    r = await asyncio.to_thread(lambda: open_app(parameters=args, response=None, player=jarvis.ui))
    return r or f"Opened {args.get('app_name')}."


async def _ex_computer_settings(jarvis, args):
    # desligar, reiniciar, digitar e apertar teclas só com o "ok" do Erton, conferido na ação
    # (core/aprovacao.py)
    r = await asyncio.to_thread(lambda: computer_settings(parameters=args, response=None, player=jarvis.ui,
                                                          jarvis=jarvis))
    return r or "Done."


async def _ex_desktop_control(jarvis, args):
    r = await asyncio.to_thread(lambda: desktop_control(parameters=args, player=jarvis.ui))
    return r or "Done."


async def _ex_file_controller(jarvis, args):
    if (
        args.get("action", "").lower() == "open"
        and not args.get("path")
        and not args.get("name")
    ):
        current_file = getattr(jarvis.ui, "current_file", None)
        if current_file:
            args["path"] = current_file
    r = await asyncio.to_thread(lambda: file_controller(parameters=args, player=jarvis.ui))
    return r or "Done."


async def _ex_graphics_quality(jarvis, args):
    quality = str(args.get("quality") or "").strip().lower()
    if quality not in {"low", "medium", "high"}:
        raise ValueError("Graphics quality must be low, medium, or high.")
    jarvis.ui.set_graphics_quality(quality)
    return f"JARVIS graphics quality changed to {quality}."


async def _ex_jarvis_ui_control(jarvis, args):
    action = str(args.get("action") or "").strip().lower()
    if action in ("change_theme", "open_command_center", "close_command_center"):
        # Jarvis Ultron (Etapa 7): na tela azul não há tema nem Command Center; antes o Jarvis
        # dizia que tinha feito e nada mudava na tela
        return ("This action no longer exists: the blue screen has a fixed color and no "
                "Command Center (nothing changed). Tell the user that in Portuguese.")
    if action == "change_graphics_quality":
        quality = str(args.get("graphics_quality") or "").strip().lower()
        if quality not in {"low", "medium", "high"}:
            raise ValueError(f"Unknown graphics quality: {quality or 'missing'}")
        jarvis.ui.set_graphics_quality(quality)
        return f"JARVIS graphics quality changed to {quality}."
    jarvis.ui.handle_ui_command(action)
    return f"JARVIS interface action completed: {action.replace('_', ' ')}."


async def _ex_email_control(jarvis, args):
    if args.get("action", "").lower() == "connect" and not args.get("credentials_path"):
        current_file = getattr(jarvis.ui, "current_file", None)
        if current_file and Path(str(current_file)).suffix.lower() == ".json":
            args["credentials_path"] = current_file
    r = await asyncio.to_thread(lambda: email_control(parameters=args, response=None, player=jarvis.ui, session_memory=None))
    return r or "Email action completed."


async def _ex_reminder(jarvis, args):
    r = await asyncio.to_thread(lambda: reminder(parameters=args, response=None, player=jarvis.ui))
    return r or "Reminder set."


async def _ex_listening_mode(jarvis, args):
    return jarvis._definir_modo_escuta(args.get("mode", ""))


async def _ex_hermes_agent(jarvis, args):
    return await jarvis._hermes_sem_travar(args.get("request", ""))


async def _ex_school_tasks(jarvis, args):
    return await jarvis._geekie_pendencias(bool(args.get("refresh", False)))


async def _ex_self_diagnosis(jarvis, args):
    return await asyncio.to_thread(jarvis._autodiagnostico, False)


async def _ex_approve_publication(jarvis, args):
    from core import hermes_ponte
    # o "ok" é conferido no código: numa fala NOVA do Erton depois da proposta (core/aprovacao.py)
    return await asyncio.to_thread(
        hermes_ponte.aprovar_e_executar,
        args.get("kind", ""), args.get("details", ""), jarvis, bool(args.get("confirm")),
    )


async def _ex_suspend_listening(jarvis, args):
    return jarvis._suspender(args.get("minutes", 10))


async def _ex_generate_image(jarvis, args):
    from core.modelos import gerar_imagem
    return await asyncio.to_thread(gerar_imagem, args.get("prompt", ""))


async def _ex_screen_process(jarvis, args):
    threading.Thread(
        target=screen_process,
        kwargs={"parameters": args, "response": None,
                "player": jarvis.ui, "session_memory": None,
                "speak": jarvis._speak_vision_result},
        daemon=True
    ).start()
    return "Vision module activated. Stay completely silent — vision module will speak directly."


async def _ex_file_processor(jarvis, args):
    if not args.get("file_path") and jarvis.ui.current_file:
        args["file_path"] = jarvis.ui.current_file
    r = await asyncio.to_thread(
        lambda: file_processor(parameters=args, player=jarvis.ui, speak=jarvis.speak)
    )
    return r or "Done."


async def _ex_deep_research(jarvis, args):
    r = request_deep_research(parameters=args, player=jarvis.ui, speak=jarvis.speak)
    return r or "Deep research preference requested."


async def _ex_create_presentation(jarvis, args):
    current_file = getattr(jarvis.ui, "current_file", None)
    supported_sources = {
        ".txt", ".md", ".rst", ".csv", ".json", ".jsonl", ".docx", ".pptx",
        ".pdf", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".webp",
        ".wav", ".mp3", ".m4a", ".mp4", ".mov", ".avi", ".webm",
    }
    if (
        not args.get("source_file")
        and not args.get("source_files")
        and current_file
        and Path(str(current_file)).suffix.lower() in supported_sources
    ):
        args["source_files"] = [current_file]
    r = request_presentation(parameters=args, player=jarvis.ui, speak=jarvis.speak)
    return r or "Presentation preference requested."


async def _ex_task_status(jarvis, args):
    from agent.task_queue import get_queue

    queue = get_queue()
    action = str(args.get("action") or "get").lower()
    task_id = str(args.get("task_id") or "").strip()
    if action == "all" or not task_id:
        return json.dumps(queue.get_all_statuses(), ensure_ascii=False)
    if action == "cancel":
        return f"Task {task_id} cancelled." if queue.cancel(task_id) else f"Task {task_id} could not be cancelled."
    status = queue.get_status(task_id)
    return json.dumps(status, ensure_ascii=False) if status else f"Task {task_id} was not found."


async def _ex_flight_finder(jarvis, args):
    r = await asyncio.to_thread(lambda: flight_finder(parameters=args, player=jarvis.ui))
    return r or "Done."


EXECUTORES = {
    # grupo 6: herdadas que ainda existem (a Etapa 18 decide, com o Erton)
    "flight_finder": _ex_flight_finder,
    # grupo 5: visão, arquivos e tarefas
    "screen_process": _ex_screen_process,
    "file_processor": _ex_file_processor,
    "deep_research": _ex_deep_research,
    "create_presentation": _ex_create_presentation,
    "task_status": _ex_task_status,
    # grupo 4: o Jarvis por dentro
    "listening_mode": _ex_listening_mode,
    "hermes_agent": _ex_hermes_agent,
    "school_tasks": _ex_school_tasks,
    "self_diagnosis": _ex_self_diagnosis,
    "approve_publication": _ex_approve_publication,
    "suspend_listening": _ex_suspend_listening,
    "generate_image": _ex_generate_image,
    # grupo 3: e-mail e lembrete
    "email_control": _ex_email_control,
    "reminder": _ex_reminder,
    # grupo 2: o sistema e a própria tela
    "open_app": _ex_open_app,
    "computer_settings": _ex_computer_settings,
    "desktop_control": _ex_desktop_control,
    "file_controller": _ex_file_controller,
    "graphics_quality": _ex_graphics_quality,
    "jarvis_ui_control": _ex_jarvis_ui_control,
    # grupo 1: internet e mídia
    "weather_report": _ex_weather_report,
    "web_search": _ex_web_search,
    "browser_control": _ex_browser_control,
    "media_control": _ex_media_control,
    "youtube_video": _ex_youtube_video,
}
