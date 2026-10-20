# Trocar o nome do assistente

Em 20/10/2026 o assistente deixou de se chamar "Jarvis" / "Jarvis Ultron" e passou a se chamar
**Luiz Conrado** ("Luiz", para quem fala com ele). O nome fica num lugar só: `core/marca.py` (`NOME`,
`NOME_CURTO` e, a partir deles, o título da janela). Trocar ali renomeia, sem mais nada:

- o que os cérebros ouvem sobre si ("Você é o ..."): Gemini (saudação), Gemma, Groq e outra empresa;
- as regras do Claude chefe e a personalidade do Hermes (`hermes/SOUL.md`, preenchida a cada abertura com
  os marcadores `__MARCA__` e `__MARCA_CURTA__`);
- o título da janela e do ícone perto do relógio (a trava de digitação reconhece a própria janela por
  ele, nos dois lados), os avisos de abertura, o campo "Converse com o ...", os títulos da tela azul e o
  item **"Sair do ..."** do menu do ícone (o comando interno continua "Quit JARVIS"; só o rótulo muda);
- a tela "Sobre você";
- as falas que o código reconhece ("desliga o ...", "modo ..."): aceitam o nome de agora e também o
  antigo ("desliga o Jarvis" e "modo Jarvis" continuam funcionando).

O teste `tests/test_marca.py` garante que esses textos não escrevem o nome à mão.

## O que foi trocado à mão em 20/10/2026 (e precisa ser de novo numa próxima troca)

- **Manuais e textos**: `LEIA-ME.md`, `VERSAO.txt`, `README.md`, `dev/ROTEIRO_DE_5_MINUTOS.md`,
  `docs/PRODUTO.md` e este guia.
- **Instaladores**: os textos (`title` e `echo`) dos arquivos .bat da raiz e os avisos (`Write-Host`) de
  `gemma/instalar_gemma.ps1`, `gemma/voltar_gemini.ps1`, `claude/instalar_claude.ps1` e
  `hermes/instalar_hermes.ps1`. Os nomes dos arquivos não mudaram (veja abaixo).
- **Textos fixos do código**: `core/prompt.txt` (cabeçalho e despedida fixa; é contrato da reorganização:
  muda num commit marcado, com os testes), `claude/CLAUDE.md` (o modelo copiado para a pasta do Claude; o
  cabeçalho "Quem usa o ..." também está em `core/claude_chefe.py`) e as descrições dos agentes em
  `claude/skills` e `hermes/`.

## O que fica como está (de propósito)

- **A palavra de ativação "Hey Jarvis"** (`core/palavra_ativacao.py`): é um modelo treinado para essa
  frase; outro nome exige outro modelo. Até lá, o cliente continua chamando "Hey Jarvis" (o LEIA-ME
  avisa).
- **Pastas e nomes internos, que não devem mudar** (ou os dados do cliente somem): `Documentos\Jarvis
  Ultron`, `~/.jarvis`, o cofre de chaves (`SERVICE="jarvis"`), as variáveis `JARVIS_*` do `.env`, o
  perfil `jarvis` do Hermes, o modelo `jarvis-gemma` do Ollama e a pasta `Claude`. Se um dia mudarem,
  precisam de migração.
- **Os nomes dos arquivos .bat** (`Iniciar Jarvis Ultron.bat` e os instaladores) e a ordem deles: são
  contrato (os testes conferem trechos deles).
- **Os nomes internos do código**: classes, funções, variáveis, testes (`JarvisLive`,
  `jarvis_ui_control`...), o comando interno "Quit JARVIS" e os prefixos "JARVIS:", "YOU:" e "SYS:" das
  linhas do registro, que são protocolo entre o cérebro e a tela (o nome exibido de quem fala vem de
  `core/marca.py`). Os comentários do código também não mudam.
- **A tela antiga (F2)**: "STARK INDUSTRIES", "MARK XXXIX" e outros nomes da Marvel, que a Etapa 19 da
  reorganização pode aposentar; o painel "Ultron" continua se chamando Ultron.
- **Licença**: o projeto veio do JARVIS-OS (MIT, veja `LICENSE`): o aviso de autoria fica.
