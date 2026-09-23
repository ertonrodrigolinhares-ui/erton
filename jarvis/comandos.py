"""Comandos locais do Jarvis: respondidos na hora, sem precisar da IA.

Cada comando recebe o texto do usuário e devolve a resposta, ou None se não se aplica.
Para criar um novo comando, escreva a função e adicione-a em COMANDOS.
"""

import ast
import operator
import random
import re
import unicodedata
import urllib.parse
import webbrowser
from datetime import datetime

DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
               "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]

SITES = {
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "whatsapp": "https://web.whatsapp.com",
    "linkedin": "https://www.linkedin.com",
    "instagram": "https://www.instagram.com",
    "agenda": "https://calendar.google.com",
    "drive": "https://drive.google.com",
    "receita federal": "https://www.gov.br/receitafederal",
    "e-cac": "https://cav.receita.fazenda.gov.br",
}

PIADAS = [
    "Por que o contador foi ao médico? Porque estava com o balanço desequilibrado.",
    "O que o zero disse para o oito? Belo cinto!",
    "Por que o livro de matemática estava triste? Porque tinha muitos problemas.",
    "Qual é o triatleta mais organizado? O que faz transição sem perder nada no caminho.",
]


def normalizar(texto: str) -> str:
    """Minúsculas e sem acentos, para facilitar a comparação."""
    texto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in texto if not unicodedata.combining(c)).strip()


def cmd_hora(texto: str, agora: datetime | None = None) -> str | None:
    if not re.search(r"\b(que horas|horas sao|hora atual|me diga a hora)\b", texto):
        return None
    agora = agora or datetime.now()
    return f"Agora são {agora.hour} horas e {agora.minute:02d} minutos."


def cmd_data(texto: str, agora: datetime | None = None) -> str | None:
    if not re.search(r"\b(que dia|data de hoje|qual a data|dia e hoje)\b", texto):
        return None
    agora = agora or datetime.now()
    return (f"Hoje é {DIAS_SEMANA[agora.weekday()]}, {agora.day} de "
            f"{MESES[agora.month - 1]} de {agora.year}.")


def cmd_abrir_site(texto: str) -> str | None:
    if not texto.startswith("abr"):
        return None
    for nome, url in SITES.items():
        if normalizar(nome) in texto:
            webbrowser.open(url)
            return f"Abrindo {nome}."
    return None


def cmd_pesquisar(texto: str) -> str | None:
    """Só abre o navegador quando o pedido cita o site ("pesquise no google ...").
    Outras pesquisas ficam com a IA, que busca na internet e resume."""
    correspondencia = re.match(r"(pesquis\w*|procur\w*|busc\w*)\s+no\s+(google|youtube)\s+(por\s+)?(.+)", texto)
    if not correspondencia:
        return None
    termo = correspondencia.group(4).strip()
    if correspondencia.group(2) == "youtube":
        webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote(termo))
        return f"Pesquisando {termo} no YouTube."
    webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(termo))
    return f"Pesquisando {termo} no Google."


_OPERADORES = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _avaliar(no: ast.AST) -> float:
    """Avalia com segurança apenas expressões aritméticas (nada de eval)."""
    if isinstance(no, ast.Expression):
        return _avaliar(no.body)
    if isinstance(no, ast.Constant) and isinstance(no.value, (int, float)):
        return no.value
    if isinstance(no, ast.BinOp) and type(no.op) in _OPERADORES:
        if isinstance(no.op, ast.Pow) and abs(_avaliar(no.right)) > 100:
            raise ValueError("expoente grande demais")
        return _OPERADORES[type(no.op)](_avaliar(no.left), _avaliar(no.right))
    if isinstance(no, ast.UnaryOp) and type(no.op) in _OPERADORES:
        return _OPERADORES[type(no.op)](_avaliar(no.operand))
    raise ValueError("expressão não suportada")


def cmd_calcular(texto: str) -> str | None:
    correspondencia = re.match(r"(calcul\w*|quanto e|quanto da)\s+(.+)", texto)
    if not correspondencia:
        return None
    expressao = correspondencia.group(2).rstrip("?")
    for palavra, simbolo in [("vezes", "*"), ("x", "*"), ("dividido por", "/"),
                             ("mais", "+"), ("menos", "-"), ("elevado a", "**"), (",", ".")]:
        expressao = re.sub(rf"(?<![a-z]){re.escape(palavra)}(?![a-z])", f" {simbolo} ", expressao)
    try:
        resultado = _avaliar(ast.parse(expressao, mode="eval"))
    except (SyntaxError, ValueError, ZeroDivisionError):
        return None  # deixa a IA tentar entender
    if isinstance(resultado, float) and resultado.is_integer():
        resultado = int(resultado)
    elif isinstance(resultado, float):
        resultado = round(resultado, 4)
    return f"O resultado é {str(resultado).replace('.', ',')}."


def cmd_piada(texto: str) -> str | None:
    if "piada" not in texto:
        return None
    return random.choice(PIADAS)


COMANDOS = [cmd_hora, cmd_data, cmd_abrir_site, cmd_pesquisar, cmd_calcular, cmd_piada]


def executar(texto: str) -> str | None:
    """Tenta cada comando local; devolve a primeira resposta encontrada."""
    texto = normalizar(texto)
    for comando in COMANDOS:
        resposta = comando(texto)
        if resposta:
            return resposta
    return None
