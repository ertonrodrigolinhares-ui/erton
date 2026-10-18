"""Gera claude/agency/INDICE.md: a lista dos agentes da coleção agency-agents (uma linha por agente).

O Claude lê esse índice quando um pedido precisa de um especialista e então abre só o arquivo do agente
escolhido. Rode de novo sempre que trocar os arquivos de claude/agency:

    python scripts/gerar_indice_agency.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PASTA = Path(__file__).resolve().parents[1] / "claude" / "agency"
TAMANHO_DESCRICAO = 160

CABECALHO = """# Agentes especialistas (coleção agency-agents)

Fonte: https://github.com/msitarzewski/agency-agents (licença MIT, veja LICENSE nesta pasta).
Os agentes estão em inglês e foram escritos para outros países. Ao usar um deles:
- responda sempre em português do Brasil;
- impostos, leis e regras trabalhistas são as do Brasil, não as do agente;
- as regras do Jarvis valem acima das do agente (nunca publique, envie, compre nem apague nada).

Para usar: escolha o agente pela linha abaixo e leia o arquivo dele (caminho a partir da pasta Agency).
Formato: `caminho` — Nome: para que serve.
"""


def ler_cabecalho(arquivo: Path) -> dict[str, str]:
    """Lê name e description do bloco --- ... --- do começo do arquivo."""
    linhas = arquivo.read_text(encoding="utf-8").splitlines()
    if not linhas or linhas[0].strip() != "---":
        return {}
    campos: dict[str, str] = {}
    for linha in linhas[1:]:
        if linha.strip() == "---":
            break
        chave, _, valor = linha.partition(":")
        if chave in ("name", "description") and valor:
            campos[chave] = valor.strip().strip('"').strip("'")
    return campos


def curto(texto: str) -> str:
    texto = " ".join(texto.split())
    if len(texto) <= TAMANHO_DESCRICAO:
        return texto
    return texto[:TAMANHO_DESCRICAO].rsplit(" ", 1)[0] + "…"


def gerar(pasta: Path = PASTA) -> str:
    partes = [CABECALHO]
    for divisao in sorted(p for p in pasta.iterdir() if p.is_dir()):
        linhas = []
        for arquivo in sorted(divisao.rglob("*.md")):
            campos = ler_cabecalho(arquivo)
            if "name" not in campos:
                continue
            caminho = arquivo.relative_to(pasta).as_posix()
            linhas.append(f"- `{caminho}` — {campos['name']}: {curto(campos.get('description', ''))}")
        if linhas:
            partes.append(f"\n## {divisao.name} ({len(linhas)})\n")
            partes.extend(linhas)
    return "\n".join(partes) + "\n"


def main() -> int:
    texto = gerar()
    (PASTA / "INDICE.md").write_text(texto, encoding="utf-8")
    print(f"INDICE.md: {texto.count(chr(10) + '- `')} agentes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
