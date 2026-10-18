"""Claude Code no PC do Erton como "chefe de tarefas" do Jarvis Ultron.

O Gemini (ou o Gemma) continua sendo a VOZ do Jarvis. Quando o pedido é grande — pesquisar a fundo,
analisar documentos, preparar relatórios, seguir um dos agentes, ou mudar o próprio código do
Jarvis — o Jarvis entrega para o Claude Code (o programa 'claude' instalado pelo "Instalar Claude"),
que usa a assinatura do Erton (Pro/Max), sem chave de API.

Travas (no código, não só nas instruções):
- Tarefas: o Claude só lê as pastas dele (Documentos/Jarvis Ultron, menos lembretes e rotinas),
  pesquisa na internet e escreve DENTRO de Documentos/Jarvis Ultron/Claude. Não roda comandos no PC
  e não usa conectores (Gmail, Metricool, Agenda...: ele abre sem nenhum servidor MCP), então não
  consegue publicar, enviar, comprar nem apagar nada.
- Código do Jarvis: primeiro o Claude só faz o PLANO (sem permissão para editar). O Jarvis conta o
  plano e só continua com o "ok" do Erton, conferido aqui, numa fala nova depois do plano. Antes de
  mexer: backup .zip e testes; depois: confere a sintaxe e roda os testes de novo. Se algo quebrar,
  o Jarvis desfaz sozinho, arquivo por arquivo. Se o Jarvis fechar ou cair no meio, o Claude morre
  junto e a próxima abertura desfaz a mudança que ficou pela metade (anotada em Backups).
- Modo privado (Gemma): nada vai para o Claude, porque ele roda na nuvem da Anthropic.
- A chave ANTHROPIC_API_KEY é tirada do ambiente: com ela o Claude cobraria pela API em vez de usar
  a assinatura. As chaves do Jarvis (Gemini, Groq...) também não vão para o Claude.

Ajustes no .env (opcionais): JARVIS_CLAUDE_EXE (caminho do claude.exe), JARVIS_CLAUDE_MODELO.
"""

from __future__ import annotations

import errno
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import site
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import zipfile
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path, PurePosixPath

TEMPO_TAREFA = 20 * 60    # uma tarefa do Claude pode levar alguns minutos
TEMPO_TESTES = 10 * 60
VALIDADE_PLANO = 15 * 60  # o "ok" vale para o plano contado nos últimos 15 minutos
MAX_TURNOS = 40
LIMITE_BACKUP = 5 * 1024 * 1024  # arquivos maiores não vão para o backup .zip

# Nunca disponíveis para o Claude chamado pelo Jarvis: comandos no PC (um script escreveria fora
# das pastas liberadas). Os conectores (Gmail, Metricool... poderiam enviar ou publicar) ficam de
# fora porque o Claude abre sem nenhum servidor MCP (--strict-mcp-config); "mcp__*" é só reforço.
PROIBIDAS = ("Bash", "PowerShell", "NotebookEdit", "mcp__*")
# Sem "Read"/"Glob"/"Grep" soltos (valeriam para o PC inteiro, até as senhas do Hermes): ler arquivos
# só nas pastas de cada modo, com Read(<pasta>/**) (veja _ler).
LEITURA = ("WebSearch", "WebFetch", "Skill")
SEGREDOS_PREFIXOS = ("GEMINI_", "GROQ_", "ELEVENLABS_", "HERMES_", "OPENAI_", "GOOGLE_GENAI_",
                     "JARVIS_PONTE_", "TELEGRAM_", "METRICOOL_")
SEGREDOS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "GOOGLE_API_KEY")

# O que o Claude nunca lê nem muda na pasta do Jarvis (chaves e memória do Erton)
PROTEGIDOS = (".env", ".env.*", "config/api_keys.json", "config/ui_settings.json", "memory/**", ".git/**",
              ".github/**", ".claude/**", ".mcp.json")
# Também nunca, mas só na pasta do programa (não existem na pasta de trabalho do Claude): as
# credenciais do Gmail (o email_control procura em config/) e os tokens, que o .gitignore já tira.
CREDENCIAIS_DO_PROGRAMA = ("**/credentials.json", "**/gmail_credentials.json", "**/client_secret_*.json",
                           "**/token.json")
# Em Documentos/Jarvis Ultron, o que o Claude das tarefas não lê: lembretes e rotinas podem ter sido
# ditos no modo privado, e esses nunca vão para a nuvem.
DADOS_PRIVADOS = ("lembretes.json", "rotinas.json")
# Fora da pasta do Jarvis (em ~): logins e senhas. AppData guarda as do Hermes no Windows.
CREDENCIAIS = (".claude/.credentials.json", ".ssh/**", ".aws/**", ".hermes/**", ".jarvis/**", "AppData/**")
# O Claude pode ler, mas nunca mudar: as travas dele e o que desfaz uma mudança interrompida.
TRAVAS = ("core/claude_chefe.py",)
PASTAS_FORA = {".git", "__pycache__", ".venv", "venv", "env", "ENV", "node_modules", ".pytest_cache",
               ".mypy_cache", ".ruff_cache", "tmp", "outputs", "memory", "build", "dist", ".qa-artifacts"}
ARQUIVOS_FORA = {".env", "api_keys.json", "ui_settings.json"}

REGRAS = """Você é o "chefe de tarefas" do Jarvis Ultron, o assistente de voz do Erton Rodrigo Linhares Coelho
(contador e administrador, CRA/PB 4473 | CRC/PB 6689; lidera a Linhares Prudêncio Contabilidade e Gestão
Empresarial; atleta de triathlon, Ironman 70.3 Hawaii). Escreva sempre em português do Brasil.

Regras:
- Nunca publique, envie mensagens ou e-mails, compre, agende ou apague nada. Prepare rascunhos e diga
  o que precisa do "ok" do Erton.
- Nunca tente invadir, escanear ou acessar sistemas, redes, sites ou arquivos de terceiros.
- Dados de clientes são sigilosos: use só o necessário para a tarefa e nunca os coloque em sites.
- Não invente: quando não souber ou não achar, diga. Cite as fontes (links) das pesquisas.
- A PRIMEIRA linha da sua resposta final deve ser "FALA: " seguida de um resumo de no máximo 2 frases
  curtas, para ser falado em voz alta (sem markdown). Depois, o conteúdo completo em markdown."""

REGRAS_TAREFA = """
Pasta de trabalho: {pasta}. Arquivos que você criar devem ficar aqui (relatórios em "Relatorios").
O Erton deixa arquivos para você analisar em "Entrada". Você também pode LER (sem alterar) os arquivos
de {dados} (por exemplo clientes.txt, carteira.txt, a pasta Faturas).
Especialistas extras: a pasta "Agency" tem centenas de agentes prontos (finanças, vendas, marketing,
gestão, jurídico, pesquisa...). Quando o pedido ganhar com um especialista, leia "Agency/INDICE.md"
(a lista das áreas), depois o INDICE.md da área que serve, escolha o agente certo e siga o arquivo
dele. Eles estão em inglês e são de outros países: responda em português, use as leis e impostos do
Brasil, e as regras acima valem mais que as deles. A pasta "Agency" é só para ler."""

REGRAS_PLANO = """
TAREFA: planejar uma mudança no código do próprio Jarvis Ultron (pasta atual). NÃO altere nada agora:
leia o código e escreva o PLANO: o que vai mudar, em quais arquivos, os riscos, e como testar.
Na linha "FALA:" resuma o plano em 2 frases simples (o Erton não é programador) e termine perguntando
se ele aprova. Não mexa em .env, chaves, memória nem na pasta .git. Você não pode mudar a .venv, pastas
que começam com ponto, tmp/outputs/build/dist nem core/claude_chefe.py (as suas travas): se o pedido
precisar disso, diga no plano que não dá."""

REGRAS_APLICAR = """
O Erton APROVOU o plano abaixo. Aplique exatamente esse plano, com mudanças pequenas e cuidadosas,
no estilo do código ao redor. Não rode comandos (não estão liberados): o Jarvis faz o backup, roda os
testes e desfaz tudo sozinho se algo quebrar. Não mexa em .env, chaves, memória nem na pasta .git.
Na linha "FALA:" diga em 1 ou 2 frases o que você mudou.

PLANO APROVADO:
{plano}"""


@dataclass
class Resposta:
    ok: bool
    texto: str = ""
    sessao: str | None = None
    erro: str = ""                      # explicação em português quando ok=False
    negadas: list = field(default_factory=list)

    @property
    def fala(self) -> str:
        return separar_fala(self.texto)[0]


# ---------------- onde estão as coisas ----------------
def pasta_dados() -> Path:
    """Documentos/Jarvis Ultron: o Claude pode LER daqui (clientes.txt, Faturas, carteira.txt...)."""
    return Path.home() / "Documents" / "Jarvis Ultron"


def pasta_trabalho() -> Path:
    return pasta_dados() / "Claude"


def pasta_backups() -> Path:
    return pasta_dados() / "Backups"


def pasta_jarvis() -> Path:
    return Path(__file__).resolve().parents[1]


_LETRAS_DO_ENV = str.maketrans({"\a": "\\a", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t",
                                "\v": "\\v"})


def _sem_ps1(caminho: str) -> str | None:
    """O Windows não abre um .ps1 como programa (WinError 193). O Claude instalado pelo npm tem um
    claude.ps1 e, ao lado, um claude.cmd: vale o .cmd. Sem ele, None."""
    if Path(caminho).suffix.lower() != ".ps1":
        return caminho
    irmao = Path(caminho).with_suffix(".cmd")
    return str(irmao) if irmao.is_file() else None


def achar_claude() -> str | None:
    """O claude.exe do instalador oficial; senão o do PATH (menos o Claude Desktop da Microsoft Store,
    que também se chama Claude.exe e abre a janela do app em vez do Claude Code)."""
    # o "Instalar Claude" antigo gravava o caminho sem dobrar a barra, e o .env lido virava "\b" em
    # outra letra (C:\...\.local\bin): aqui ela volta a ser barra
    escolhido = os.environ.get("JARVIS_CLAUDE_EXE", "").translate(_LETRAS_DO_ENV).strip().strip('"')
    # (o "Instalar Claude" antigo também podia gravar o claude.ps1 do npm, que o Windows não abre)
    if escolhido and Path(escolhido).is_file() and (programa := _sem_ps1(escolhido)):
        return programa
    oficial = Path.home() / ".local" / "bin" / ("claude.exe" if sys.platform == "win32" else "claude")
    if oficial.is_file():
        return str(oficial)
    achado = shutil.which("claude")
    if achado and "windowsapps" not in achado.lower():
        return _sem_ps1(achado)
    return None


def no_modo_privado() -> bool:
    from core.cerebro_gemma import cerebro_gemma

    return cerebro_gemma()


def ambiente() -> dict:
    """Ambiente do Claude: sem chave da API (senão cobra fora da assinatura) e sem as chaves do Jarvis."""
    env = {k: v for k, v in os.environ.items()
           if k.upper() not in SEGREDOS and not k.upper().startswith(SEGREDOS_PREFIXOS)}
    env["PYTHONIOENCODING"] = "utf-8"
    env["ENABLE_CLAUDEAI_MCP_SERVERS"] = "false"  # reforço do --strict-mcp-config: sem conectores
    return env


def regra_de_pasta(caminho: Path | str) -> str:
    """Caminho absoluto no formato das regras do Claude Code: C:\\Users\\X -> //c/Users/X."""
    texto = Path(caminho).resolve().as_posix()
    if re.match(r"^[A-Za-z]:/", texto):
        texto = "/" + texto[0].lower() + texto[2:]
    return "/" + texto


def _ler(*pastas) -> list[str]:
    """Leitura só nessas pastas (e o que estiver dentro delas)."""
    return [f"Read({regra_de_pasta(p)}/**)" for p in pastas]


def _pastas_do_hermes() -> list[str]:
    """Onde o Hermes guarda as senhas dele (token do Telegram, senha de app do Gmail...). No Windows é
    %LOCALAPPDATA%\\hermes, que Read(~/.hermes/**) não pega. (Lidas aqui, antes de ambiente() tirar
    as variáveis HERMES_ do Claude.)"""
    pastas = [os.environ.get(nome, "").strip().strip('"') for nome in ("HERMES_HOME", "HERMES_JARVIS_HOME")]
    local = os.environ.get("LOCALAPPDATA", "").strip().strip('"')
    if local:
        pastas.append(str(Path(local) / "hermes"))
    return list(dict.fromkeys(p for p in pastas if p))


def _fora_da_foto(raiz: str) -> list[str]:
    """Na pasta do Jarvis, o que fotografar() não cobre também não pode ser mudado: senão não iria
    para o backup, não seria conferido nem desfeito (.venv, pastas com ponto, tmp, .zip, .log...).
    E as TRAVAS, que o Claude só lê."""
    regras = [f"Edit({raiz}/**/{nome}/**)" for nome in sorted(PASTAS_FORA) if not nome.startswith(".")]
    regras += [f"Edit({raiz}/**/.*/**)", f"Edit({raiz}/**/.env*)"]
    regras += [f"Edit({raiz}/**/*{fim})" for fim in (".pyc", ".zip", ".log")]
    regras += [f"Edit({raiz}/**/{nome})" for nome in sorted(ARQUIVOS_FORA) if not nome.startswith(".")]
    return regras + [f"Edit({raiz}/{item})" for item in TRAVAS]


def _proibidas_na(pasta: Path) -> list[str]:
    """As regras vão na linha de comando. Com o Claude do npm (claude.cmd), o Windows a passa pelo
    cmd.exe, que recusa mais de 8191 letras ("The command line is too long") e toda tarefa falharia:
    por isso cada regra só entra onde faz diferença."""
    regras = list(PROIBIDAS)
    pasta, jarvis = regra_de_pasta(pasta), regra_de_pasta(pasta_jarvis())
    for raiz in dict.fromkeys([pasta, jarvis]):
        for item in PROTEGIDOS:
            regras += [f"Read({raiz}/{item})", f"Edit({raiz}/{item})"]
    for item in CREDENCIAIS_DO_PROGRAMA:
        regras += [f"Read({jarvis}/{item})", f"Edit({jarvis}/{item})"]
    if jarvis == pasta or jarvis.startswith(pasta + "/"):  # só onde o Claude pode mudar a pasta do Jarvis
        regras += _fora_da_foto(jarvis)
    if pasta == regra_de_pasta(pasta_trabalho()):
        # O que as próximas tarefas seguem sozinhas o Claude só lê: os especialistas (Agency) e os
        # CLAUDE.md (carregados em toda tarefa). Assim uma página da internet com instruções
        # escondidas não vira regra permanente. O Erton continua podendo editar à mão.
        regras += [f"Edit({pasta}/Agency/**)", f"Edit({pasta}/**/CLAUDE.md)", f"Edit({pasta}/**/CLAUDE.local.md)"]
    regras += [f"Read({regra_de_pasta(pasta_dados())}/{nome})" for nome in DADOS_PRIVADOS]
    regras += [f"Read(~/{item})" for item in CREDENCIAIS]
    return list(dict.fromkeys(regras + _ler(*_pastas_do_hermes())))


def preparar_pasta() -> Path:
    """Cria a pasta de trabalho do Claude e copia/atualiza os agentes (skills) do Jarvis."""
    pasta = pasta_trabalho()
    for sub in ("Entrada", "Relatorios", "Mudancas"):
        (pasta / sub).mkdir(parents=True, exist_ok=True)
    origem = pasta_jarvis() / "claude"
    try:
        modelo = origem / "CLAUDE.md"
        if modelo.is_file() and not (pasta / "CLAUDE.md").exists():
            shutil.copy2(modelo, pasta / "CLAUDE.md")
        for skill in sorted((origem / "skills").glob("*/SKILL.md")):
            destino = pasta / ".claude" / "skills" / skill.parent.name / "SKILL.md"
            if not destino.exists() or destino.stat().st_mtime < skill.stat().st_mtime:
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(skill, destino)
    except OSError as erro:
        print(f"[Claude] Não consegui copiar os agentes: {erro}")
    _copiar_agency(origem / "agency", pasta / "Agency")
    return pasta


def _copiar_agency(origem: Path, destino: Path) -> None:
    """Especialistas da coleção agency-agents: ficam em Agency (fora de .claude) e o Claude abre os
    índices só quando precisa, por isso não pesam na lista do Gemini. O Claude não pode mudar essa
    pasta (veja _proibidas_na) e, se algo mudar mesmo assim, a cópia volta ao original: copia de novo
    quando o tamanho ou a data diferem, e o que não for da coleção sai. Os índices vão primeiro; um
    arquivo preso (antivírus, OneDrive) não impede os outros."""
    if not origem.is_dir():
        return
    arquivos = [a for a in origem.rglob("*") if a.is_file()]
    arquivos.sort(key=lambda a: (a.name != "INDICE.md", len(a.relative_to(origem).parts), a.as_posix()))
    falhas = 0
    for arquivo in arquivos:
        alvo = destino / arquivo.relative_to(origem)
        try:
            fonte = arquivo.stat()
            if alvo.exists():
                atual = alvo.stat()
                if atual.st_size == fonte.st_size and atual.st_mtime_ns == fonte.st_mtime_ns:
                    continue
            alvo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(arquivo, alvo)  # leva a data junto: na próxima vez fica igual e não copia
        except OSError:
            falhas += 1
    if arquivos:
        falhas += _limpar_sobras(destino, {a.relative_to(origem).as_posix().casefold() for a in arquivos})
    if falhas:
        print(f"[Claude] Não consegui copiar ou limpar {falhas} arquivo(s) dos especialistas (pasta Agency).")


def _limpar_sobras(destino: Path, esperados: set[str]) -> int:
    """Tira de Agency o que não está na coleção (agente que saiu numa atualização, arquivo que não
    devia estar lá). A pasta é toda do Jarvis. Compara sem maiúsculas, como o Windows, e não entra
    em atalhos de pasta. Devolve quantos não deu para apagar."""
    falhas = 0
    for raiz, pastas, arquivos in os.walk(destino, topdown=False, followlinks=False):
        for nome in arquivos:
            arquivo = Path(raiz) / nome
            if arquivo.relative_to(destino).as_posix().casefold() in esperados:
                continue
            try:
                arquivo.unlink()
            except OSError:
                falhas += 1
        for nome in pastas:
            try:
                (Path(raiz) / nome).rmdir()  # só some se ficou vazia
            except OSError:
                pass
    return falhas


def agentes() -> list[str]:
    raiz = pasta_jarvis() / "claude" / "skills"
    return sorted(p.parent.name for p in raiz.glob("*/SKILL.md"))


def agente_do_jarvis(nome: str | None) -> str | None:
    """O nome certo de um dos agentes do Jarvis (claude/skills), aceitando o jeito que o Gemini
    escrever: "Briefing Diário", "briefing diario" e "briefing-diario" dão "briefing-diario"."""
    nome = (nome or "").strip()
    if not nome:
        return None
    lista = agentes()
    if nome in lista:
        return nome
    simples = _so_letras(nome)
    achados = [s for s in lista if _so_letras(s) == simples]
    return achados[0] if len(achados) == 1 else None


def _so_letras(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto.lower())
    base = "".join(c for c in base if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-")


def campo_no_cabecalho(texto: str, campo: str = "name") -> str | None:
    """Um campo (name, description...) do bloco --- ... --- do começo de um agente. Só do
    cabeçalho, nunca do corpo; aceita arquivo salvo com BOM."""
    linhas = texto.lstrip("\ufeff").splitlines()
    if not linhas or linhas[0].strip() != "---":
        return None
    for linha in linhas[1:]:
        if linha.strip() == "---":
            return None
        chave, _, valor = linha.partition(":")
        if chave.strip() == campo and valor.strip():
            return valor.strip().strip("\"'")
    return None


@lru_cache(maxsize=4)
def _mapa_agency(raiz: str) -> tuple[tuple[str, str, str], ...]:
    """(nome do arquivo, name: em letras simples, caminho) de cada especialista. Lido uma vez por
    abertura do Jarvis: trocar a coleção pede fechar e abrir o Jarvis de novo."""
    pasta = Path(raiz)
    mapa = []
    for arquivo in sorted(pasta.rglob("*.md")):
        if arquivo.name == "INDICE.md":
            continue
        try:
            with open(arquivo, encoding="utf-8", errors="replace") as f:
                nome = campo_no_cabecalho(f.read(1200))
        except OSError:
            continue
        mapa.append((arquivo.stem, _so_letras(nome or ""), arquivo.relative_to(pasta).as_posix()))
    return tuple(mapa)


def agente_agency(nome: str) -> str | None:
    """Caminho (a partir da pasta Agency) do especialista com esse nome, ou None.

    Procura em camadas e só aceita uma resposta única em cada uma: 1) o nome do arquivo
    ("finance-tax-strategist"); 2) o nome de dentro do arquivo ("Tax Strategist"); 3) o fim do nome
    do arquivo ("tax-strategist"). Assim "Data Engineer" acha o engineering-data-engineer mesmo
    existindo também um gis-spatial-data-engineer."""
    procurado = _so_letras(nome or "")
    if not procurado:
        return None
    mapa = _mapa_agency(str(pasta_jarvis() / "claude" / "agency"))
    for bate in (lambda stem, nome_: stem == procurado,
                 lambda stem, nome_: nome_ == procurado,
                 lambda stem, nome_: stem.endswith("-" + procurado)):
        achados = [caminho for stem, nome_, caminho in mapa if bate(stem, nome_)]
        if len(achados) == 1:
            return achados[0]
        if achados:
            return None  # serve para mais de um: melhor não chutar
    return None


# ---------------- conversar com o Claude Code ----------------
def comando(exe: str, permitir, pasta: Path, sessao: str | None = None, turnos: int = MAX_TURNOS,
            pastas_extras=()) -> list[str]:
    """O pedido vai pela entrada padrão (não pela linha de comando), porque no Windows um claude.cmd
    estragaria textos com acentos, aspas ou '&'."""
    cmd = [exe, "-p", "--output-format", "json", "--permission-mode", "dontAsk", "--max-turns", str(turnos),
           "--strict-mcp-config"]  # nenhum servidor MCP: sem os conectores da conta (Gmail, Agenda...)
    modelo = os.environ.get("JARVIS_CLAUDE_MODELO", "").strip()
    if modelo:
        cmd += ["--model", modelo]
    if sessao:
        cmd += ["--resume", sessao]
    extras = [str(p) for p in pastas_extras if Path(p).is_dir()]
    if extras:
        cmd += ["--add-dir", *extras]
    cmd += ["--allowedTools", *permitir, "--disallowedTools", *_proibidas_na(pasta)]
    return cmd


def _ler_json(saida: str) -> dict | None:
    saida = (saida or "").strip()
    if not saida:
        return None
    try:
        dados = json.loads(saida)
        if isinstance(dados, list):  # alguns modos devolvem a lista de mensagens
            dados = next((m for m in reversed(dados) if isinstance(m, dict) and m.get("type") == "result"), None)
        return dados if isinstance(dados, dict) else None
    except ValueError:
        pass
    for linha in reversed(saida.splitlines()):
        try:
            dados = json.loads(linha)
        except ValueError:
            continue
        if isinstance(dados, dict) and dados.get("type") == "result":
            return dados
    return None


def explicar(texto: str, subtipo: str = "") -> str:
    baixo = (texto or "").lower()
    if subtipo == "error_max_turns":
        return "a tarefa ficou grande demais para uma vez só; peça em partes menores"
    if "not logged in" in baixo or "/login" in baixo or "login expired" in baixo or "invalid api key" in baixo:
        return ("o Claude não está conectado à sua conta. Dê dois cliques em 'Instalar Claude' na pasta do "
                "Jarvis para entrar de novo")
    if "subscription access" in baixo or "oauth_org_not_allowed" in baixo:
        return "a sua organização desligou o uso da assinatura no Claude Code"
    if "limit" in baixo and ("reset" in baixo or "hit your" in baixo):
        volta = re.search(r"resets?\s+([^·\n.]+)", texto or "", re.IGNORECASE)
        quando = f" (volta: {volta.group(1).strip()})" if volta else ""
        return f"o limite do seu plano do Claude acabou por agora{quando}"
    return (texto or "erro desconhecido").strip()[:200]


@lru_cache(maxsize=1)
def _estruturas_do_job():
    """JOBOBJECT_EXTENDED_LIMIT_INFORMATION do Windows (para o "job" que morre junto com o Jarvis)."""
    import ctypes

    class Basico(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", ctypes.c_uint32), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", ctypes.c_uint32),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", ctypes.c_uint32),
                    ("SchedulingClass", ctypes.c_uint32)]

    class Contadores(ctypes.Structure):
        _fields_ = [(nome, ctypes.c_uint64) for nome in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class Estendido(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", Basico), ("IoInfo", Contadores),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    return Estendido


@lru_cache(maxsize=1)
def _kernel32():
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    k32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    k32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    k32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    return k32


def _job_que_morre_com_o_jarvis(processo):
    """No Windows, põe o programa num "job" com KILL_ON_JOB_CLOSE: se o Jarvis fechar, cair ou for
    encerrado no meio, o Windows encerra o programa (e o que ele abriu) junto. Sem isso o claude.exe
    continuaria mudando o código sozinho, sem testes e sem desfazer. None se não deu (ou fora do Windows)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        k32 = _kernel32()
        job = k32.CreateJobObjectW(None, None)
        if not job:
            return None
        info = _estruturas_do_job()()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if (k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))  # 9 = estendida
                and k32.AssignProcessToJobObject(job, int(processo._handle))):
            return job
        k32.CloseHandle(job)
    except Exception as erro:
        print(f"[Claude] Não consegui prender o programa ao Jarvis: {erro}")
    return None


def _encerrar_tudo(processo, job) -> None:
    """Encerra o programa e tudo o que ele abriu (o claude.cmd do npm abre um node.exe)."""
    try:
        if sys.platform == "win32":
            # a árvore toda, enquanto o primeiro ainda existe (depois não dá para achar os "netos")
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(processo.pid)], capture_output=True, timeout=30,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            os.killpg(processo.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    if job:
        _kernel32().TerminateJobObject(job, 1)  # e o que ainda estiver no job
    try:
        processo.kill()
    except OSError:
        pass


def _executar(cmd: list[str], entrada: bytes | None, tempo: float, pasta: Path, env: dict) -> tuple[int, bytes, bytes]:
    """Roda um programa e devolve (código, saída, erros). Passando do tempo, encerra o programa E o que
    ele abriu, e levanta subprocess.TimeoutExpired (o subprocess.run só encerrava o primeiro: com o
    claude.cmd do npm, o node.exe seguia trabalhando e segurando a tarefa)."""
    if sys.platform == "win32":
        extra = {"creationflags": subprocess.CREATE_NO_WINDOW}
    else:
        extra = {"start_new_session": True}  # grupo próprio: dá para encerrar os "netos" também
    processo = subprocess.Popen(cmd, stdin=subprocess.PIPE if entrada is not None else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(pasta), env=env, **extra)
    job = _job_que_morre_com_o_jarvis(processo)
    try:
        saida, erros = processo.communicate(entrada, timeout=tempo)
    except subprocess.TimeoutExpired:
        _encerrar_tudo(processo, job)
        try:
            processo.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            pass  # algo ainda segura a saída: desiste dela
        raise
    finally:
        if job:
            _kernel32().CloseHandle(job)  # o que sobrou no job é encerrado aqui
    return processo.returncode, saida, erros


def rodar(pedido: str, permitir, pasta: Path, sessao: str | None = None, tempo: float = TEMPO_TAREFA,
          turnos: int = MAX_TURNOS, pastas_extras=()) -> Resposta:
    exe = achar_claude()
    if not exe:
        return Resposta(False, erro="o Claude Code não está instalado. Dê dois cliques em 'Instalar Claude' "
                                    "na pasta do Jarvis")
    try:
        codigo, saida, problemas = _executar(comando(exe, permitir, pasta, sessao, turnos, pastas_extras),
                                             pedido.encode("utf-8"), tempo, pasta, ambiente())
    except subprocess.TimeoutExpired:
        return Resposta(False, erro=f"o Claude passou de {int(tempo // 60)} minutos e eu parei a tarefa")
    except OSError as erro:
        return Resposta(False, erro=f"não consegui abrir o Claude Code: {erro}")
    saida = saida.decode("utf-8", "replace")
    problemas = problemas.decode("utf-8", "replace")
    dados = _ler_json(saida)
    if dados is None:
        return Resposta(False, erro=explicar(problemas.strip() or saida.strip() or f"saída {codigo}"))
    texto = str(dados.get("result") or "")
    negadas = list(dados.get("permission_denials") or [])
    if dados.get("is_error") or str(dados.get("subtype", "success")) != "success" or codigo != 0:
        detalhe = texto or " ".join(map(str, dados.get("errors") or [])) or problemas
        return Resposta(False, texto, dados.get("session_id"), explicar(detalhe, str(dados.get("subtype", ""))), negadas)
    return Resposta(True, texto, dados.get("session_id"), negadas=negadas)


def separar_fala(texto: str) -> tuple[str, str]:
    """('resumo para falar', 'conteúdo completo')."""
    texto = (texto or "").strip()
    achado = re.search(r"^\s*\**FALA:?\**\s*(.+)$", texto, re.IGNORECASE | re.MULTILINE)
    if achado:
        fala = achado.group(1).strip().strip("*").strip()
        resto = (texto[:achado.start()] + texto[achado.end():]).strip()
        return fala, resto
    limpo = re.sub(r"[#*`>|_]+", " ", texto)
    frases = re.split(r"(?<=[.!?])\s+", " ".join(limpo.split()))
    return " ".join(frases[:2])[:400], texto


def _nome_de_arquivo(texto: str) -> str:
    base = _so_letras(texto)[:50] or "tarefa"
    return f"{datetime.now():%Y-%m-%d-%H%M}-{base}.md"


def salvar_relatorio(pedido: str, conteudo: str) -> Path | None:
    if len(conteudo.strip()) < 200:
        return None
    arquivo = pasta_trabalho() / "Relatorios" / _nome_de_arquivo(pedido)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(f"# {pedido.strip()}\n\n{conteudo.strip()}\n", encoding="utf-8")
    return arquivo


# ---------------- tarefas (pesquisa, análise, agentes) ----------------
_SO_RASCUNHO = " Onde ele falar em publicar, enviar ou usar conectores, prepare só o rascunho."


def _instrucao_do_agente(agente: str | None) -> str:
    """O que vai no pedido sobre o agente. O nome vem do Gemini: no texto entra só o caminho de um
    arquivo que existe (ou uma versão limpa e curta do nome, como dica)."""
    agente = (agente or "").strip()
    if not agente:
        return ""
    skill = agente_do_jarvis(agente)
    if skill:
        return f"\nSiga as instruções do agente do arquivo .claude/skills/{skill}/SKILL.md nesta pasta." + _SO_RASCUNHO
    especialista = agente_agency(agente)
    if especialista:
        return f"\nSiga as instruções do especialista do arquivo Agency/{especialista} nesta pasta." + _SO_RASCUNHO
    dica = " ".join(re.sub(r"[^\w &+-]", " ", agente).split())[:60]
    if not dica:
        return ""
    return (f"\nO Erton pediu o especialista \"{dica}\", que não achei pelo nome: procure o mais parecido "
            "nos índices da pasta Agency e, se nenhum servir, diga isso e faça a tarefa sem ele.")


def fazer_tarefa(pedido: str, agente: str | None = None, sessao: str | None = None) -> Resposta:
    pasta = preparar_pasta()
    texto = REGRAS + REGRAS_TAREFA.format(pasta=pasta, dados=pasta_dados())
    texto += _instrucao_do_agente(agente)
    texto += f"\n\nPEDIDO DO ERTON:\n{pedido.strip()}"
    permitir = [*LEITURA, *_ler(pasta, pasta_dados()), f"Edit({regra_de_pasta(pasta)}/**)"]
    return rodar(texto, permitir, pasta, sessao=sessao, pastas_extras=[pasta_dados()])


# ---------------- código do Jarvis: plano -> ok -> backup -> testes -> aplica -> confere ----------------
def planejar(pedido: str) -> Resposta:
    pasta = pasta_jarvis()
    texto = REGRAS + REGRAS_PLANO + f"\n\nPEDIDO DO ERTON:\n{pedido.strip()}"
    return rodar(texto, [*LEITURA, *_ler(pasta)], pasta)  # sem Edit: no plano ele não consegue mudar nada


def _arquivos_de_codigo(pasta: Path, exemplos: bool = False):
    """Com exemplos=True vêm também os .env.example (só exemplo, sem chaves)."""
    for raiz, pastas, arquivos in os.walk(pasta):
        pastas[:] = [p for p in pastas if p not in PASTAS_FORA and not p.startswith(".")]
        for nome in arquivos:
            if exemplos and nome == ".env.example":
                pass
            elif nome in ARQUIVOS_FORA or nome.startswith(".env") or nome.endswith((".pyc", ".zip", ".log")):
                continue
            caminho = Path(raiz) / nome
            yield caminho.relative_to(pasta).as_posix(), caminho


def fotografar(pasta: Path) -> dict[str, str]:
    """{arquivo: impressão digital} de tudo o que o Claude pode mudar. Os maiores que 5 MB (e os que
    não deu para ler) não vão para o backup, mas entram aqui com tamanho e data: assim nunca são
    apagados como se fossem novos, e uma mudança neles aparece."""
    foto = {}
    for nome, caminho in _arquivos_de_codigo(pasta):
        try:
            info = caminho.stat()
            if info.st_size > LIMITE_BACKUP:
                foto[nome] = f"grande:{info.st_size}:{info.st_mtime_ns}"
            else:
                foto[nome] = hashlib.sha1(caminho.read_bytes()).hexdigest()
        except OSError:
            foto[nome] = "ilegivel"
    return foto


def _vai_no_backup(impressao: str) -> bool:
    return len(impressao) == 40  # sha1 de verdade (não "grande:..." nem "ilegivel")


def fazer_backup(pasta: Path, foto: dict[str, str]) -> Path:
    destino = pasta_backups() / f"jarvis-antes-do-claude-{datetime.now():%Y%m%d-%H%M%S}.zip"
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zipado:
        for nome, impressao in foto.items():
            if _vai_no_backup(impressao):
                zipado.write(pasta / nome, nome)
    return destino


def _nome_seguro(nome: str) -> bool:
    """Um nome (da foto ou da anotação) nunca aponta para fora da pasta do Jarvis."""
    caminho = PurePosixPath(nome)
    return bool(nome) and not caminho.is_absolute() and ".." not in caminho.parts and ":" not in nome


class BackupEstragado(Exception):
    """O backup .zip da mudança sumiu ou estragou: com ele não dá para voltar nada (e não adianta tentar
    de novo)."""


@dataclass
class Restauro:
    mexidos: list = field(default_factory=list)   # voltaram ao que eram (ou foram apagados)
    deixados: list = field(default_factory=list)  # mudaram de novo depois do Claude: não eram dele
    copia: Path | None = None                      # .zip com o que estava no lugar antes de desfazer


def _guardar_como_esta(pasta: Path, nomes: list[str]) -> Path | None:
    """Antes de sobrescrever ou apagar, guarda a versão atual: desfazer nunca perde nada de ninguém."""
    nomes = [n for n in nomes if (pasta / n).is_file()]
    if not nomes:
        return None
    destino = pasta_backups() / f"jarvis-desfeito-{datetime.now():%Y%m%d-%H%M%S}.zip"
    n = 2
    while destino.exists():
        destino = destino.with_name(f"jarvis-desfeito-{datetime.now():%Y%m%d-%H%M%S}-{n}.zip")
        n += 1
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zipado:
        for nome in nomes:
            zipado.write(pasta / nome, nome)
    return destino


def restaurar(pasta: Path, backup: Path, antes: dict[str, str], nomes=None,
              claude: dict[str, str] | None = None) -> Restauro:
    """Volta ao que era cada arquivo de 'nomes' (padrão: tudo o que mudou desde 'antes') e apaga os
    que não existiam antes. Com 'claude' (a foto logo depois do Claude), só mexe no que continua como
    o Claude deixou: o que mudou depois foi outra pessoa e fica como está. Nunca apaga um arquivo que
    já existia, e guarda a versão atual de tudo o que sobrescreve ou apaga (Restauro.copia)."""
    depois = fotografar(pasta)
    feito = Restauro()
    alvos = []
    for nome in (mudancas(antes, depois) if nomes is None else nomes):
        if depois.get(nome) == antes.get(nome) or not _nome_seguro(nome):
            continue
        if claude is not None and depois.get(nome) != claude.get(nome):
            feito.deixados.append(nome)
            continue
        alvos.append(nome)
    voltar = {}
    if any(n in antes for n in alvos):
        # lê o backup ANTES de mexer em qualquer arquivo: se ele sumiu ou estragou, nada é apagado nem trocado
        try:
            with zipfile.ZipFile(backup) as zipado:
                guardados = set(zipado.namelist())
                # o que não está nele (grande demais) fica como está e aparece como "não consegui"
                voltar = {n: zipado.read(n) for n in alvos if n in antes and n in guardados}
        except (FileNotFoundError, zipfile.BadZipFile, zlib.error, EOFError, ValueError) as erro:
            raise BackupEstragado(f"{backup.name}: {erro}") from erro
    feito.copia = _guardar_como_esta(pasta, alvos)
    for nome in [n for n in alvos if n not in antes]:  # criados durante a mudança
        try:
            (pasta / nome).unlink()
            feito.mexidos.append(nome)
        except OSError:
            pass
    for nome, conteudo in voltar.items():
        (pasta / nome).parent.mkdir(parents=True, exist_ok=True)
        (pasta / nome).write_bytes(conteudo)
        feito.mexidos.append(nome)
    return feito


def mudancas(antes: dict[str, str], depois: dict[str, str]) -> list[str]:
    return sorted(n for n in antes.keys() | depois.keys() if antes.get(n) != depois.get(n))


def _copiar_codigo(pasta: Path, destino: Path) -> None:
    """Cópia do código para os testes: sem .env, sem a memória e sem os dados do Erton (da pasta
    memory vão só os .py, que são código). Arquivos maiores que 5 MB não vão. O .env.example vai: é só
    exemplo, sem chaves, e um teste lê."""
    arquivos = list(_arquivos_de_codigo(pasta, exemplos=True))
    memoria = pasta / "memory"
    if memoria.is_dir():
        arquivos += [(f"memory/{c.name}", c) for c in memoria.iterdir()
                     if c.is_file() and (c.suffix in (".py", ".md") or ".example." in c.name)]
    for nome, caminho in arquivos:
        alvo = destino / nome
        try:
            if caminho.stat().st_size > LIMITE_BACKUP:
                continue
            alvo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(caminho, alvo)
        except OSError:
            continue


def rodar_testes(pasta: Path, tempo: float = TEMPO_TESTES) -> set[str] | None:
    """Roda os testes do Jarvis. Devolve o conjunto de testes que falharam (None = não deu para rodar).
    Os testes rodam numa cópia do código e com uma "pasta do usuário" de mentira: assim não mexem no
    tema, no histórico, no diagnóstico nem nas chaves do Erton (e o .env dele não é lido)."""
    if not (pasta / "tests").is_dir():
        return None
    if importlib.util.find_spec("pytest") is not None:
        cmd = [sys.executable, "-m", "pytest", "tests", "-q", "-rfE", "-p", "no:cacheprovider"]
        falhou = re.compile(r"^(?:FAILED|ERROR) (\S+)", re.MULTILINE)
        terminou = re.compile(r"\d+ (?:passed|failed)")
    else:
        cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."]
        falhou = re.compile(r"^(?:FAIL|ERROR): (\S+ \([^)]+\))", re.MULTILINE)
        terminou = re.compile(r"^Ran \d+ tests?", re.MULTILINE)
    with tempfile.TemporaryDirectory(prefix="jarvis-testes-", ignore_cleanup_errors=True) as temporaria:
        copia, casa = Path(temporaria) / "jarvis", Path(temporaria) / "casa"
        _copiar_codigo(pasta, copia)
        for sub in ("AppData/Roaming", "AppData/Local", "Documents"):
            (casa / sub).mkdir(parents=True, exist_ok=True)
        env = ambiente()
        env.setdefault("PYTHONUSERBASE", site.getuserbase())  # os pacotes do usuário continuam achados
        env.update(QT_QPA_PLATFORM="offscreen", JARVIS_UM_PROCESSO="1", JARVIS_ORBE_GPU="0",
                   HOME=str(casa), USERPROFILE=str(casa), APPDATA=str(casa / "AppData" / "Roaming"),
                   LOCALAPPDATA=str(casa / "AppData" / "Local"))
        try:
            _codigo, saida, erros = _executar(cmd, None, tempo, copia, env)
        except (subprocess.TimeoutExpired, OSError):
            return None
    saida = saida.decode("utf-8", "replace") + "\n" + erros.decode("utf-8", "replace")
    if not terminou.search(saida):
        return None
    return set(falhou.findall(saida))


def conferir_sintaxe(pasta: Path, nomes: list[str]) -> list[str]:
    ruins = []
    for nome in nomes:
        caminho = pasta / nome
        if nome.endswith(".py") and caminho.is_file():
            try:  # compila só na memória (não grava nada)
                compile(caminho.read_bytes(), str(caminho), "exec")
            except (SyntaxError, ValueError, OSError) as erro:
                ruins.append(f"{nome}: {str(erro).splitlines()[-1][:120] if str(erro) else type(erro).__name__}")
    return ruins


@dataclass
class Resultado:
    ok: bool
    fala: str
    detalhes: str = ""


_aplicando = threading.Lock()  # preso enquanto o Claude muda o código do Jarvis (do backup ao fim)


def aplicando() -> bool:
    """True enquanto o Claude aplica uma mudança no código do Jarvis (neste programa). Quem religa o
    cérebro ou mexe na pasta do Jarvis confere isto antes."""
    return _aplicando.locked()


def _anotacao() -> Path:
    """A mudança em andamento fica anotada fora da pasta do Jarvis (e fora do alcance do Claude)."""
    return pasta_backups() / "aplicando.json"


def _anotar(dados: dict) -> None:
    arquivo = _anotacao()
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    novo = arquivo.with_name(arquivo.name + ".novo")
    novo.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    os.replace(novo, arquivo)  # de uma vez: nunca fica uma anotação pela metade


def _ler_anotacao() -> dict | None:
    try:
        dados = json.loads(_anotacao().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _apagar_anotacao() -> None:
    try:
        _anotacao().unlink()
    except FileNotFoundError:
        pass


def _travar_codigo() -> int | None:
    """Trava Backups/aplicando.lock sem esperar: enquanto travada, um Jarvis aberto está mudando ou
    desfazendo o código. aplicando() só enxerga este programa, e fechar a janela deixa o Jarvis na
    bandeja: um segundo Jarvis aberto (dois cliques em "Iniciar Jarvis Ultron") não pode desfazer a
    mudança que o primeiro ainda está fazendo. A trava fica com quem travou até _soltar_codigo() ou até
    o programa fechar ou cair (aí o próprio Windows solta). None = outro Jarvis está com ela agora."""
    arquivo = pasta_backups() / "aplicando.lock"  # nunca é apagado (só travado e solto)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    descritor = os.open(arquivo, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if sys.platform == "win32":
            import msvcrt

            os.lseek(descritor, 0, os.SEEK_SET)
            msvcrt.locking(descritor, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(descritor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as erro:
        if isinstance(erro, BlockingIOError) or erro.errno in (errno.EACCES, errno.EAGAIN):
            os.close(descritor)
            return None  # outro Jarvis está com ela
        print(f"[Claude] A trava entre dois Jarvis abertos não funciona nesta pasta: {erro}")
    return descritor


def _soltar_codigo(descritor: int) -> None:
    try:
        if sys.platform == "win32":
            import msvcrt

            os.lseek(descritor, 0, os.SEEK_SET)
            msvcrt.locking(descritor, msvcrt.LK_UNLCK, 1)
    except OSError:
        pass
    os.close(descritor)  # fechar também solta (fora do Windows)


def _mesma_pasta(uma, outra) -> bool:
    def normal(caminho) -> str:
        try:
            caminho = Path(caminho).resolve()
        except OSError:
            caminho = Path(caminho).absolute()
        return os.path.normcase(str(caminho))  # no Windows, sem diferenciar maiúsculas

    return normal(uma) == normal(outra)


def desfazer_interrompida() -> str:
    """Na abertura do Jarvis (e do cérebro): uma mudança do Claude no código ficou pela metade porque o
    Jarvis fechou, o cérebro foi religado ou o PC desligou no meio? Volta os arquivos ao que eram
    antes dela (guardando a versão pela metade em Backups). Devolve o aviso para o Erton ("" se não
    havia nada); o aviso continua valendo até esquecer_interrompida()."""
    if aplicando() or _ler_anotacao() is None:
        return ""  # nada anotado, ou a mudança está rodando agora, neste programa
    trava = _travar_codigo()
    if trava is None:
        return ""  # outro Jarvis aberto está mudando (ou desfazendo) o código agora: a anotação é dele
    try:
        return _desfazer_interrompida()
    finally:
        _soltar_codigo(trava)


def _desfazer_interrompida() -> str:
    dados = _ler_anotacao()
    if dados is None:
        return ""
    if dados.get("aviso"):
        return str(dados["aviso"])  # já desfeita (por exemplo pelo "Iniciar Jarvis Ultron"); falta contar
    try:
        backup = Path(str(dados["backup"]))
        antes = {str(k): str(v) for k, v in dict(dados["antes"]).items()}
        anotada = Path(str(dados["pasta"]))
    except (KeyError, TypeError, ValueError):
        _apagar_anotacao()
        return ("Uma mudança do Claude no meu código foi interrompida, mas a anotação dela estragou e eu não "
                f"consegui conferir. Os backups estão em {pasta_backups()}.")
    pasta = pasta_jarvis()
    if not _mesma_pasta(anotada, pasta):
        return ""  # foi em outro Jarvis (outra pasta): a anotação fica para quando ele abrir
    pedido, plano = str(dados.get("pedido") or "mudança no código"), str(dados.get("plano") or "")
    if not isinstance(dados.get("pela_metade"), dict):
        # primeira tentativa: anota como o Claude deixou cada arquivo. Se não der para desfazer agora, as
        # próximas aberturas só mexem nisso (o que mudar ou aparecer depois na pasta é de outra pessoa)
        agora = fotografar(pasta)
        dados["pela_metade"] = {n: agora.get(n) for n in mudancas(antes, agora)}
        try:
            _anotar(dados)
        except OSError:
            pass
    mudados = sorted(str(n) for n in dados["pela_metade"])
    como_ficou = {str(n): str(v) for n, v in dados["pela_metade"].items() if v is not None}
    try:
        feito = restaurar(pasta, backup, antes, mudados, como_ficou)
    except BackupEstragado as erro:  # não adianta tentar de novo: avisa uma vez só e não mexe em nada
        aviso = ("Uma mudança do Claude no meu código ficou pela metade e eu não consegui desfazer, porque o "
                 f"backup dela sumiu ou estragou ({backup.name}). Não mexi em nada; os arquivos que ele mudou "
                 f"são {', '.join(mudados[:3]) or 'nenhum'}.")
        registrar(pedido, plano, mudados, f"NÃO DESFEITO: o Jarvis fechou no meio e o backup estragou ({erro})",
                  backup)
    except OSError as erro:  # a anotação fica: tento de novo na próxima abertura
        return (f"Uma mudança do Claude no meu código ficou pela metade e eu não consegui desfazer ({erro}). "
                f"Tento de novo na próxima vez que eu abrir. O backup está em {backup}.")
    else:
        aviso = _aviso_de_desfeita(pasta, antes, mudados, feito, backup)
        if mudados:
            registrar(pedido, plano, mudados, "DESFEITO: o Jarvis fechou no meio da mudança", backup)
    dados["aviso"] = aviso
    try:
        _anotar(dados)
    except OSError:
        pass
    return aviso


def _aviso_de_desfeita(pasta: Path, antes: dict[str, str], mudados: list[str], feito: Restauro,
                       backup: Path) -> str:
    if not mudados:
        return ("Uma mudança do Claude no meu código foi interrompida porque o Jarvis fechou ou foi religado no "
                "meio, mas ele ainda não tinha mudado nenhum arquivo.")
    agora = fotografar(pasta)
    sobrou = [n for n in mudados if n not in feito.deixados and agora.get(n) != antes.get(n)]
    aviso = ("Uma mudança do Claude no meu código ficou pela metade porque o Jarvis fechou ou foi religado no "
             "meio, e eu desfiz: o código voltou a ser como era antes dela.")
    if feito.deixados:
        aviso += f" Não mexi em {', '.join(feito.deixados[:3])}, que mudou depois."
    if sobrou:
        aviso += f" Atenção: não consegui voltar {', '.join(sobrou[:3])}; o backup está em {backup}."
    if feito.copia:
        aviso += f" A versão pela metade ficou guardada em Backups, no arquivo {feito.copia.name}."
    return aviso


def esquecer_interrompida(aviso: str | None = None) -> None:
    """O aviso de desfazer_interrompida() já foi dado ao Erton: apaga a anotação, mas só a desse aviso
    (nunca a de uma mudança que este ou outro Jarvis aberto está fazendo agora)."""
    if aplicando() or not (_ler_anotacao() or {}).get("aviso"):
        return
    trava = _travar_codigo()
    if trava is None:
        return  # outro Jarvis aberto está mudando o código: a anotação agora é dele
    try:
        dados = _ler_anotacao() or {}
        if dados.get("aviso") and (aviso is None or dados["aviso"] == aviso):
            _apagar_anotacao()
    finally:
        _soltar_codigo(trava)


def aplicar_plano(plano: str, sessao: str | None, pedido: str) -> Resultado:
    if not _aplicando.acquire(blocking=False):
        return Resultado(False, "Já tem uma mudança do Claude no código em andamento; espere ela terminar.")
    try:
        trava = _travar_codigo()  # e nenhum outro Jarvis aberto mexe no código até o fim
        if trava is None:
            return Resultado(False, "Outro Jarvis aberto neste PC está mudando o código agora; espere ele terminar.")
        try:
            return _aplicar_plano(plano, sessao, pedido)
        finally:
            _soltar_codigo(trava)
    finally:
        _aplicando.release()


def _aplicar_plano(plano: str, sessao: str | None, pedido: str) -> Resultado:
    pasta = pasta_jarvis()
    falhas_antes = rodar_testes(pasta)
    antes = fotografar(pasta)  # logo antes do Claude: o que mudar antes disso não é dele
    backup = fazer_backup(pasta, antes)
    # se o Jarvis fechar ou cair daqui até o fim, a próxima abertura desfaz (desfazer_interrompida), só
    # nesta pasta do Jarvis
    _anotar({"backup": str(backup), "antes": antes, "pedido": pedido, "plano": plano, "desde": time.time(),
             "pasta": str(pasta)})
    try:
        return _aplicar_e_conferir(pasta, antes, backup, falhas_antes, plano, sessao, pedido)
    except Exception:
        restaurar(pasta, backup, antes)  # erro inesperado no meio: volta já (a anotação fica se nem isso der)
        _apagar_anotacao()
        raise


def _aplicar_e_conferir(pasta: Path, antes: dict[str, str], backup: Path, falhas_antes, plano: str,
                        sessao: str | None, pedido: str) -> Resultado:
    permitir = [*LEITURA, *_ler(pasta), f"Edit({regra_de_pasta(pasta)}/**)"]
    texto = REGRAS + REGRAS_APLICAR.format(plano=plano.strip())
    resposta = rodar(texto, permitir, pasta, sessao=sessao, turnos=MAX_TURNOS + 20)
    if not resposta.ok and sessao and "session" in resposta.erro.lower():
        resposta = rodar(texto, permitir, pasta, turnos=MAX_TURNOS + 20)  # a conversa do plano sumiu
    depois_claude = fotografar(pasta)
    mudados = mudancas(antes, depois_claude)

    def desfazer(motivo: str) -> Resultado:
        # só o que continua como o Claude deixou; o que alguém mudou depois fica como está
        feito = restaurar(pasta, backup, antes, mudados, depois_claude)
        _apagar_anotacao()
        agora = fotografar(pasta)
        sobrou = [n for n in mudados if n not in feito.deixados and agora.get(n) != antes.get(n)]
        fala = f"Desfiz a mudança porque {motivo}. O código voltou a ser como era antes dela."
        if feito.deixados:
            fala = (f"Desfiz a mudança porque {motivo}. O que o Claude mudou voltou a ser como era; não mexi em "
                    f"{', '.join(feito.deixados[:3])}, que mudou depois dele.")
        if sobrou:
            fala += f" Atenção: não consegui voltar {', '.join(sobrou)}; o backup está em {backup}."
        if feito.copia:
            # o que alguém salvou na pasta do Jarvis enquanto o Claude trabalhava também voltou: fica guardado
            fala += (f" A versão que estava no lugar ficou guardada em Backups, no arquivo {feito.copia.name}, "
                     "caso você tenha mexido em algum arquivo do Jarvis enquanto o Claude trabalhava.")
        registro = registrar(pedido, plano, mudados, f"DESFEITO: {motivo}", backup)
        guardado = f". O que estava no lugar ficou guardado em {feito.copia}" if feito.copia else ""
        return Resultado(False, fala, f"Registro: {registro}{guardado}")

    if not resposta.ok:
        if mudados:
            return desfazer(f"o Claude parou no meio ({resposta.erro})")
        _apagar_anotacao()
        return Resultado(False, f"O Claude não conseguiu aplicar: {resposta.erro}.")
    if not mudados:
        _apagar_anotacao()
        return Resultado(False, "O Claude terminou sem mudar nenhum arquivo. " + resposta.fala)

    ruins = conferir_sintaxe(pasta, mudados)
    if ruins:
        return desfazer("o código novo tinha erro de escrita (" + "; ".join(ruins[:2]) + ")")
    falhas_depois = rodar_testes(pasta)
    if falhas_antes is not None:
        if falhas_depois is None:
            return desfazer("os testes não conseguiram nem rodar depois da mudança")
        novas = sorted(falhas_depois - falhas_antes)
        if novas:
            return desfazer(f"{len(novas)} teste(s) que passavam começaram a falhar ({', '.join(novas[:3])})")
        situacao = "os testes continuam passando"
    else:
        situacao = "não consegui rodar os testes neste PC, mas a sintaxe está certa"

    _apagar_anotacao()  # deu certo: a próxima abertura não desfaz
    registro = registrar(pedido, plano, mudados, f"APLICADO ({situacao})", backup)
    # o X da janela só esconde o Jarvis perto do relógio: reabrindo assim, o antigo continuaria ligado
    fala = (f"Pronto: o Claude mudou {len(mudados)} arquivo(s) e {situacao}. As mudanças valem quando você "
            f"fechar o Jarvis de verdade, no ícone perto do relógio, em Quit JARVIS, e abrir de novo. "
            f"{resposta.fala}").strip()
    return Resultado(True, fala, f"Arquivos: {', '.join(mudados)}. Backup: {backup}. Registro: {registro}")


def registrar(pedido: str, plano: str, mudados: list[str], situacao: str, backup: Path) -> Path:
    arquivo = pasta_trabalho() / "Mudancas" / _nome_de_arquivo(pedido)
    try:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(
            f"# {pedido.strip()}\n\nSituação: {situacao}\n\nBackup: {backup}\n\nArquivos: "
            f"{', '.join(mudados) or 'nenhum'}\n\n## Plano aprovado\n\n{plano.strip()}\n", encoding="utf-8")
    except OSError as erro:
        print(f"[Claude] Não consegui salvar o registro: {erro}")
    return arquivo


def _principal(argumentos: list[str]) -> int:
    """'python -m core.claude_chefe --desfazer-interrompida': o "Iniciar Jarvis Ultron" roda isto ANTES de
    abrir o Jarvis, porque uma mudança pela metade pode impedir até a tela de abrir. E antes até de
    instalar os componentes, porque ela pode ter mexido no requirements.txt (por isso aqui só o Python puro)."""
    if "--desfazer-interrompida" in argumentos:
        aviso = desfazer_interrompida()
        if aviso:
            try:
                print(aviso)
            except (OSError, UnicodeError):
                pass
    return 0


if __name__ == "__main__":
    sys.exit(_principal(sys.argv[1:]))
