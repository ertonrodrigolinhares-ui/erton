import json
from types import SimpleNamespace

import groq
import httpx
import pytest

from jarvis import cerebro_groq, config
from jarvis.cerebro_groq import CerebroGroq, esquema_ferramenta
from jarvis.ia import CerebroComReserva
from jarvis.ia_base import IAIndisponivel


def _resposta(texto=None, chamadas=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=texto, tool_calls=chamadas))])


def _chamada(id_, nome, argumentos):
    return SimpleNamespace(id=id_, function=SimpleNamespace(name=nome, arguments=json.dumps(argumentos)))


class GroqFalso:
    roteiro = []
    pedidos = []

    def __init__(self, **_):
        self.models = SimpleNamespace(list=lambda: SimpleNamespace(
            data=[SimpleNamespace(id="llama-3.3-70b-versatile"), SimpleNamespace(id="llama-3.1-8b-instant")]))
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._criar))

    def _criar(self, **pedido):
        GroqFalso.pedidos.append(json.loads(json.dumps(pedido, default=str)))
        proximo = GroqFalso.roteiro.pop(0)
        if isinstance(proximo, Exception):
            raise proximo
        return proximo


@pytest.fixture
def groq_falso(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PASTA_TRABALHO", tmp_path)
    monkeypatch.setattr(cerebro_groq.groq, "Groq", GroqFalso)
    GroqFalso.roteiro, GroqFalso.pedidos = [], []
    return GroqFalso


def _erro(classe, codigo):
    resposta = httpx.Response(codigo, request=httpx.Request("POST", "https://api.groq.com"))
    return classe("erro", response=resposta, body=None)


def test_esquema_no_formato_json_schema():
    def criar_planilha(arquivo: str, linhas: list[list[str]], aba: str = "Planilha1") -> str:
        """Cria uma planilha.

        Args:
          arquivo: nome.
          linhas: dados.
          aba: aba.
        """
        return ""

    esquema = esquema_ferramenta(criar_planilha)
    parametros = esquema["function"]["parameters"]
    assert esquema["function"]["name"] == "criar_planilha"
    assert parametros["type"] == "object"
    assert parametros["properties"]["linhas"] == {"type": "array", "items": {"type": "array", "items": {"type": "string"}}}
    assert parametros["required"] == ["arquivo", "linhas"]


def test_usa_ferramenta_e_responde(groq_falso, tmp_path):
    groq_falso.roteiro = [
        _resposta(chamadas=[_chamada("c1", "lembrar_informacao", {"assunto": "time", "informacao": "Treze"})]),
        _resposta("Guardei que o seu time é o Treze."),
    ]
    cerebro = CerebroGroq("Erton", "gsk_x", confirmar=lambda *a: True, avisar=print)
    assert cerebro.perguntar("lembre que meu time é o Treze") == "Guardei que o seu time é o Treze."
    assert cerebro.modelo == "llama-3.3-70b-versatile"
    assert "Treze" in (tmp_path / "memoria.json").read_text(encoding="utf-8")
    segundo_pedido = groq_falso.pedidos[1]["messages"]
    assert segundo_pedido[-1]["role"] == "tool" and "Guardei" in segundo_pedido[-1]["content"]
    assert any(t["function"]["name"] == "criar_planilha" for t in groq_falso.pedidos[0]["tools"])


def test_erros_viram_mensagens_e_nao_sujam_o_historico(groq_falso):
    groq_falso.roteiro = [_erro(groq.RateLimitError, 429), _erro(groq.AuthenticationError, 401)]
    cerebro = CerebroGroq("Erton", "gsk_x")
    assert "limite gratuito do Groq" in cerebro.perguntar("oi")
    assert "chave do Groq não é válida" in cerebro.perguntar("oi")
    assert len(cerebro.mensagens) == 1  # só as instruções do sistema


class CerebroQueFalha:
    ferramentas = ["x"]
    desistir_rapido = False

    def perguntar_ou_falhar(self, texto):
        raise IAIndisponivel("Atingi o limite gratuito do Gemini por agora.")

    def esquecer(self):
        pass


def test_reserva_responde_quando_gemini_falha(groq_falso):
    groq_falso.roteiro = [_resposta("Resposta do Groq.")]
    principal = CerebroQueFalha()
    cerebro = CerebroComReserva(principal, CerebroGroq("Erton", "gsk_x"))
    assert principal.desistir_rapido is True
    assert cerebro.perguntar("oi") == "Resposta do Groq."
    assert cerebro.respondeu_pela_reserva and cerebro.ferramentas == ["x"]

    groq_falso.roteiro = [_erro(groq.RateLimitError, 429)]
    resposta = cerebro.perguntar("oi")
    assert "limite gratuito do Gemini" in resposta and "limite gratuito do Groq" in resposta


def test_combinacoes_de_chaves(groq_falso, monkeypatch):
    from jarvis.cerebro_gemini import CerebroGemini
    from jarvis.ia import criar_cerebro

    for nome in ("GEMINI_API_KEY", "GROQ_API_KEY", "JARVIS_IA"):
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setattr(config, "ENV_PROJETO", config.PASTA_TRABALHO / "nao-existe.env")
    monkeypatch.setattr(config, "ARQUIVO_ENV", config.PASTA_TRABALHO / "nao-existe2.env")
    avisos = dict(confirmar=lambda *a: True, avisar=print)

    assert criar_cerebro(config.Config.carregar(), **avisos) is None
    monkeypatch.setenv("GROQ_API_KEY", "gsk_x")
    assert isinstance(criar_cerebro(config.Config.carregar(), **avisos), CerebroGroq)
    monkeypatch.setenv("GEMINI_API_KEY", "AIza_x")
    ambos = criar_cerebro(config.Config.carregar(), **avisos)
    assert isinstance(ambos, CerebroComReserva)
    assert isinstance(ambos.principal, CerebroGemini) and ambos.reserva.ferramentas is ambos.principal.ferramentas
    monkeypatch.setenv("GROQ_API_KEY", "")
    assert isinstance(criar_cerebro(config.Config.carregar(), **avisos), CerebroGemini)
