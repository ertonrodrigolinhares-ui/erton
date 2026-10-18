"""Confere se alguma mudança fez falhar um teste que passava.

Uso, na pasta do Jarvis:  python dev/conferir_testes.py
(--todas mostra também a lista completa das falhas desta rodada, para comparar rodadas.)

Roda a suíte inteira com uma "pasta do usuário" temporária (HOME, USERPROFILE, APPDATA e
LOCALAPPDATA): assim os testes não mexem no tema, nos Documentos nem nas configurações do Erton. Depois
compara as falhas com a lista de tests/dados/falhas_conhecidas.txt e responde só "nenhuma falha nova"
ou a lista das novas. A sentinela (tests/test_sentinela.py) roda junto: se algum teste mexer no .env,
nas chaves, na memória ou no tmp/ da pasta do Jarvis, ela aparece como falha nova.

Feche o Jarvis antes: aberto nesta mesma pasta, ele grava na memória e no tmp/ e a sentinela acusa.

Sai com 0 (nenhuma falha nova), 1 (há falhas novas) ou 2 (não deu para rodar os testes)."""

from __future__ import annotations

import os
import re
import site
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CONHECIDAS = RAIZ / "tests" / "dados" / "falhas_conhecidas.txt"
TEMPO_LIMITE = 1800  # segundos; a suíte leva poucos minutos
INSTAVEL = "instavel:"
COMANDO = [sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:warnings", "-p", "no:cacheprovider", "-rfE"]
FALHOU = re.compile(r"^(?:FAILED|ERROR) (\S+)", re.MULTILINE)
TERMINOU = re.compile(r"\d+ (?:passed|failed)")


def ler_conhecidas(arquivo: Path = CONHECIDAS) -> tuple[set[str], set[str]]:
    """(falhas conhecidas, instáveis). Linhas com # são comentário; "instavel: X" = às vezes falha."""
    fixas, instaveis = set(), set()
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        if linha.startswith(INSTAVEL):
            instaveis.add(linha[len(INSTAVEL):].strip())
        else:
            fixas.add(linha)
    return fixas, instaveis


def rodar_suite() -> set[str] | None:
    """Roda os testes e devolve o conjunto dos que falharam (None = não deu para rodar)."""
    with tempfile.TemporaryDirectory(prefix="jarvis-casa-testes-", ignore_cleanup_errors=True) as casa:
        casa = Path(casa)
        for sub in ("AppData/Roaming", "AppData/Local", "Documents"):
            (casa / sub).mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env.setdefault("PYTHONUSERBASE", site.getuserbase())  # os pacotes instalados no usuário continuam achados
        env.update(QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8", HOME=str(casa), USERPROFILE=str(casa),
                   APPDATA=str(casa / "AppData" / "Roaming"), LOCALAPPDATA=str(casa / "AppData" / "Local"))
        try:
            feito = subprocess.run(COMANDO, cwd=RAIZ, env=env, capture_output=True, timeout=TEMPO_LIMITE)
        except (subprocess.TimeoutExpired, OSError) as erro:
            print(f"Não deu para rodar os testes: {erro}")
            return None
    saida = feito.stdout.decode("utf-8", "replace") + "\n" + feito.stderr.decode("utf-8", "replace")
    if not TERMINOU.search(saida):
        print("Os testes não chegaram ao fim. Final da saída:\n" + saida[-3000:])
        return None
    # só o resumo do fim: um print de algum teste começando por "ERROR " não vira falha
    resumo = saida.split("short test summary info")[-1] if "short test summary info" in saida else ""
    return set(FALHOU.findall(resumo))


def main(argumentos: list[str]) -> int:
    fixas, instaveis = ler_conhecidas()
    falhas = rodar_suite()
    if falhas is None:
        return 2
    novas = sorted(falhas - fixas - instaveis)
    if "--todas" in argumentos:
        print(f"Falhas desta rodada ({len(falhas)}):")
        print("\n".join(f"  {nome}" for nome in sorted(falhas)))
    if novas:
        print(f"{len(novas)} falha(s) nova(s):")
        print("\n".join(f"  {nome}" for nome in novas))
    else:
        print("nenhuma falha nova")
    oscilaram = sorted(falhas & instaveis)
    if oscilaram:  # não contam como novas, mas ficam à vista
        print(f"(instáveis que falharam desta vez, não contam: {', '.join(oscilaram)})")
    sumiram = sorted(fixas - falhas)
    if sumiram:  # bom sinal, mas confira: a lista de conhecidas só muda de propósito, numa etapa
        print(f"({len(sumiram)} falha(s) conhecida(s) passaram a funcionar; se foi de propósito, tire-as do "
              f"{CONHECIDAS.name})")
    return 1 if novas else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
