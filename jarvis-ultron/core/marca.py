"""O nome do produto, num lugar só: para o dia em que o Jarvis mudar de nome.

NOME é como ele aparece nas telas e nos prompts dos cérebros; NOME_CURTO é como as pessoas o chamam
("Jarvis, ..."). TITULO_DA_JANELA é o título da janela, que a trava de digitação usa para reconhecer
a própria janela (actions/computer_settings.py): por isso a tela e a trava leem daqui.

Os textos dos cérebros, do Claude chefe e do Hermes trazem as marcas __MARCA__ e __MARCA_CURTA__,
que aplicar() troca pelo nome na hora. O que NÃO muda por aqui, de propósito (veja docs/RENOMEAR.md):
a palavra de ativação "Hey Jarvis" (um modelo treinado), as pastas e os nomes internos
(Documentos\\Jarvis Ultron, ~/.jarvis, o cofre, as variáveis JARVIS_*, o perfil "jarvis" do Hermes)
e os nomes dos arquivos .bat.
"""

NOME = "Jarvis Ultron"
NOME_CURTO = "Jarvis"
TITULO_DA_JANELA = NOME


def aplicar(texto: str) -> str:
    """Troca __MARCA__ e __MARCA_CURTA__ pelo nome de agora (lido na hora: os testes trocam o nome)."""
    return texto.replace("__MARCA__", NOME).replace("__MARCA_CURTA__", NOME_CURTO)
