"""Claude Code no PC do Erton como "chefe de tarefas" do Jarvis Ultron.

O Gemini (ou o Gemma) continua sendo a VOZ do Jarvis. Quando o pedido é grande — pesquisar a fundo,
analisar documentos, preparar relatórios, seguir um dos agentes, ou mudar o próprio código do
Jarvis — o Jarvis entrega para o Claude Code (o programa 'claude' instalado pelo "Instalar Claude"),
que usa a assinatura do Erton (Pro/Max), sem chave de API.

Travas (no código, não só nas instruções):
- Tarefas: o Claude só lê, pesquisa na internet e escreve DENTRO de Documentos/Jarvis Ultron/Claude.
  Não roda comandos no PC e não usa conectores (Gmail, Metricool, Agenda...), então não consegue
  publicar, enviar, comprar nem apagar nada.
- Código do Jarvis: primeiro o Claude só faz o PLANO (sem permissão para editar). O Jarvis conta o
  plano e só continua com o "ok" do Erton, conferido aqui, numa fala nova depois do plano. Antes de
  mexer: backup .zip e testes; depois: confere a sintaxe e roda os testes de novo. Se algo quebrar,
  o Jarvis desfaz sozinho, arquivo por arquivo.
- Modo privado (Gemma): nada vai para o Claude, porque ele roda na nuvem da Anthropic.
- A chave ANTHROPIC_API_KEY é tirada do ambiente: com ela o Claude cobraria pela API em vez de usar
  a assinatura. As chaves do Jarvis (Gemini, Groq...) também não vão para o Claude.

Ajustes no .env (opcionais): JARVIS_CLAUDE_EXE (caminho do claude.exe), JARVIS_CLAUDE_MODELO.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

TEMPO_TAREFA = 20 * 60    # uma tarefa do Claude pode levar alguns minutos
TEMPO_TESTES = 10 * 60
VALIDADE_PLANO = 15 * 60  # o "ok" vale para o plano contado nos últimos 15 minutos
MAX_TURNOS = 40

# Nunca disponíveis para o Claude chamado pelo Jarvis: comandos no PC (um script escreveria fora
# das pastas liberadas) e conectores (Gmail, Metricool... poderiam enviar ou publicar).
PROIBIDAS = ("Bash", "PowerShell", "NotebookEdit", "mcp__*")
LEITURA = ("Read", "Glob", "Grep", "WebSearch", "WebFetch", "Skill")
SEGREDOS_PREFIXOS = ("GEMINI_", "GROQ_", "ELEVENLABS_", "HERMES_", "OPENAI_", "GOOGLE_GENAI_",
                     "JARVIS_PONTE_", "TELEGRAM_", "METRICOOL_")
SEGREDOS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "GOOGLE_API_KEY")

# O que o Claude nunca lê nem muda na pasta do Jarvis (chaves e memória do Erton)
PROTEGIDOS = (".env", ".env.*", "config/api_keys.json", "config/ui_settings.json", "memory/**", ".git/**",
              ".github/**", ".claude/**")
CREDENCIAIS = (".claude/.credentials.json", ".ssh/**", ".aws/**", ".hermes/**", ".jarvis/**")
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
de {dados} (por exemplo clientes.txt, carteira.txt, a pasta Faturas)."""

REGRAS_PLANO = """
TAREFA: planejar uma mudança no código do próprio Jarvis Ultron (pasta atual). NÃO altere nada agora:
leia o código e escreva o PLANO: o que vai mudar, em quais arquivos, os riscos, e como testar.
Na linha "FALA:" resuma o plano em 2 frases simples (o Erton não é programador) e termine perguntando
se ele aprova. Não mexa em .env, chaves, memória nem na pasta .git."""

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


def achar_claude() -> str | None:
    """O claude.exe do instalador oficial; senão o do PATH (menos o Claude Desktop da Microsoft Store,
    que também se chama Claude.exe e abre a janela do app em vez do Claude Code)."""
    escolhido = os.environ.get("JARVIS_CLAUDE_EXE", "").strip().strip('"')
    if escolhido and Path(escolhido).is_file():
        return escolhido
    oficial = Path.home() / ".local" / "bin" / ("claude.exe" if sys.platform == "win32" else "claude")
    if oficial.is_file():
        return str(oficial)
    achado = shutil.which("claude")
    if achado and "windowsapps" not in achado.lower():
        return achado
    return None


def no_modo_privado() -> bool:
    from core.cerebro_gemma import cerebro_gemma

    return cerebro_gemma()


def ambiente() -> dict:
    """Ambiente do Claude: sem chave da API (senão cobra fora da assinatura) e sem as chaves do Jarvis."""
    env = {k: v for k, v in os.environ.items()
           if k.upper() not in SEGREDOS and not k.upper().startswith(SEGREDOS_PREFIXOS)}
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def regra_de_pasta(caminho: Path | str) -> str:
    """Caminho absoluto no formato das regras do Claude Code: C:\\Users\\X -> //c/Users/X."""
    texto = Path(caminho).resolve().as_posix()
    if re.match(r"^[A-Za-z]:/", texto):
        texto = "/" + texto[0].lower() + texto[2:]
    return "/" + texto


def _proibidas_na(pasta: Path) -> list[str]:
    regras = list(PROIBIDAS)
    for raiz in dict.fromkeys([regra_de_pasta(pasta), regra_de_pasta(pasta_jarvis())]):
        for item in PROTEGIDOS:
            regras += [f"Read({raiz}/{item})", f"Edit({raiz}/{item})"]
    return regras + [f"Read(~/{item})" for item in CREDENCIAIS]


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
    return pasta


def agentes() -> list[str]:
    raiz = pasta_jarvis() / "claude" / "skills"
    return sorted(p.parent.name for p in raiz.glob("*/SKILL.md"))


# ---------------- conversar com o Claude Code ----------------
def comando(exe: str, permitir, pasta: Path, sessao: str | None = None, turnos: int = MAX_TURNOS,
            pastas_extras=()) -> list[str]:
    """O pedido vai pela entrada padrão (não pela linha de comando), porque no Windows um claude.cmd
    estragaria textos com acentos, aspas ou '&'."""
    cmd = [exe, "-p", "--output-format", "json", "--permission-mode", "dontAsk", "--max-turns", str(turnos)]
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


def rodar(pedido: str, permitir, pasta: Path, sessao: str | None = None, tempo: float = TEMPO_TAREFA,
          turnos: int = MAX_TURNOS, pastas_extras=()) -> Resposta:
    exe = achar_claude()
    if not exe:
        return Resposta(False, erro="o Claude Code não está instalado. Dê dois cliques em 'Instalar Claude' "
                                    "na pasta do Jarvis")
    extra = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    try:
        feito = subprocess.run(comando(exe, permitir, pasta, sessao, turnos, pastas_extras), input=pedido.encode("utf-8"),
                               capture_output=True, timeout=tempo, cwd=str(pasta), env=ambiente(), **extra)
    except subprocess.TimeoutExpired:
        return Resposta(False, erro=f"o Claude passou de {int(tempo // 60)} minutos e eu parei a tarefa")
    except OSError as erro:
        return Resposta(False, erro=f"não consegui abrir o Claude Code: {erro}")
    saida = feito.stdout.decode("utf-8", "replace")
    problemas = feito.stderr.decode("utf-8", "replace")
    dados = _ler_json(saida)
    if dados is None:
        return Resposta(False, erro=explicar(problemas.strip() or saida.strip() or f"saída {feito.returncode}"))
    texto = str(dados.get("result") or "")
    negadas = list(dados.get("permission_denials") or [])
    if dados.get("is_error") or str(dados.get("subtype", "success")) != "success" or feito.returncode != 0:
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
    import unicodedata

    base = unicodedata.normalize("NFKD", texto.lower())
    base = "".join(c for c in base if not unicodedata.combining(c))
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:50] or "tarefa"
    return f"{datetime.now():%Y-%m-%d-%H%M}-{base}.md"


def salvar_relatorio(pedido: str, conteudo: str) -> Path | None:
    if len(conteudo.strip()) < 200:
        return None
    arquivo = pasta_trabalho() / "Relatorios" / _nome_de_arquivo(pedido)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(f"# {pedido.strip()}\n\n{conteudo.strip()}\n", encoding="utf-8")
    return arquivo


# ---------------- tarefas (pesquisa, análise, agentes) ----------------
def fazer_tarefa(pedido: str, agente: str | None = None, sessao: str | None = None) -> Resposta:
    pasta = preparar_pasta()
    texto = REGRAS + REGRAS_TAREFA.format(pasta=pasta, dados=pasta_dados())
    if agente:
        texto += (f"\nSiga as instruções do agente '{agente}' (arquivo .claude/skills/{agente}/SKILL.md "
                  "nesta pasta). Onde ele falar em publicar, enviar ou usar conectores, prepare só o rascunho.")
    texto += f"\n\nPEDIDO DO ERTON:\n{pedido.strip()}"
    permitir = [*LEITURA, f"Edit({regra_de_pasta(pasta)}/**)"]
    return rodar(texto, permitir, pasta, sessao=sessao, pastas_extras=[pasta_dados()])


# ---------------- código do Jarvis: plano -> ok -> backup -> testes -> aplica -> confere ----------------
def planejar(pedido: str) -> Resposta:
    pasta = pasta_jarvis()
    texto = REGRAS + REGRAS_PLANO + f"\n\nPEDIDO DO ERTON:\n{pedido.strip()}"
    return rodar(texto, LEITURA, pasta)  # sem Edit: no plano ele não consegue mudar nada


def _arquivos_de_codigo(pasta: Path):
    for raiz, pastas, arquivos in os.walk(pasta):
        pastas[:] = [p for p in pastas if p not in PASTAS_FORA and not p.startswith(".")]
        for nome in arquivos:
            if nome in ARQUIVOS_FORA or nome.startswith(".env") or nome.endswith((".pyc", ".zip", ".log")):
                continue
            caminho = Path(raiz) / nome
            try:
                if caminho.stat().st_size <= 5 * 1024 * 1024:
                    yield caminho.relative_to(pasta).as_posix(), caminho
            except OSError:
                continue


def fotografar(pasta: Path) -> dict[str, str]:
    """{arquivo: impressão digital} de tudo o que o Claude pode mudar."""
    foto = {}
    for nome, caminho in _arquivos_de_codigo(pasta):
        try:
            foto[nome] = hashlib.sha1(caminho.read_bytes()).hexdigest()
        except OSError:
            continue
    return foto


def fazer_backup(pasta: Path, foto: dict[str, str]) -> Path:
    destino = pasta_backups() / f"jarvis-antes-do-claude-{datetime.now():%Y%m%d-%H%M%S}.zip"
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zipado:
        for nome in foto:
            zipado.write(pasta / nome, nome)
    return destino


def restaurar(pasta: Path, backup: Path, antes: dict[str, str]) -> list[str]:
    """Volta cada arquivo mudado ao que era; apaga os que o Claude criou. Devolve o que mexeu."""
    depois = fotografar(pasta)
    mexidos = []
    with zipfile.ZipFile(backup) as zipado:
        for nome, impressao in antes.items():
            if depois.get(nome) != impressao:
                (pasta / nome).parent.mkdir(parents=True, exist_ok=True)
                (pasta / nome).write_bytes(zipado.read(nome))
                mexidos.append(nome)
    for nome in depois.keys() - antes.keys():
        try:
            (pasta / nome).unlink()
            mexidos.append(nome)
        except OSError:
            pass
    return mexidos


def mudancas(antes: dict[str, str], depois: dict[str, str]) -> list[str]:
    return sorted(n for n in antes.keys() | depois.keys() if antes.get(n) != depois.get(n))


def rodar_testes(pasta: Path, tempo: float = TEMPO_TESTES) -> set[str] | None:
    """Roda os testes do Jarvis. Devolve o conjunto de testes que falharam (None = não deu para rodar)."""
    if not (pasta / "tests").is_dir():
        return None
    env = ambiente()
    env.update(QT_QPA_PLATFORM="offscreen", JARVIS_UM_PROCESSO="1", JARVIS_ORBE_GPU="0")
    if importlib.util.find_spec("pytest") is not None:
        cmd = [sys.executable, "-m", "pytest", "tests", "-q", "-rfE", "-p", "no:cacheprovider"]
        falhou = re.compile(r"^(?:FAILED|ERROR) (\S+)", re.MULTILINE)
        terminou = re.compile(r"\d+ (?:passed|failed)")
    else:
        cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."]
        falhou = re.compile(r"^(?:FAIL|ERROR): (\S+ \([^)]+\))", re.MULTILINE)
        terminou = re.compile(r"^Ran \d+ tests?", re.MULTILINE)
    extra = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    try:
        feito = subprocess.run(cmd, cwd=str(pasta), env=env, capture_output=True, timeout=tempo, **extra)
    except (subprocess.TimeoutExpired, OSError):
        return None
    saida = feito.stdout.decode("utf-8", "replace") + "\n" + feito.stderr.decode("utf-8", "replace")
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


def aplicar_plano(plano: str, sessao: str | None, pedido: str) -> Resultado:
    pasta = pasta_jarvis()
    antes = fotografar(pasta)
    backup = fazer_backup(pasta, antes)
    falhas_antes = rodar_testes(pasta)

    permitir = [*LEITURA, f"Edit({regra_de_pasta(pasta)}/**)"]
    texto = REGRAS + REGRAS_APLICAR.format(plano=plano.strip())
    resposta = rodar(texto, permitir, pasta, sessao=sessao, turnos=MAX_TURNOS + 20)
    if not resposta.ok and sessao and "session" in resposta.erro.lower():
        resposta = rodar(texto, permitir, pasta, turnos=MAX_TURNOS + 20)  # a conversa do plano sumiu
    mudados = mudancas(antes, fotografar(pasta))

    def desfazer(motivo: str) -> Resultado:
        restaurar(pasta, backup, antes)
        sobrou = mudancas(antes, fotografar(pasta))
        fim = "" if not sobrou else f" Atenção: não consegui voltar {', '.join(sobrou)}; o backup está em {backup}."
        registro = registrar(pedido, plano, mudados, f"DESFEITO: {motivo}", backup)
        return Resultado(False, f"Desfiz a mudança porque {motivo}. O Jarvis ficou como estava.{fim}",
                         f"Registro: {registro}")

    if not resposta.ok:
        if mudados:
            return desfazer(f"o Claude parou no meio ({resposta.erro})")
        return Resultado(False, f"O Claude não conseguiu aplicar: {resposta.erro}.")
    if not mudados:
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

    registro = registrar(pedido, plano, mudados, f"APLICADO ({situacao})", backup)
    fala = (f"Pronto: o Claude mudou {len(mudados)} arquivo(s) e {situacao}. As mudanças valem quando você "
            f"reabrir o Jarvis. {resposta.fala}").strip()
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
