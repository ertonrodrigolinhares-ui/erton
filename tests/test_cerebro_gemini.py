from google.genai import chats, errors

from jarvis import cerebro_gemini
from jarvis.cerebro_gemini import CerebroGemini


class RespostaFalsa:
    text = "Olá!"


class ChatFalso:
    def __init__(self, modelo, falhas):
        self.modelo = modelo
        self.falhas = falhas

    def send_message(self, texto):
        erro = self.falhas.get(self.modelo)
        if erro:
            raise erro
        return RespostaFalsa()

    def get_history(self):
        return []


def _cerebro(monkeypatch, falhas):
    monkeypatch.setattr(cerebro_gemini, "ESPERAS", [0, 0, 0])
    criados = []

    def criar(self, model, config, history=None):
        criados.append(model)
        return ChatFalso(model, falhas)

    monkeypatch.setattr(chats.Chats, "create", criar)
    return CerebroGemini("Erton", "principal", "chave"), criados


def test_troca_de_modelo_quando_sobrecarregado(monkeypatch):
    sobrecarga = errors.ServerError(503, {"error": {"message": "The model is overloaded."}})
    cerebro, criados = _cerebro(monkeypatch, {"principal": sobrecarga})
    assert cerebro.perguntar("oi") == "Olá!"
    assert criados == ["principal", "gemini-flash-lite-latest"]


def test_cota_esgotada_em_todos(monkeypatch):
    cota = errors.ClientError(429, {"error": {"message": "quota"}})
    falhas = {m: cota for m in ["principal"] + cerebro_gemini.MODELOS_RESERVA}
    cerebro, _ = _cerebro(monkeypatch, falhas)
    assert "limite gratuito" in cerebro.perguntar("oi")


def test_chave_invalida(monkeypatch):
    invalida = errors.ClientError(400, {"error": {"message": "API key not valid."}})
    cerebro, criados = _cerebro(monkeypatch, {"principal": invalida})
    assert "chave do Gemini não é válida" in cerebro.perguntar("oi")
    assert criados == ["principal"]
