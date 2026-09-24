from unittest.mock import patch

import pytest

from jarvis import config, ferramentas
from jarvis.persona import prompt_sistema


@pytest.fixture
def kit(tmp_path, monkeypatch):
    monkeypatch.setattr(ferramentas, "PASTA_TRABALHO", tmp_path)
    monkeypatch.setattr(config, "PASTA_TRABALHO", tmp_path)
    respostas = {"confirmar": True}
    avisos = []
    usadas = []
    lista = ferramentas.criar_ferramentas(
        confirmar=lambda titulo, detalhe: respostas["confirmar"],
        avisar=avisos.append,
        pesquisar=lambda pergunta: f"resultado: {pergunta}",
        ao_usar=usadas.append,
        analisar_imagem=lambda pergunta, png: f"vi {len(png) > 0}: {pergunta}",
    )
    return {f.__name__: f for f in lista}, respostas, avisos, usadas, tmp_path


def test_planilha_criar_ler_e_acrescentar(kit):
    f, respostas, _, usadas, pasta = kit
    assert "2 linhas" in f["criar_planilha"]("despesas", ["Item", "Valor"], [["Aluguel", "1.500,00"], ["Luz", "320"]])
    assert (pasta / "despesas.xlsx").exists()
    assert "1 linha(s) acrescentadas" in f["adicionar_linhas_planilha"]("despesas.xlsx", [["Total", "=SUM(B2:B3)"]])
    conteudo = f["ler_planilha"]("despesas")
    assert "1: Item | Valor" in conteudo and "2: Aluguel | 1500" in conteudo and "=SUM(B2:B3)" in conteudo
    assert usadas[:2] == ["criar_planilha", "adicionar_linhas_planilha"]

    respostas["confirmar"] = False
    assert "não autorizou" in f["criar_planilha"]("despesas", ["X"], [])
    assert "não autorizou" in f["adicionar_linhas_planilha"]("despesas", [["y"]])


def test_numeros_brasileiros():
    assert ferramentas._numero_ou_texto("1.234,56") == 1234.56
    assert ferramentas._numero_ou_texto("320") == 320
    assert ferramentas._numero_ou_texto("CNPJ 12.345") == "CNPJ 12.345"


def test_arquivo_texto_e_listagem(kit):
    f, respostas, _, _, pasta = kit
    assert "salvo" in f["salvar_arquivo_texto"]("robo.py", "print('oi')")
    assert f["ler_arquivo_texto"]("robo.py") == "print('oi')"
    assert "robo.py" in f["listar_arquivos"]()
    respostas["confirmar"] = False
    assert "não autorizou" in f["salvar_arquivo_texto"]("robo.py", "outro")
    assert (pasta / "robo.py").read_text() == "print('oi')"


def test_executar_codigo(kit):
    f, respostas, _, _, pasta = kit
    saida = f["executar_codigo_python"]("import os; print(2 + 3); print(os.getcwd())")
    assert "5" in saida and str(pasta) in saida
    respostas["confirmar"] = False
    assert "não autorizou" in f["executar_codigo_python"]("print(1)")


def test_whatsapp_e_email(kit):
    f, *_ = kit
    with patch("webbrowser.open") as abrir:
        assert "Não tenho o número" in f["preparar_whatsapp"]("Emanuele", "Estou chegando")
        f["salvar_contato"]("Emanuele", "(83) 99999-8888")
        assert "Falta só" in f["preparar_whatsapp"]("emanuele", "Estou chegando")
        f["preparar_email"]("cliente@exemplo.com", "Balanço", "Segue o balanço.")
    assert abrir.call_args_list[0].args[0] == "https://wa.me/5583999998888?text=Estou%20chegando"
    assert abrir.call_args_list[1].args[0].startswith("https://mail.google.com/mail/?view=cm&to=cliente%40exemplo.com")


def test_lembrete_e_pesquisa(kit):
    f, _, avisos, *_ = kit
    with patch("threading.Timer") as temporizador:
        f["criar_lembrete"](10, "ligar para o cliente")
    assert temporizador.call_args.args[0] == 600
    assert temporizador.call_args.kwargs["args"] == ("⏰ Lembrete: ligar para o cliente",)
    assert f["pesquisar_internet"]("selic hoje") == "resultado: selic hoje"


def test_erro_vira_texto(kit):
    f, *_ = kit
    assert "não encontrada" in f["ler_planilha"]("nao-existe")
    assert f["ler_planilha"]("x", aba="Z").startswith("Planilha")  # arquivo inexistente, sem exceção


def test_memoria_entra_nas_instrucoes(kit):
    f, *_ = kit
    assert "Guardei" in f["lembrar_informacao"]("time do Erton", "Treze")
    assert "- time do erton: Treze" in prompt_sistema("Erton", True)
    assert "Esqueci" in f["esquecer_informacao"]("Time do Erton")
    assert "Treze" not in prompt_sistema("Erton", True)


def test_ver_tela(kit, monkeypatch):
    from PIL import Image, ImageGrab

    f, *_ = kit
    monkeypatch.setattr(ImageGrab, "grab", lambda **_: Image.new("RGB", (3000, 1000), "blue"))
    assert f["ver_tela"]("qual o erro?") == "vi True: qual o erro?"
