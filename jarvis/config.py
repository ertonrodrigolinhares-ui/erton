"""Configurações do Jarvis, lidas de variáveis de ambiente (ou de um arquivo .env)."""

import os
from dataclasses import dataclass


def _carregar_dotenv(caminho: str = ".env") -> None:
    """Carrega pares CHAVE=valor de um arquivo .env, sem sobrescrever o ambiente."""
    if not os.path.exists(caminho):
        return
    with open(caminho, encoding="utf-8") as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


@dataclass
class Config:
    nome_usuario: str
    palavra_ativacao: str
    modelo: str
    esforco: str
    idioma: str

    @classmethod
    def carregar(cls) -> "Config":
        _carregar_dotenv()
        return cls(
            nome_usuario=os.getenv("JARVIS_USUARIO", "Erton"),
            palavra_ativacao=os.getenv("JARVIS_PALAVRA_ATIVACAO", "jarvis").lower(),
            modelo=os.getenv("JARVIS_MODELO", "claude-opus-5"),
            esforco=os.getenv("JARVIS_ESFORCO", "medium"),
            idioma=os.getenv("JARVIS_IDIOMA", "pt-BR"),
        )
