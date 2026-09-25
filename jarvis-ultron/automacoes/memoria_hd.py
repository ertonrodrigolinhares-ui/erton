"""Memória do Jarvis no HD externo (automação: salve na pasta 'automacoes' e reabra o Jarvis).

Tudo o que o Jarvis aprende é copiado para o seu HD externo:
  - a memória dele (o que ele sabe de você, respostas guardadas, histórico de tarefas);
  - lembretes, rotinas, bloco de notas, relatórios e imagens (Documentos/Jarvis Ultron);
  - o que os agentes do Hermes aprenderam (memórias e habilidades);
  - as suas automações (esta pasta).

Como ligar (uma vez):
  - diga "Jarvis, use o HD E como memória" (troque E pela letra do HD); ou
  - crie no HD uma pasta chamada exatamente:  Jarvis Ultron - Memoria

Depois é sozinho: com o HD ligado, ele copia ao abrir e a cada 30 minutos, e guarda uma cópia por
dia em "historico" (os últimos 30 dias). Nada é apagado do HD.
Por segurança, NUNCA copia chaves e senhas (.env, api_keys.json, auth.json, tokens).

Por voz: "Jarvis, salve sua memória no HD agora" · "Jarvis, como está a memória do HD?"
         "Jarvis, recupere sua memória do HD" (só com a sua confirmação; guarda a atual antes).
"""

from __future__ import annotations

import fnmatch
import json
import os
import shutil
import string
import threading
import time
import uuid
from datetime import date, datetime
from pathlib import Path

FERRAMENTA = {
    "name": "external_memory_drive",
    "description": (
        "JARVIS's memory backup on the user's external hard drive (HD externo). setup: use drive letter "
        "(e.g. 'E') as memory drive. save_now: copy everything JARVIS learned to the drive now. status: say "
        "where/when it was last saved. restore: bring the memory back from the drive — ONLY after the user "
        "explicitly confirms; pass confirm=true then. Answer in Portuguese."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "setup | save_now | status | restore"},
            "drive": {"type": "STRING", "description": "Drive letter for setup, e.g. E"},
            "confirm": {"type": "BOOLEAN", "description": "restore only: true after the user confirmed"},
        },
        "required": ["action"],
    },
}

PASTA_NO_HD = "Jarvis Ultron - Memoria"
MARCADOR = ".jarvis-memoria"
COPIAR_A_CADA = 30 * 60  # segundos
PROCURAR_HD_A_CADA = 5 * 60
DIAS_DE_HISTORICO = 30
NUNCA_COPIAR = (".env", "*.env", ".env.*", "api_keys.json", "auth.json", "*token*", "*credential*",
                "*secret*", "*.key", "*.pem", "__pycache__", "*.pyc", "*.tmp", "*.lock")

_trava = threading.Lock()
_iniciado = threading.Event()


# ---------------------------------------------------------------- onde estão as coisas

def pasta_jarvis() -> Path:
    return Path(__file__).resolve().parent.parent


def pasta_documentos() -> Path:
    return Path.home() / "Documents" / "Jarvis Ultron"


def arquivo_config() -> Path:
    return pasta_documentos() / "memoria_hd.json"


def fontes() -> list[tuple[str, Path, list[str] | None]]:
    """(nome no HD, pasta, só estes itens ou None = tudo)."""
    lista = [
        ("memoria-jarvis", pasta_jarvis() / "memory", ["*.json", "*.md"]),
        ("documentos", pasta_documentos(), None),
        ("automacoes", pasta_jarvis() / "automacoes", None),
    ]
    hermes = os.environ.get("HERMES_JARVIS_HOME", "").strip()
    if hermes:
        for sub in ("memories", "skills", "jarvis"):
            lista.append((f"hermes/{sub}", Path(hermes) / sub, None))
    return lista


def _proibido(nome: str) -> bool:
    nome = nome.lower()
    return any(fnmatch.fnmatch(nome, padrao) for padrao in NUNCA_COPIAR)


# ---------------------------------------------------------------- configuração e HD

def ler_config(caminho: Path | None = None) -> dict:
    try:
        dados = json.loads((caminho or arquivo_config()).read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def gravar_config(dados: dict, caminho: Path | None = None) -> None:
    caminho = caminho or arquivo_config()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def raizes() -> list[Path]:
    """Discos que podem ser o HD (no Windows: D: até Z:). JARVIS_HD_MEMORIA no .env força um caminho."""
    forcado = os.environ.get("JARVIS_HD_MEMORIA", "").strip()
    if forcado:
        return [Path(forcado)]
    if os.name == "nt":
        return [Path(f"{letra}:\\") for letra in string.ascii_uppercase[3:] if os.path.exists(f"{letra}:\\")]
    return [p for base in (Path("/media"), Path("/mnt"), Path("/Volumes")) if base.is_dir()
            for p in base.iterdir() if p.is_dir()]


def achar_hd(config: dict | None = None, discos: list[Path] | None = None) -> Path | None:
    """A pasta da memória no HD, se o HD estiver ligado (procura pela marca, mesmo se a letra mudar)."""
    config = ler_config() if config is None else config
    marca = config.get("marca")
    sem_marca = None
    for raiz in (raizes() if discos is None else discos):
        pasta = raiz / PASTA_NO_HD
        try:
            if not pasta.is_dir():
                continue
            arquivo_marca = pasta / MARCADOR
            if arquivo_marca.exists():
                if marca and arquivo_marca.read_text(encoding="utf-8").strip() == marca:
                    return pasta
                continue  # memória de outro Jarvis/computador: não mistura
            sem_marca = sem_marca or pasta  # pasta criada à mão pelo usuário
        except OSError:
            continue
    return sem_marca


def preparar_hd(pasta: Path, config_caminho: Path | None = None) -> Path:
    config = ler_config(config_caminho)
    marca = config.get("marca") or uuid.uuid4().hex
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo_marca = pasta / MARCADOR
    if not arquivo_marca.exists():
        arquivo_marca.write_text(marca, encoding="utf-8")
        leia = pasta / "LEIA-ME.txt"
        leia.write_text("Memória do Jarvis Ultron.\n'atual' = cópia mais recente; 'historico' = uma cópia por "
                        "dia.\nNão apague o arquivo .jarvis-memoria (é como o Jarvis reconhece este HD).\n",
                        encoding="utf-8")
    config["marca"] = arquivo_marca.read_text(encoding="utf-8").strip()
    gravar_config(config, config_caminho)
    return pasta


# ---------------------------------------------------------------- cópia

def _copiar_pasta(origem: Path, destino: Path, filtros: list[str] | None) -> tuple[int, int]:
    """Copia o que é novo ou mudou. Devolve (copiados, total). Não apaga nada do destino."""
    copiados = total = 0
    if not origem.is_dir():
        return 0, 0
    for raiz, pastas, arquivos in os.walk(origem):
        pastas[:] = [p for p in pastas if not _proibido(p) and not p.startswith(".")]
        for nome in arquivos:
            if _proibido(nome) or (filtros and not any(fnmatch.fnmatch(nome.lower(), f) for f in filtros)):
                continue
            fonte = Path(raiz) / nome
            alvo = destino / fonte.relative_to(origem)
            total += 1
            try:
                info = fonte.stat()
                if alvo.exists():
                    antigo = alvo.stat()
                    if antigo.st_size == info.st_size and antigo.st_mtime >= info.st_mtime - 2:
                        continue
                alvo.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(fonte, alvo)
                copiados += 1
            except OSError as erro:
                print(f"[Memória HD] Não copiei {fonte.name}: {erro}")
    return copiados, total


def _historico(hd: Path, hoje: date) -> None:
    """Uma cópia por dia da memória (a parte pequena e mais importante); guarda 30 dias."""
    pasta_dia = hd / "historico" / hoje.isoformat()
    if not pasta_dia.exists():
        for nome in ("memoria-jarvis", "hermes/memories"):
            origem = hd / "atual" / nome
            if origem.is_dir():
                shutil.copytree(origem, pasta_dia / nome, dirs_exist_ok=True)
    dias = sorted(p for p in (hd / "historico").glob("????-??-??") if p.is_dir())
    for velho in dias[:-DIAS_DE_HISTORICO]:
        shutil.rmtree(velho, ignore_errors=True)


def salvar(hd: Path, agora: datetime | None = None, config_caminho: Path | None = None) -> tuple[int, int]:
    agora = agora or datetime.now()
    with _trava:
        copiados = total = 0
        for nome, origem, filtros in fontes():
            c, t = _copiar_pasta(origem, hd / "atual" / nome, filtros)
            copiados, total = copiados + c, total + t
        _historico(hd, agora.date())
        config = ler_config(config_caminho)
        config.update({"ultima_copia": agora.isoformat(timespec="minutes"), "ultimo_hd": str(hd.anchor or hd),
                       "arquivos": total})
        gravar_config(config, config_caminho)
    return copiados, total


def restaurar(hd: Path) -> int:
    """Traz de volta a memória do Jarvis e os documentos. A versão atual fica com '.antes-de-restaurar'."""
    trazidos = 0
    with _trava:
        for nome, destino, filtros in fontes():
            if nome.startswith("hermes") or nome == "automacoes":
                continue  # Hermes e automações: só manualmente
            origem = hd / "atual" / nome
            if not origem.is_dir():
                continue
            for fonte in origem.rglob("*"):
                if not fonte.is_file() or _proibido(fonte.name):
                    continue
                alvo = destino / fonte.relative_to(origem)
                alvo.parent.mkdir(parents=True, exist_ok=True)
                if alvo.exists():
                    shutil.copy2(alvo, alvo.with_name(alvo.name + ".antes-de-restaurar"))
                shutil.copy2(fonte, alvo)
                trazidos += 1
    return trazidos


# ---------------------------------------------------------------- por voz e sozinho

def _quando(texto: str) -> str:
    try:
        return datetime.fromisoformat(texto).strftime("%d/%m às %H:%M")
    except (TypeError, ValueError):
        return "nunca"


def executar(args: dict, jarvis) -> str:
    acao = str(args.get("action", "status") or "status").strip().lower()
    if acao == "setup":
        letra = str(args.get("drive", "")).strip().rstrip(":\\/").upper()
        if len(letra) != 1 or letra not in string.ascii_uppercase:
            return "Falta a letra do HD (ex.: E). Ask the user which letter the external drive has in 'Este Computador'."
        if letra == "C":
            return "O C: é o disco do próprio computador, não o HD externo. Ask for the external drive letter."
        raiz = Path(f"{letra}:\\")
        if not raiz.exists():
            return f"Não achei o disco {letra}:. Tell the user in Portuguese to plug in the HD and check the letter."
        hd = preparar_hd(raiz / PASTA_NO_HD)
        copiados, total = salvar(hd)
        return (f"HD {letra}: pronto como memória do Jarvis. Copiei {total} arquivos. A partir de agora salvo sozinho "
                "a cada 30 minutos quando ele estiver ligado. Tell the user in Portuguese.")
    hd = achar_hd()
    config = ler_config()
    if acao in ("save_now", "salvar", "save"):
        if hd is None:
            return ("O HD da memória não está conectado (ou ainda não foi escolhido). Tell the user in Portuguese to "
                    "plug it in, or say 'use o HD E como memória'.")
        preparar_hd(hd)
        copiados, total = salvar(hd)
        return f"Memória salva no HD: {copiados} arquivos novos ou alterados, {total} no total. Tell the user in Portuguese."
    if acao in ("restore", "restaurar"):
        if hd is None:
            return "O HD da memória não está conectado. Tell the user in Portuguese."
        if not args.get("confirm"):
            return ("Before restoring, ask the user to confirm (in Portuguese): the memory saved on the HD on "
                    f"{_quando(config.get('ultima_copia'))} will replace the current one (the current one is kept "
                    "as a backup). Then call again with confirm=true.")
        trazidos = restaurar(hd)
        return (f"Recuperei {trazidos} arquivos da memória do HD. Tell the user in Portuguese to close and reopen "
                "JARVIS so it loads the restored memory.")
    ligado = f"ligado ({hd.anchor or hd})" if hd else "desconectado"
    return (f"HD da memória: {ligado}. Última cópia: {_quando(config.get('ultima_copia'))}, "
            f"{config.get('arquivos', 0)} arquivos. Tell the user in Portuguese.")


def iniciar(jarvis) -> None:
    if _iniciado.is_set():
        return
    _iniciado.set()
    parar = getattr(jarvis, "_shutdown_requested", None) or threading.Event()

    def log(texto: str) -> None:
        try:
            jarvis.ui.write_log(f"SYS: {texto}")
        except Exception:
            print(f"[Memória HD] {texto}")

    def laco():
        parar.wait(60)  # deixa o Jarvis abrir primeiro
        ultima, avisou_ausente = 0.0, False
        while not parar.is_set():
            try:
                hd = achar_hd()
                if hd is None:
                    if not avisou_ausente and ler_config().get("marca"):
                        log("HD da memória desconectado: salvo quando ele for ligado.")
                    avisou_ausente = True
                elif time.monotonic() - ultima >= COPIAR_A_CADA or avisou_ausente:
                    preparar_hd(hd)
                    copiados, total = salvar(hd)
                    ultima, avisou_ausente = time.monotonic(), False
                    log(f"Memória salva no HD ({hd.anchor or hd}): {copiados} novos/alterados de {total}.")
            except Exception as erro:
                print(f"[Memória HD] {erro}")
            parar.wait(PROCURAR_HD_A_CADA)

    threading.Thread(target=laco, daemon=True, name="MemoriaHD").start()
