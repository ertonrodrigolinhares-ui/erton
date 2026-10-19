"""Confere se alguma mudança fez falhar um teste que passava.

Uso, na pasta do Jarvis:  python dev/conferir_testes.py
(--todas mostra também a lista completa das falhas desta rodada, para comparar rodadas.)

Roda a suíte inteira com uma "pasta do usuário" temporária (HOME, USERPROFILE, APPDATA e
LOCALAPPDATA): assim os testes não mexem no tema, nos Documentos nem nas configurações do Erton. Depois
compara as falhas com a lista de tests/dados/falhas_conhecidas.txt e responde só "nenhuma falha nova"
ou a lista das novas. A sentinela (tests/test_sentinela.py) roda junto: se algum teste mexer no .env,
nas chaves, na memória ou no tmp/ da pasta do Jarvis, ela aparece como falha nova.

Um teste anotado como instável que falhar roda de novo, sozinho e na mesma pasta temporária, até 3
vezes: se passar numa delas, foi a oscilação de sempre e não conta; se falhar em todas, é falha nova.

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
REPETIR = 3  # vezes que um instável que falhou roda de novo, sozinho
COMANDO = [sys.executable, "-m", "pytest", "-q", "-p", "no:warnings", "-p", "no:cacheprovider", "-rfE"]
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


def ambiente(casa: Path) -> dict[str, str]:
    """As variáveis para o pytest, com a "pasta do usuário" na pasta temporária casa."""
    for sub in ("AppData/Roaming", "AppData/Local", "Documents"):
        (casa / sub).mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.setdefault("PYTHONUSERBASE", site.getuserbase())  # os pacotes instalados no usuário continuam achados
    env.update(QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8", HOME=str(casa), USERPROFILE=str(casa),
               APPDATA=str(casa / "AppData" / "Roaming"), LOCALAPPDATA=str(casa / "AppData" / "Local"))
    return env


def rodar_pytest(alvos: list[str], env: dict[str, str]) -> set[str] | None:
    """Roda os testes dos alvos e devolve o conjunto dos que falharam (None = não deu para rodar)."""
    try:
        feito = subprocess.run(COMANDO + alvos, cwd=RAIZ, env=env, capture_output=True, timeout=TEMPO_LIMITE)
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


def instaveis_que_sempre_falham(oscilaram, rodar, vezes: int = REPETIR) -> list[str]:
    """Roda de novo, sozinho, cada instável que falhou. Os que falham em todas as vezes não são a
    oscilação de sempre (o brilho do anel logo abaixo do limite): eles contam como falha nova. Se não
    der para rodar, também conta (na dúvida, o alarme toca)."""
    sempre = []
    for nome in oscilaram:
        for _ in range(vezes):
            falhas = rodar([nome])
            if falhas is not None and nome not in falhas:
                break  # passou: foi só a oscilação
        else:
            sempre.append(nome)
    return sempre


def main(argumentos: list[str]) -> int:
    fixas, instaveis = ler_conhecidas()
    with tempfile.TemporaryDirectory(prefix="jarvis-casa-testes-", ignore_cleanup_errors=True) as casa:
        env = ambiente(Path(casa))
        falhas = rodar_pytest(["tests"], env)
        if falhas is None:
            return 2
        oscilaram = sorted(falhas & instaveis)
        sempre = instaveis_que_sempre_falham(oscilaram, lambda alvos: rodar_pytest(alvos, env))
    novas = sorted((falhas - fixas - instaveis) | set(sempre))
    if "--todas" in argumentos:
        print(f"Falhas desta rodada ({len(falhas)}):")
        print("\n".join(f"  {nome}" for nome in sorted(falhas)))
    if novas:
        print(f"{len(novas)} falha(s) nova(s):")
        print("\n".join(f"  {nome}" + (f" (instável, mas falhou também nas {REPETIR} vezes que rodou de novo)"
                                         if nome in sempre else "") for nome in novas))
    else:
        print("nenhuma falha nova")
    passaram = [nome for nome in oscilaram if nome not in sempre]
    if passaram:  # não contam como novas, mas ficam à vista
        print(f"(instáveis que falharam desta vez e passaram ao rodar de novo, não contam: {', '.join(passaram)})")
    sumiram = sorted(fixas - falhas)
    if sumiram:  # bom sinal, mas confira: a lista de conhecidas só muda de propósito, numa etapa
        print(f"({len(sumiram)} falha(s) conhecida(s) passaram a funcionar; se foi de propósito, tire-as do "
              f"{CONHECIDAS.name})")
    return 1 if novas else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
