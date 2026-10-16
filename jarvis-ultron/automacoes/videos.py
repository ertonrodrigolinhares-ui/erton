"""Vídeos com IA (Google Veo) — Jarvis Ultron (automação: salve na pasta 'automacoes' e reabra o Jarvis).

Diga, por exemplo:
  - "Jarvis, faz um vídeo de 8 segundos de um triatleta cruzando a linha de chegada no Havaí."
  - "Jarvis, faz um vídeo vertical para o Instagram de uma corrida na praia ao amanhecer."

Como funciona (sempre com o seu "ok", porque cada vídeo é COBRADO pelo Google):
  1. O Jarvis diz quanto o vídeo deve custar e espera você aprovar ("ok", "pode fazer").
  2. Com o ok, o vídeo é gerado em segundo plano (1 a alguns minutos) — dá para continuar conversando.
  3. Pronto: ele salva em Documentos/Jarvis Ultron/Videos, abre o vídeo e avisa.

Precisa da chave do Gemini com faturamento ativado no Google (o Veo não tem uso grátis).
Qualidade: "economico" (Veo Lite, 720p), "rapido" (Veo Fast, padrão) ou "maximo" (Veo completo).
O preço mostrado é uma estimativa; o valor certo é o da conta do Google Cloud.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

FERRAMENTA = {
    "name": "generate_video",
    "description": (
        "Creates a short AI video (Google Veo) from a description. It COSTS MONEY, so it works in two calls: "
        "first call with confirm=false returns the estimated price — tell the user the price in Portuguese and "
        "ask for an explicit ok. Only after the user clearly approves in their own words, call again with "
        "confirm=true (same description). The video is made in the background; tell the user you will warn "
        "when it is ready. Never call with confirm=true without the user's explicit approval."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "description": {"type": "STRING", "description": "Detailed scene description, in English"},
            "seconds": {"type": "INTEGER", "description": "Length in seconds: 4, 6 or 8 (default 8)"},
            "quality": {"type": "STRING", "description": "economico | rapido | maximo (default rapido)"},
            "vertical": {"type": "BOOLEAN", "description": "true for 9:16 (Instagram/Reels/Stories)"},
            "confirm": {"type": "BOOLEAN", "description": "true ONLY after the user approved the price"},
        },
        "required": ["description"],
    },
}

# US$ por segundo (estimativa de tabelas públicas de 2026; o valor real é o da conta do Google)
PRECO_POR_SEGUNDO = {"economico": 0.05, "rapido": 0.12, "maximo": 0.40}
CONHECIDOS = {  # caso a lista de modelos não venha (o Jarvis prefere o que a conta mostrar)
    "economico": ["veo-3.1-lite-generate-preview", "veo-3.1-fast-generate-preview", "veo-3.1-fast-generate-001"],
    "rapido": ["veo-3.1-fast-generate-preview", "veo-3.1-fast-generate-001", "veo-3.0-fast-generate-001"],
    "maximo": ["veo-3.1-generate-preview", "veo-3.1-generate-001", "veo-3.0-generate-001"],
}
VALIDADE_PEDIDO = 10 * 60  # segundos que o preço informado vale para o "ok"
ESPERA_MAXIMA = 15 * 60    # desiste se o Google não terminar em 15 minutos

_pendente: dict = {}
_trava = threading.Lock()


def pasta_videos() -> Path:
    return Path.home() / "Documents" / "Jarvis Ultron" / "Videos"


def _qualidade(valor) -> str:
    valor = str(valor or "rapido").strip().lower()
    return valor if valor in PRECO_POR_SEGUNDO else "rapido"


def _segundos(valor) -> int:
    try:
        s = int(valor or 8)
    except (TypeError, ValueError):
        s = 8
    return min((4, 6, 8), key=lambda opcao: abs(opcao - s))


def estimar(segundos: int, qualidade: str) -> tuple[float, float]:
    """(dólares, reais) aproximados."""
    dolares = PRECO_POR_SEGUNDO[qualidade] * segundos
    cambio = float(os.environ.get("JARVIS_DOLAR", "5.4") or 5.4)
    return dolares, dolares * cambio


def escolher_modelo(cliente, qualidade: str) -> list[str]:
    """Modelos Veo a tentar, do que a conta mostrar (mais novo primeiro), depois os conhecidos."""
    achados = []
    try:
        for m in cliente.models.list(config={"page_size": 200}):
            nome = str(getattr(m, "name", "") or "").split("/")[-1]
            if nome.startswith("veo"):
                achados.append(nome)
    except Exception:
        pass

    def combina(nome: str) -> bool:
        if qualidade == "economico":
            return "lite" in nome
        if qualidade == "rapido":
            return "fast" in nome
        return "lite" not in nome and "fast" not in nome

    proprios = sorted((n for n in achados if combina(n)), reverse=True)
    return list(dict.fromkeys(proprios + CONHECIDOS[qualidade]))


def _abrir(arquivo: Path) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(str(arquivo))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(arquivo)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as erro:
        print(f"[Vídeos] Não consegui abrir o vídeo: {erro}")


def gerar(descricao: str, segundos: int, qualidade: str, vertical: bool, cliente=None,
          dormir=time.sleep, agora=time.monotonic) -> Path:
    """Faz o vídeo de verdade (bloqueia; roda em segundo plano). Devolve o arquivo .mp4."""
    from google.genai import types

    if cliente is None:
        from google import genai

        from core.gemini_acesso import opcoes_http
        from core.modelos import _chave

        cliente = genai.Client(api_key=_chave(), http_options=opcoes_http())
    config = types.GenerateVideosConfig(
        number_of_videos=1, duration_seconds=segundos,
        aspect_ratio="9:16" if vertical else "16:9",
        resolution="720p" if qualidade == "economico" else "1080p",
    )
    ultimo = None
    for modelo in escolher_modelo(cliente, qualidade)[:4]:
        try:
            operacao = cliente.models.generate_videos(
                model=modelo, source=types.GenerateVideosSource(prompt=descricao), config=config)
        except Exception as erro:
            ultimo = erro
            if "404" in str(erro) or "not found" in str(erro).lower():
                continue  # este modelo não existe na conta: tenta o próximo
            raise
        inicio = agora()
        while not operacao.done:
            if agora() - inicio > ESPERA_MAXIMA:
                raise TimeoutError("o Google não terminou o vídeo em 15 minutos")
            dormir(10)
            operacao = cliente.operations.get(operacao)
        if getattr(operacao, "error", None):
            raise RuntimeError(str(operacao.error)[:200])
        videos = getattr(getattr(operacao, "result", None) or getattr(operacao, "response", None),
                         "generated_videos", None) or []
        if not videos:
            raise RuntimeError("o Google não devolveu o vídeo (pode ter recusado a descrição)")
        video = videos[0].video
        if getattr(video, "uri", None) and not getattr(video, "video_bytes", None):
            cliente.files.download(file=video)  # caminho normal (AI Studio): baixa o arquivo
        pasta_videos().mkdir(parents=True, exist_ok=True)
        arquivo = pasta_videos() / f"video-{datetime.now():%Y%m%d-%H%M%S}.mp4"
        video.save(str(arquivo))
        return arquivo
    raise RuntimeError(f"nenhum modelo de vídeo disponível na sua conta ({ultimo})")


def _explicar(erro: Exception) -> str:
    texto = str(erro).lower()
    if "billing" in texto or "faturamento" in texto:
        return "o Google pede faturamento ativado para vídeos (Google Cloud > Faturamento)"
    if "safety" in texto or "recus" in texto or "blocked" in texto:
        return "o Google recusou a descrição (regras de conteúdo); tente descrever de outro jeito"
    if "resource_exhausted" in texto or "429" in texto or "quota" in texto:
        return "a cota de vídeos acabou por agora; tente mais tarde"
    return str(erro)[:160]


def executar(args: dict, jarvis) -> str:
    descricao = str(args.get("description", "")).strip()
    if not descricao:
        return "Faltou a descrição do vídeo."
    segundos = _segundos(args.get("seconds"))
    qualidade = _qualidade(args.get("quality"))
    vertical = bool(args.get("vertical"))
    dolares, reais = estimar(segundos, qualidade)
    chave = (descricao.lower(), segundos, qualidade, vertical)
    fala = str(getattr(jarvis, "_current_input_transcript", "") or getattr(jarvis, "_last_input_transcript", "") or "")

    if not args.get("confirm"):
        with _trava:
            _pendente.clear()
            _pendente.update(chave=chave, em=time.monotonic(), fala=fala.strip().lower())
        return (f"Estimated price: about US$ {dolares:.2f} (about R$ {reais:.2f}) for a {segundos}-second "
                f"{'vertical ' if vertical else ''}video ({qualidade}). Tell the user this price in Portuguese "
                "and ask for an explicit ok before making it.")

    # Confirmado: só vale se o próprio Erton aprovou este mesmo pedido, em palavras dele, numa fala
    # DEPOIS de ouvir o preço (um "pode fazer" dito junto com o pedido não conta).
    from core.hermes_ponte import usuario_aprovou

    with _trava:
        pedido_ok = (_pendente.get("chave") == chave
                     and time.monotonic() - _pendente.get("em", 0) < VALIDADE_PEDIDO)
        aprovado = pedido_ok and fala.strip().lower() != _pendente.get("fala") and usuario_aprovou(fala)
        if aprovado:
            _pendente.clear()
    if not pedido_ok:
        return ("Not confirmed: first call with confirm=false to show the price for exactly this video, "
                "then ask the user for an ok.")
    if not aprovado:
        return "Not confirmed: the user did not clearly approve. Ask for an explicit ok (for example 'ok, pode fazer')."

    ui = getattr(jarvis, "ui", None)

    def trabalhar():
        try:
            arquivo = gerar(descricao, segundos, qualidade, vertical)
        except Exception as erro:
            aviso = f"Não consegui fazer o vídeo: {_explicar(erro)}."
        else:
            _abrir(arquivo)
            aviso = f"O vídeo ficou pronto e já abri para você. Está salvo em {arquivo.parent}."
        anunciar = getattr(jarvis, "anunciar", None)
        if callable(anunciar):  # respeita o modo chamada: guarda o aviso até o "Hey Jarvis"
            anunciar(aviso, "Vídeo")
            return
        if ui is not None:
            ui.write_log(f"SYS: 🎬 {aviso}")
        falar = getattr(jarvis, "_falar_aviso", None)
        if callable(falar):
            falar(aviso)

    threading.Thread(target=trabalhar, daemon=True, name="VideoVeo").start()
    if ui is not None:
        ui.write_log(f"SYS: 🎬 Fazendo o vídeo ({segundos}s, {qualidade}, ~R$ {reais:.2f})...")
    return ("The video is being made in the background (1 to a few minutes). Tell the user, in one short "
            "Portuguese sentence, that you will warn when it is ready.")
