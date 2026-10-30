"""Vídeos com IA (Google Veo) — Jarvis Ultron (automação: salve na pasta 'automacoes' e reabra o Jarvis).

Diga, por exemplo:
  - "Jarvis, faz um vídeo de 8 segundos de um triatleta cruzando a linha de chegada no Havaí."
  - "Jarvis, faz um vídeo vertical para o Instagram de uma corrida na praia ao amanhecer."

Como funciona (sempre com o seu "ok", porque cada vídeo é COBRADO pelo Google):
  1. O Jarvis diz quanto o vídeo deve custar e espera você aprovar ("ok", "pode fazer").
  2. Com o ok, o vídeo é gerado em segundo plano (1 a alguns minutos) — dá para continuar conversando.
  3. Pronto: ele salva em Documentos/Jarvis Ultron/Videos, abre o vídeo e avisa.

Se o Jarvis fechar ou religar (ex.: "modo privado") no meio, o pedido fica anotado e o vídeo é buscado
quando ele abrir de novo no modo normal (o Google cobra o vídeo mesmo assim).

Precisa da chave do Gemini com faturamento ativado no Google (o Veo não tem uso grátis).
Qualidade: "economico" (Veo Lite, 720p), "rapido" (Veo Fast, padrão) ou "maximo" (Veo completo).
O Jarvis nunca troca para um modelo mais caro do que o do preço aprovado. 1080p só nos vídeos de
8 segundos (o Google não aceita 1080p com 4 ou 6 segundos); os mais curtos saem em 720p.
O preço mostrado é uma estimativa; o valor certo é o da conta do Google Cloud.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

USA_IA_NUVEM = True  # a descrição vai para o Veo (Google): desligada no modo privado

from core.frases import frase

AVISO_MODO_PRIVADO = frase("modo_privado_video")  # o texto fica no core/frases.py (Etapa 8)

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
    # só modelos da MESMA faixa de preço: o "ok" foi dado para o preço desta qualidade
    "economico": ["veo-3.1-lite-generate-preview"],
    "rapido": ["veo-3.1-fast-generate-preview", "veo-3.1-fast-generate-001", "veo-3.0-fast-generate-001"],
    "maximo": ["veo-3.1-generate-preview", "veo-3.1-generate-001", "veo-3.0-generate-001"],
}
VALIDADE_PEDIDO = 10 * 60  # segundos que o preço informado vale para o "ok"
ESPERA_MAXIMA = 15 * 60    # desiste se o Google não terminar em 15 minutos
ESPERA_AO_ABRIR = 8.0      # ao abrir, deixa a conversa começar antes de avisar do vídeo que ficou pela metade

_pendente: dict = {}
_trava = threading.Lock()
_trava_anotados = threading.Lock()


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
    try:  # aceita "5,40" (vírgula, do jeito brasileiro) além de "5.40"
        cambio = float(str(os.environ.get("JARVIS_DOLAR", "") or "5.4").strip().replace(",", "."))
    except ValueError:
        cambio = 5.4
    if not (cambio > 0 and math.isfinite(cambio)):
        cambio = 5.4
    return dolares, dolares * cambio


def _da_faixa(nome: str, qualidade: str) -> bool:
    """O modelo é da faixa de preço desta qualidade? (nunca usa um mais caro que o preço aprovado)"""
    if qualidade == "economico":
        return "lite" in nome
    if qualidade == "rapido":
        return "fast" in nome
    return "lite" not in nome and "fast" not in nome


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

    proprios = sorted((n for n in achados if _da_faixa(n, qualidade)), reverse=True)
    return [n for n in dict.fromkeys(proprios + CONHECIDOS[qualidade]) if _da_faixa(n, qualidade)]


def _resolucao(modelo: str, segundos: int, qualidade: str, vertical: bool) -> str:
    """1080p só com 8 segundos (o Google recusa 1080p com 4 ou 6 s); o Veo 3.0 só faz 1080p deitado."""
    if qualidade == "economico" or segundos != 8:
        return "720p"
    if modelo.startswith("veo-3.0") and vertical:
        return "720p"
    return "1080p"


def _abrir(arquivo: Path) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(str(arquivo))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(arquivo)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as erro:
        print(f"[Vídeos] Não consegui abrir o vídeo: {erro}")


def _cliente():
    from google import genai

    from core.gemini_acesso import opcoes_http
    from core.modelos import _chave

    return genai.Client(api_key=_chave(), http_options=opcoes_http())


def gerar(descricao: str, segundos: int, qualidade: str, vertical: bool, cliente=None,
          dormir=time.sleep, agora=time.monotonic) -> Path:
    """Faz o vídeo de verdade (bloqueia; roda em segundo plano). Devolve o arquivo .mp4."""
    from google.genai import types

    if cliente is None:
        cliente = _cliente()
    ultimo = None
    for modelo in escolher_modelo(cliente, qualidade)[:4]:
        config = types.GenerateVideosConfig(
            number_of_videos=1, duration_seconds=segundos,
            aspect_ratio="9:16" if vertical else "16:9",
            resolution=_resolucao(modelo, segundos, qualidade, vertical),
        )
        # Anotado no disco ANTES de pedir: se o Jarvis fechar ou religar no meio (ex.: "modo privado"),
        # este fio morre sem aviso; a anotação fica e o próximo cérebro busca o vídeo ou avisa (iniciar).
        anotado = _anotar()
        try:
            try:
                operacao = cliente.models.generate_videos(
                    model=modelo, source=types.GenerateVideosSource(prompt=descricao), config=config)
            except Exception as erro:
                ultimo = erro
                if "404" in str(erro) or "not found" in str(erro).lower():
                    continue  # este modelo não existe na conta: tenta o próximo
                raise
            _anotar(anotado, str(getattr(operacao, "name", "") or ""))
            return _terminar(cliente, operacao, dormir, agora)
        finally:  # terminou (pronto, erro ou anotado em pendentes.txt): tira a anotação
            _desanotar(anotado)
    if qualidade == "economico":  # nunca troca sozinho para um modelo mais caro que o preço aprovado
        raise RuntimeError("a sua conta não tem o modelo econômico (Veo Lite); se quiser, peça de novo na "
                           "qualidade rápida, que custa mais (eu digo o preço antes)")
    raise RuntimeError(f"nenhum modelo de vídeo disponível na sua conta ({ultimo})")


def _terminar(cliente, operacao, dormir, agora) -> Path:
    """Espera o Google terminar o vídeo já pedido e grava o .mp4."""
    # Daqui em diante o Google já está fazendo (e cobrando) o vídeo: uma falha de rede não pode
    # fazer perder o vídeo nem levar o Erton a pedir (e pagar) outro sem saber.
    try:
        pronta = _esperar(cliente, operacao, dormir, agora)
    except Exception as erro:
        raise _ja_pedido(operacao, erro) from erro
    if getattr(pronta, "error", None):
        raise RuntimeError(str(pronta.error)[:200])
    videos = getattr(getattr(pronta, "result", None) or getattr(pronta, "response", None),
                     "generated_videos", None) or []
    if not videos:
        raise RuntimeError("o Google não devolveu o vídeo (pode ter recusado a descrição)")
    try:
        return _salvar(cliente, videos[0].video, dormir)
    except Exception as erro:
        raise _ja_pedido(operacao, erro) from erro


# ----- vídeo que ficou pela metade (o Jarvis fechou ou religou o cérebro durante a espera)

def _arquivo_anotados() -> Path:
    return pasta_videos() / "em-andamento.json"


def _ler_anotados() -> list[dict]:
    try:
        dados = json.loads(_arquivo_anotados().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    pedidos = dados.get("pedidos") if isinstance(dados, dict) else None
    return [p for p in pedidos if isinstance(p, dict) and p.get("id")] if isinstance(pedidos, list) else []


def _gravar_anotados(pedidos: list[dict]) -> None:
    arquivo = _arquivo_anotados()
    if not pedidos:
        arquivo.unlink(missing_ok=True)
        return
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    temporario = arquivo.with_suffix(".tmp")
    temporario.write_text(json.dumps({"pedidos": pedidos}, ensure_ascii=False, indent=2), encoding="utf-8")
    temporario.replace(arquivo)


def _anotar(anotado: str | None = None, nome: str = "") -> str:
    """Anota (ou completa com o número do pedido do Google) um vídeo em andamento. Devolve o id."""
    anotado = anotado or uuid.uuid4().hex[:12]
    try:
        with _trava_anotados:
            pedidos = [p for p in _ler_anotados() if p["id"] != anotado]
            pedidos.append({"id": anotado, "nome": nome, "em": datetime.now().isoformat(timespec="seconds")})
            _gravar_anotados(pedidos)
    except OSError as erro:
        print(f"[Vídeos] Não consegui anotar o vídeo em andamento: {erro}")
    return anotado


def _desanotar(anotado: str) -> None:
    try:
        with _trava_anotados:
            pedidos = _ler_anotados()
            if any(p["id"] == anotado for p in pedidos):
                _gravar_anotados([p for p in pedidos if p["id"] != anotado])
    except OSError as erro:
        print(f"[Vídeos] Não consegui tirar a anotação do vídeo: {erro}")


def iniciar(jarvis) -> None:
    """Ao abrir: um vídeo pago ficou pela metade (o Jarvis fechou ou religou o cérebro no meio)?
    No modo normal, busca no Google e abre; no modo privado só avisa (não fala com o Google) e
    busca quando o Erton voltar ao modo normal."""
    pedidos = _ler_anotados()
    if pedidos:
        threading.Thread(target=_retomar, args=(jarvis, pedidos), daemon=True, name="VideoVeo").start()


def _retomar(jarvis, pedidos: list[dict], cliente=None, dormir=time.sleep, agora=time.monotonic) -> None:
    dormir(ESPERA_AO_ABRIR)
    privado, para_depois = _modo_privado(), 0
    for pedido in pedidos:
        nome = str(pedido.get("nome") or "")
        if not nome:  # fechou enquanto pedia: não dá para saber se o Google recebeu
            _para_pendentes("", "o Jarvis fechou enquanto pedia")
            _desanotar(pedido["id"])
            _avisar(jarvis, "Quando o Jarvis fechou, um vídeo pago estava sendo pedido ao Google e pode ter sido "
                            "cobrado. Antes de pedir outro, confira na conta do Google.")
            continue
        if privado:  # buscar seria falar com o Google: fica anotado para o modo normal
            para_depois += 1
            continue
        _log(jarvis, "SYS: 🎬 Buscando o vídeo pago que ficou pela metade quando o Jarvis fechou ou religou...")
        try:
            from google.genai import types

            arquivo = _terminar(cliente or _cliente(), types.GenerateVideosOperation(name=nome), dormir, agora)
        except Exception as erro:
            aviso = ("O vídeo pago que ficou pela metade quando o Jarvis fechou ou religou não chegou: "
                     f"{_explicar(erro)}.")
            if not isinstance(erro, VideoJaPedido):  # o VideoJaPedido já anotou e já fala da cobrança
                _para_pendentes(nome, type(erro).__name__)
                aviso += " Ele pode ter sido cobrado; anotei o número do pedido em pendentes.txt, na pasta de vídeos."
        else:
            _abrir(arquivo)
            aviso = ("O vídeo pago que ficou pela metade quando o Jarvis fechou ou religou ficou pronto e já abri "
                     f"para você. Está salvo em {arquivo.parent}.")
        _desanotar(pedido["id"])
        _avisar(jarvis, aviso)
    if para_depois:
        _avisar(jarvis, "Um vídeo pago ficou pela metade quando o Jarvis religou. No modo privado não falo com o "
                        "Google; busco o vídeo quando você voltar ao modo normal.")


def _log(jarvis, texto: str) -> None:
    ui = getattr(jarvis, "ui", None)
    if ui is not None:
        ui.write_log(texto)


def _avisar(jarvis, aviso: str) -> None:
    anunciar = getattr(jarvis, "anunciar", None)
    if callable(anunciar):  # respeita o modo chamada: guarda o aviso até o "Hey Jarvis"
        anunciar(aviso, "Vídeo")
        return
    _log(jarvis, f"SYS: 🎬 {aviso}")
    falar = getattr(jarvis, "_falar_aviso", None)
    if callable(falar):
        falar(aviso)


class VideoJaPedido(RuntimeError):
    """Falhou DEPOIS de o Google começar o vídeo (que pode ser cobrado mesmo assim)."""


def _passageiro(erro: Exception) -> bool:
    """Falha de rede ou do servidor que costuma passar sozinha (vale tentar de novo)."""
    if isinstance(erro, OSError):  # inclui ConnectionError e TimeoutError
        return True
    codigo = getattr(erro, "code", None)  # erros da API do Google trazem o código HTTP
    if isinstance(codigo, int):
        return codigo in (408, 429) or codigo >= 500
    try:
        import httpx

        return isinstance(erro, httpx.TransportError)
    except ImportError:
        return False


def _esperar(cliente, operacao, dormir, agora, tentativas_finais: int = 3):
    """Acompanha o vídeo até o Google terminar; falhas passageiras de rede não interrompem a espera."""
    inicio = agora()
    extras = 0  # tentativas depois do prazo
    while not operacao.done:
        vencido = agora() - inicio > ESPERA_MAXIMA
        if not vencido:
            dormir(10)
        # vencido: ainda dá uma última olhada (o PC pode ter dormido no meio da espera)
        try:
            operacao = cliente.operations.get(operacao)
        except Exception as erro:
            if not _passageiro(erro):
                raise
            if vencido:  # o PC pode ter acabado de acordar e o Wi-Fi ainda estar voltando: espera um pouco
                extras += 1
                if extras > tentativas_finais:
                    raise
                dormir(10 * extras)
            print(f"[Vídeos] Falha passageira ao acompanhar o vídeo ({type(erro).__name__}); tento de novo.")
            continue
        if vencido and not operacao.done:
            raise TimeoutError("o Google não terminou o vídeo em 15 minutos")
    return operacao


def _salvar(cliente, video, dormir, tentativas: int = 3) -> Path:
    """Baixa (se preciso) e grava o .mp4, tentando de novo se a rede ou o disco falhar por um instante."""
    pasta_videos().mkdir(parents=True, exist_ok=True)
    arquivo = pasta_videos() / f"video-{datetime.now():%Y%m%d-%H%M%S}.mp4"
    vez = 1
    while True:
        try:
            if getattr(video, "uri", None) and not getattr(video, "video_bytes", None):
                cliente.files.download(file=video)  # caminho normal (AI Studio): baixa o arquivo
            video.save(str(arquivo))
            return arquivo
        except Exception as erro:
            if vez >= tentativas or not _passageiro(erro):
                raise
            print(f"[Vídeos] Falha ao baixar/gravar o vídeo ({type(erro).__name__}); tento de novo.")
            dormir(5 * vez)
            vez += 1


def _ja_pedido(operacao, erro: Exception) -> VideoJaPedido:
    """Anota o pedido do Google (para conferir/baixar depois) e explica que pode ter sido cobrado."""
    nome = str(getattr(operacao, "name", "") or "")
    print(f"[Vídeos] O vídeo já tinha sido pedido ao Google e não chegou: {nome or 'sem número'} "
          f"({type(erro).__name__}).")
    _para_pendentes(nome, type(erro).__name__)
    if isinstance(erro, TimeoutError) or not _passageiro(erro):
        causa = _explicar(erro)[:100]
    else:
        causa = "a conexão com o Google falhou"
    return VideoJaPedido(
        f"{causa}. Atenção: o Google já estava fazendo este vídeo e pode cobrar por ele mesmo assim; antes "
        "de pedir outro, confira na conta do Google (anotei o número do pedido em pendentes.txt, na pasta "
        "de vídeos)")


def _para_pendentes(nome: str, motivo: str) -> None:
    """Anota em pendentes.txt um pedido ao Google que não chegou (para conferir/baixar depois)."""
    try:
        pasta_videos().mkdir(parents=True, exist_ok=True)
        with open(pasta_videos() / "pendentes.txt", "a", encoding="utf-8") as saida:
            saida.write(f"{datetime.now():%Y-%m-%d %H:%M}  {nome or 'sem número'}  ({motivo})\n")
    except OSError:
        pass


def _explicar(erro: Exception) -> str:
    if isinstance(erro, VideoJaPedido):  # o aviso de possível cobrança vai inteiro
        return str(erro)
    texto = str(erro).lower()
    if "billing" in texto or "faturamento" in texto:
        return "o Google pede faturamento ativado para vídeos (Google Cloud > Faturamento)"
    if "safety" in texto or "recus" in texto or "blocked" in texto:
        return "o Google recusou a descrição (regras de conteúdo); tente descrever de outro jeito"
    if "resource_exhausted" in texto or "429" in texto or "quota" in texto:
        return "a cota de vídeos acabou por agora; tente mais tarde"
    return str(erro)[:160]


def _modo_privado() -> bool:
    from core.cerebro_gemma import cerebro_gemma

    return cerebro_gemma()


def executar(args: dict, jarvis) -> str:
    descricao = str(args.get("description", "")).strip()
    if not descricao:
        return "Faltou a descrição do vídeo."
    if _modo_privado():  # antes do preço e do confirm=true: nada vai para o Google
        return AVISO_MODO_PRIVADO
    segundos = _segundos(args.get("seconds"))
    qualidade = _qualidade(args.get("quality"))
    vertical = bool(args.get("vertical"))
    dolares, reais = estimar(segundos, qualidade)
    chave = (descricao.lower(), segundos, qualidade, vertical)
    from core import aprovacao

    if not args.get("confirm"):
        with _trava:
            _pendente.clear()
            _pendente.update(chave=chave, em=time.monotonic(), marca=aprovacao.marca(jarvis))
        return (f"Estimated price: about US$ {dolares:.2f} (about R$ {reais:.2f}) for a {segundos}-second "
                f"{'vertical ' if vertical else ''}video ({qualidade}). Tell the user this price in Portuguese "
                "and ask for an explicit ok before making it.")

    # Confirmado: só vale se o próprio Erton aprovou este mesmo pedido, em palavras dele, numa fala
    # NOVA depois de ouvir o preço (um "pode fazer" dito junto com o pedido não conta, nem quando a
    # transcrição dele chega atrasada): core/aprovacao.py.
    with _trava:
        pedido_ok = (_pendente.get("chave") == chave
                     and time.monotonic() - _pendente.get("em", 0) < VALIDADE_PEDIDO)
        fala_do_ok = aprovacao.fala_que_aprovou(jarvis, _pendente.get("marca", 0)) if pedido_ok else 0
        preco_em = _pendente.get("em", 0)
        if fala_do_ok:
            _pendente.clear()
    if not pedido_ok:
        return ("Not confirmed: first call with confirm=false to show the price for exactly this video, "
                "then ask the user for an ok.")
    if not fala_do_ok:
        return "Not confirmed: the user did not clearly approve. Ask for an explicit ok (for example 'ok, pode fazer')."

    ui = getattr(jarvis, "ui", None)

    def trabalhar():
        # A ferramenta pode ter chegado com só o começo da resposta transcrito ("Ok," ... "pode
        # cancelar, tá caro"): antes de gastar, confere de novo com a fala inteira.
        if not aprovacao.ainda_aprovado(jarvis, fala_do_ok):
            with _trava:
                if not _pendente:  # o preço continua valendo para um "ok" claro numa fala nova
                    _pendente.update(chave=chave, em=preco_em, marca=aprovacao.marca(jarvis))
            aviso = ("Não fiz o vídeo: a sua resposta não foi um 'ok' claro, então nada foi cobrado. "
                     "Se quiser mesmo o vídeo, diga 'ok, pode fazer'.")
        else:
            try:
                if _modo_privado():  # o modo mudou entre o preço e o ok
                    raise RuntimeError("o modo privado foi ligado; nada foi mandado para o Google")
                arquivo = gerar(descricao, segundos, qualidade, vertical)
            except Exception as erro:
                aviso = f"Não consegui fazer o vídeo: {_explicar(erro)}."
            else:
                _abrir(arquivo)
                aviso = f"O vídeo ficou pronto e já abri para você. Está salvo em {arquivo.parent}."
        _avisar(jarvis, aviso)

    # o nome do fio avisa a troca de modo (main.py) de que um vídeo pago está em andamento
    threading.Thread(target=trabalhar, daemon=True, name="VideoVeo").start()
    if ui is not None:
        ui.write_log(f"SYS: 🎬 Fazendo o vídeo ({segundos}s, {qualidade}, ~R$ {reais:.2f})...")
    return ("The video is being made in the background (1 to a few minutes). Tell the user, in one short "
            "Portuguese sentence, that you will warn when it is ready.")
