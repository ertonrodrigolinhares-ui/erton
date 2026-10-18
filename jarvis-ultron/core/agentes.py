"""Agentes do Jarvis Ultron: quais estão LIGADOS (eles viram botões no painel Ultron).

Os agentes ficam em claude/skills/<nome>/SKILL.md e rodam no Claude (claude_task com agent=<nome>).
A lista dos ligados fica em Documentos/Jarvis Ultron/agentes_ligados.txt, um nome por linha. Quem
liga e desliga: o "Ativar Agentes" (na pasta do Jarvis) ou estas funções.
"""

from __future__ import annotations

import re
from pathlib import Path

EMOJIS = {
    "agenda-inteligente": "📅", "agente-provas": "🏁", "briefing-diario": "☀️", "clientes-grupos": "👥",
    "conteudo-atleta": "📸", "controle-gastos": "💳", "email-triagem": "📧", "holding-sucessao": "🏛️",
    "investimentos": "📈", "legislacao": "⚖️", "linkedin-lideranca": "💼", "noticias-setor": "📰",
    "nutricao-recuperacao": "🥗", "prazos-fiscais": "🗓️", "proposta-comercial": "📝", "relatorio-mensal": "📊",
    "respostas-redes": "💬", "resumo-reuniao": "🗒️", "rotina-atleta-8h": "⏱️", "treinador-dados": "🏊",
    "treino-semana": "🚴", "viagens": "✈️",
}
NOMES_CURTOS = {
    "agenda-inteligente": "Agenda", "agente-provas": "Provas", "briefing-diario": "Briefing",
    "clientes-grupos": "Clientes", "conteudo-atleta": "Conteúdo", "controle-gastos": "Gastos",
    "email-triagem": "E-mails", "holding-sucessao": "Holding", "investimentos": "Investimentos",
    "legislacao": "Legislação", "linkedin-lideranca": "LinkedIn", "noticias-setor": "Notícias",
    "nutricao-recuperacao": "Nutrição", "prazos-fiscais": "Prazos", "proposta-comercial": "Proposta",
    "relatorio-mensal": "Relatório", "respostas-redes": "Respostas", "resumo-reuniao": "Reunião",
    "rotina-atleta-8h": "Rotina 8h", "treinador-dados": "Treinador", "treino-semana": "Treino",
    "viagens": "Viagens",
}


def pasta_agentes() -> Path:
    return Path(__file__).resolve().parents[1] / "claude" / "skills"


def arquivo_ligados() -> Path:
    return Path.home() / "Documents" / "Jarvis Ultron" / "agentes_ligados.txt"


def _descricao(skill: Path) -> str:
    try:
        texto = skill.read_text(encoding="utf-8")
    except OSError:
        return ""
    achado = re.search(r'^description:\s*"?(.*?)"?\s*$', texto, re.MULTILINE)
    return achado.group(1).strip() if achado else ""


def todos() -> list[dict]:
    """Todos os agentes que existem: [{nome, titulo, curto, emoji, descricao}]."""
    saida = []
    for skill in sorted(pasta_agentes().glob("*/SKILL.md")):
        nome = skill.parent.name
        descricao = _descricao(skill)
        titulo = descricao.split(":", 1)[0].strip() if ":" in descricao[:60] else nome.replace("-", " ").capitalize()
        resumo = descricao.split(":", 1)[1].strip() if ":" in descricao[:60] else descricao
        saida.append({"nome": nome, "titulo": titulo, "curto": NOMES_CURTOS.get(nome, titulo[:12]),
                      "emoji": EMOJIS.get(nome, "🤖"), "descricao": resumo})
    return saida


def ligados() -> list[str]:
    """Nomes dos agentes ligados (na ordem em que foram ligados), só os que existem."""
    try:
        linhas = arquivo_ligados().read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return []
    existentes = {a["nome"] for a in todos()}
    vistos = []
    for linha in linhas:
        nome = linha.strip()
        if nome in existentes and nome not in vistos:
            vistos.append(nome)
    return vistos


def _gravar(nomes: list[str]) -> None:
    arquivo = arquivo_ligados()
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text("".join(f"{n}\n" for n in nomes), encoding="utf-8")


def ligar(nome: str) -> bool:
    if nome not in {a["nome"] for a in todos()}:
        return False
    atuais = ligados()
    if nome not in atuais:
        _gravar(atuais + [nome])
    return True


def desligar(nome: str) -> bool:
    atuais = ligados()
    if nome not in atuais:
        return False
    _gravar([n for n in atuais if n != nome])
    return True


def botoes_dos_ligados() -> list[tuple]:
    """Botões do painel Ultron para os agentes ligados: (ferramenta, emoji, título, subtítulo, args)."""
    por_nome = {a["nome"]: a for a in todos()}
    botoes = []
    for nome in ligados():
        a = por_nome[nome]
        sub = a["descricao"] if len(a["descricao"]) <= 42 else a["descricao"][:40].rstrip() + "…"
        pedido = (f"Rode agora o agente {nome}, seguindo o SKILL.md dele, com o que estiver disponível, e me "
                  "traga o resultado. Se faltar alguma informação, diga o que falta.")
        botoes.append(("claude_task", a["emoji"], a["titulo"], sub, {"request": pedido, "agent": nome}))
    return botoes
