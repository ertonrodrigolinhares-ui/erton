"""Gera os índices dos especialistas da coleção agency-agents (pasta claude/agency).

- claude/agency/INDICE.md: só as áreas (uma linha cada), para o Claude escolher por onde ir;
- claude/agency/<área>/INDICE.md: os agentes daquela área (uma linha por agente).

Assim o Claude lê poucas linhas em vez da lista inteira. Rode de novo sempre que trocar os arquivos
de claude/agency:

    python scripts/gerar_indice_agency.py
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from core.claude_chefe import campo_no_cabecalho  # noqa: E402  (o mesmo leitor que o Jarvis usa)

PASTA = RAIZ / "claude" / "agency"
TAMANHO_DESCRICAO = 160

# O que cada área tem, em português (as áreas que não estiverem aqui aparecem só com o nome).
AREAS = {
    "academic": "pesquisa acadêmica: história, geografia, psicologia, estatística, narrativa",
    "design": "marca, identidade visual, interface, imagens geradas por IA",
    "engineering": "programação: sites, apps, dados, nuvem, IA (aqui só servem para explicar e planejar)",
    "finance": "contabilidade, análise financeira, orçamento, investimentos, impostos (regras dos EUA)",
    "game-development": "criação de jogos",
    "gis": "mapas e geoprocessamento",
    "healthcare": "saúde: atendimento e conformidade",
    "marketing": "conteúdo, redes sociais (LinkedIn, Instagram, YouTube...), SEO, e-mail, imprensa",
    "paid-media": "anúncios pagos (Google, Meta...)",
    "product": "gestão de produto, pesquisa com usuários, priorização",
    "project-management": "projetos, prazos, atas de reunião, operações",
    "research": "pesquisa aprofundada",
    "sales": "vendas, propostas, negociação, funil",
    "security": "segurança da informação e conformidade (SOC 2, ISO 27001...)",
    "spatial-computing": "realidade virtual e aumentada",
    "specialized": "negócios em geral: chefe de gabinete, CFO, M&A, jurídico, RH, estratégia, mentoria",
    "support": "atendimento, relatórios executivos, finanças do dia a dia, conformidade",
    "testing": "testes e qualidade de software",
}

CABECALHO = """# Agentes especialistas (coleção agency-agents)

Fonte: https://github.com/msitarzewski/agency-agents (licença MIT, veja LICENSE nesta pasta).
Os agentes estão em inglês e foram escritos para outros países. Ao usar um deles:
- responda sempre em português do Brasil;
- impostos, leis e regras trabalhistas são as do Brasil, não as do agente;
- as regras do Jarvis valem acima das do agente (nunca publique, envie, compre nem apague nada).

Como usar: escolha a área abaixo, leia o INDICE.md dela, escolha o agente e leia o arquivo dele.
"""


def _curto(texto: str) -> str:
    texto = " ".join(texto.split())
    if len(texto) <= TAMANHO_DESCRICAO:
        return texto
    return texto[:TAMANHO_DESCRICAO].rsplit(" ", 1)[0] + "…"


def _agentes_da_area(area: Path) -> list[str]:
    linhas = []
    for arquivo in sorted(area.rglob("*.md")):
        if arquivo.name == "INDICE.md":
            continue
        texto = arquivo.read_text(encoding="utf-8")
        nome = campo_no_cabecalho(texto, "name")
        if not nome:
            continue
        descricao = _curto(campo_no_cabecalho(texto, "description") or "")
        linhas.append(f"- `{arquivo.relative_to(area.parent).as_posix()}` — {nome}: {descricao}")
    return linhas


def gerar(pasta: Path = PASTA) -> dict[str, str]:
    """{caminho do índice (a partir de pasta): texto}."""
    indices: dict[str, str] = {}
    principal = [CABECALHO, "Formato: `índice da área` — quantos agentes — o que tem.\n"]
    for area in sorted(p for p in pasta.iterdir() if p.is_dir()):
        linhas = _agentes_da_area(area)
        if not linhas:
            continue
        sobre = AREAS.get(area.name, area.name)
        principal.append(f"- `{area.name}/INDICE.md` — {len(linhas)} agente{'s' if len(linhas) != 1 else ''} — {sobre}")
        indices[f"{area.name}/INDICE.md"] = (
            f"# Especialistas: {area.name} ({sobre})\n\n"
            "Caminhos a partir da pasta Agency. Formato: `arquivo` — Nome: para que serve.\n\n"
            + "\n".join(linhas) + "\n")
    indices["INDICE.md"] = "\n".join(principal) + "\n"
    return indices


def main() -> int:
    indices = gerar()
    for caminho, texto in indices.items():
        (PASTA / caminho).write_text(texto, encoding="utf-8")
    total = sum(t.count("\n- `") for c, t in indices.items() if c != "INDICE.md")
    print(f"{len(indices)} índices, {total} agentes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
