"""Sentinela: falha se algum teste mexer nos dados do Erton.

Os testes nunca podem gravar no .env, nas configurações e chaves (config/*.json), na memória
(memory/*.json) nem no tmp/ de verdade. A foto desses arquivos é tirada quando este arquivo é carregado
(o tests/conftest.py o carrega antes de todos os outros testes) e conferida no fim (o conftest põe a
sentinela por último). Rodando com "python -m unittest", ela confere só os testes que vieram antes dela.

Se ela falhar, o teste culpado tem de usar uma pasta temporária (veja o test_hosted_api e o
_historico_temporario do test_presentation_maker). Com o Jarvis aberto nesta mesma pasta, ele mesmo
grava na memória e no tmp/: feche o Jarvis antes de rodar os testes."""

import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def foto_dos_dados(raiz: Path = RAIZ) -> dict[str, tuple[int, int]]:
    """{arquivo: (tamanho, data da última mudança)} dos dados do Erton. As pastas do tmp/ entram com
    (-1, 0): assim uma pasta criada ou apagada também aparece."""
    caminhos = [raiz / ".env", *(raiz / "config").glob("*.json"), *(raiz / "memory").glob("*.json")]
    tmp = raiz / "tmp"
    if tmp.exists():
        caminhos += [tmp, *tmp.rglob("*")]
    foto = {}
    for caminho in caminhos:
        try:
            info = caminho.stat()
        except OSError:
            continue  # não existe (ou sumiu no meio da leitura)
        nome = caminho.relative_to(raiz).as_posix()
        foto[nome] = (-1, 0) if caminho.is_dir() else (info.st_size, info.st_mtime_ns)
    return foto


def mexidos(antes: dict, depois: dict) -> list[str]:
    """Os arquivos criados, apagados ou alterados entre as duas fotos."""
    return sorted(nome for nome in antes.keys() | depois.keys() if antes.get(nome) != depois.get(nome))


FOTO_ANTES = foto_dos_dados()  # tirada ao carregar, antes de qualquer teste rodar


class SentinelaTests(unittest.TestCase):
    def test_a_foto_percebe_cada_tipo_de_mudanca(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            for sub in ("config", "memory", "tmp/sub"):
                (raiz / sub).mkdir(parents=True)
            for nome in (".env", "config/api_keys.json", "memory/task_history.json", "tmp/sub/banco.db"):
                (raiz / nome).write_text("1", encoding="utf-8")
            (raiz / "config" / "__init__.py").write_text("", encoding="utf-8")  # código não conta
            antes = foto_dos_dados(raiz)
            self.assertEqual(mexidos(antes, foto_dos_dados(raiz)), [])
            (raiz / ".env").write_text("22", encoding="utf-8")
            (raiz / "config" / "api_keys.json").unlink()
            (raiz / "memory" / "long_term.json").write_text("{}", encoding="utf-8")
            (raiz / "tmp" / "sub" / "banco.db").write_text("22", encoding="utf-8")
            (raiz / "tmp" / "nova").mkdir()
            (raiz / "config" / "__init__.py").write_text("# mudou", encoding="utf-8")
            self.assertEqual(mexidos(antes, foto_dos_dados(raiz)),
                             [".env", "config/api_keys.json", "memory/long_term.json",
                              "tmp/nova", "tmp/sub/banco.db"])

    def test_nenhum_teste_mexeu_nos_dados_do_erton(self):
        mudou = mexidos(FOTO_ANTES, foto_dos_dados())
        self.assertEqual(mudou, [], "Algum teste mexeu nos dados do Erton (o teste culpado tem de usar uma "
                                    "pasta temporária; se o Jarvis estiver aberto nesta pasta, feche-o): "
                                    + ", ".join(mudou))


if __name__ == "__main__":
    unittest.main()
