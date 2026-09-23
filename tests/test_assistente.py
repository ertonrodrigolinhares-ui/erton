from jarvis import config as config_mod
from jarvis.assistente import SEM_CHAVE, responder


class CerebroFalso:
    def __init__(self):
        self.perguntas = []
        self.esquecido = False

    def perguntar(self, texto):
        self.perguntas.append(texto)
        return "resposta da IA"

    def esquecer(self):
        self.esquecido = True


def test_comando_local_nao_chama_ia():
    cerebro = CerebroFalso()
    resposta, acao = responder("calcule 2 mais 2", cerebro, "Erton")
    assert resposta == "O resultado é 4." and acao is None
    assert cerebro.perguntas == []


def test_pergunta_livre_vai_para_ia():
    cerebro = CerebroFalso()
    assert responder("o que é uma holding?", cerebro, "Erton") == ("resposta da IA", None)


def test_sem_chave():
    assert responder("o que é uma holding?", None, "Erton") == (SEM_CHAVE, None)


def test_sair_e_nova_conversa():
    cerebro = CerebroFalso()
    assert responder("Tchau!", cerebro, "Erton") == ("Até logo, Erton.", "sair")
    assert responder("nova conversa", cerebro, "Erton")[1] == "esquecer"
    assert cerebro.esquecido


def test_salvar_chave_no_env(tmp_path, monkeypatch):
    arquivo = tmp_path / ".env"
    arquivo.write_text("JARVIS_USUARIO=Erton\nGEMINI_API_KEY=antiga\n", encoding="utf-8")
    monkeypatch.setattr(config_mod, "ARQUIVO_ENV", arquivo)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    config_mod.salvar_no_env("GEMINI_API_KEY", "nova")
    assert arquivo.read_text(encoding="utf-8") == "JARVIS_USUARIO=Erton\nGEMINI_API_KEY=nova\n"
    assert config_mod.Config.carregar().chave_api == "nova"
