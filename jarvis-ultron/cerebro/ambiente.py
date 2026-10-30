"""Onde o Jarvis Ultron está: a pasta do programa e os caminhos fixos (um pedaço do cérebro).

Etapa 15 da reorganização: estes nomes saíram do main.py (que continua oferecendo-os para quem usa
main.X). Na Etapa 16 o preparo feito ao importar o main (.env, Studio/Vertex e central de modelos) vem
para cá como preparar_ambiente(). Nada aqui lê o ambiente ao ser importado."""

import sys
from pathlib import Path


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[1]  # a pasta do Jarvis (cerebro/ fica um nível abaixo)


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
