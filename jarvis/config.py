"""Configurações do Jarvis, lidas de variáveis de ambiente (ou do arquivo .env)."""

import os
from dataclasses import dataclass
from pathlib import Path

# Pasta do usuário onde o Jarvis guarda configurações e arquivos. Fica fora da pasta do
# programa, para a chave não se perder quando você baixar uma versão nova do Jarvis.
PASTA_TRABALHO = Path.home() / "Documents" / "Jarvis"
ARQUIVO_ENV = PASTA_TRABALHO / "config.env"
# Um .env na pasta do projeto também é lido (útil para quem programa).
ENV_PROJETO = Path(__file__).resolve().parent.parent / ".env"

NOME_CHAVE = {"gemini": "GEMINI_API_KEY", "claude": "ANTHROPIC_API_KEY"}
SITE_CHAVE = {
    "gemini": "https://aistudio.google.com/apikey",
    "claude": "https://console.anthropic.com/settings/keys",
}


def _carregar_dotenv() -> None:
    """Carrega pares CHAVE=valor dos arquivos de configuração, sem sobrescrever o ambiente."""
    for arquivo in (ENV_PROJETO, ARQUIVO_ENV):
        if not arquivo.exists():
            continue
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


def salvar_no_env(chave: str, valor: str) -> None:
    """Grava (ou atualiza) CHAVE=valor no arquivo de configuração e no ambiente atual."""
    ARQUIVO_ENV.parent.mkdir(parents=True, exist_ok=True)
    linhas = ARQUIVO_ENV.read_text(encoding="utf-8").splitlines() if ARQUIVO_ENV.exists() else []
    linhas = [l for l in linhas if not l.strip().startswith(f"{chave}=")]
    linhas.append(f"{chave}={valor}")
    ARQUIVO_ENV.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    os.environ[chave] = valor


@dataclass
class Config:
    nome_usuario: str
    palavra_ativacao: str
    ia: str
    gemini_modelo: str
    claude_modelo: str
    claude_esforco: str
    idioma: str

    @classmethod
    def carregar(cls) -> "Config":
        _carregar_dotenv()
        ia = os.getenv("JARVIS_IA", "gemini").lower()
        return cls(
            nome_usuario=os.getenv("JARVIS_USUARIO", "Erton"),
            palavra_ativacao=os.getenv("JARVIS_PALAVRA_ATIVACAO", "jarvis").lower(),
            ia=ia if ia in NOME_CHAVE else "gemini",
            gemini_modelo=os.getenv("JARVIS_GEMINI_MODELO", "gemini-flash-latest"),
            claude_modelo=os.getenv("JARVIS_CLAUDE_MODELO", "claude-opus-5"),
            claude_esforco=os.getenv("JARVIS_CLAUDE_ESFORCO", "medium"),
            idioma=os.getenv("JARVIS_IDIOMA", "pt-BR"),
        )

    @property
    def nome_chave(self) -> str:
        return NOME_CHAVE[self.ia]

    @property
    def site_chave(self) -> str:
        return SITE_CHAVE[self.ia]

    @property
    def chave_api(self) -> str:
        return os.getenv(self.nome_chave, "").strip()
