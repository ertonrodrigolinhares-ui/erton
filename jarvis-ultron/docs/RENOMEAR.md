# Trocar o nome do Jarvis

O nome do produto fica num lugar só: `core/marca.py` (`NOME`, `NOME_CURTO` e, a partir deles, o
título da janela). Trocar ali renomeia, sem mais nada:

- o que os cérebros ouvem sobre si ("Você é o ..."): Gemini (saudação), Gemma, Groq e outra empresa;
- as regras do Claude chefe e a personalidade do Hermes (`hermes/SOUL.md`, preenchida a cada abertura);
- o título da janela e do ícone perto do relógio (a trava de digitação reconhece a própria janela por
  ele, nos dois lados), os avisos de abertura, o campo "Converse com o ..." e os títulos da tela azul;
- a tela "Sobre você".

O teste `tests/test_marca.py` garante que esses textos não escrevem o nome à mão.

## O que ainda é trocado à mão (de propósito)

- **A palavra de ativação "Hey Jarvis"** (`core/palavra_ativacao.py`): é um modelo treinado para essa
  frase; outro nome exige outro modelo. Até lá, o cliente continua chamando "Hey Jarvis".
- **"Jarvis, ..." nas falas** que o código reconhece: `main.py` (`_SELF_QUIT_PATTERNS`, "desliga o
  Jarvis"), `core/prompt.txt` (cabeçalho "JARVIS CORE PROTOCOL", a despedida fixa, que também está em
  `SELF_QUIT_GOODBYE` e nos testes) e `core/cerebro_gemma.py` (os pedidos de modo privado). O
  `prompt.txt` é contrato da reorganização: muda num commit marcado, com os testes.
- **Pastas e nomes internos, que não devem mudar** (ou os dados do cliente somem): `Documentos\Jarvis
  Ultron`, `~/.jarvis`, o cofre de chaves (`SERVICE="jarvis"`), as variáveis `JARVIS_*` do `.env`, o
  perfil `jarvis` do Hermes e a pasta `Claude`. Se um dia mudarem, precisam de migração.
- **Os arquivos .bat** (`Iniciar Jarvis Ultron.bat` e os instaladores) e os textos deles, que são
  contrato (mesmo nome e ordem); e o `hermes/instalar_hermes.ps1`, que escreve "Jarvis Ultron" ao criar o
  perfil do Hermes.
- **Manuais e textos**: `LEIA-ME.md`, `VERSAO.txt`, `README.md`, `dev/ROTEIRO_DE_5_MINUTOS.md`,
  `claude/CLAUDE.md` (o modelo copiado para a pasta do Claude; o cabeçalho "Quem usa o Jarvis" também
  está na `_QUEM_E` de `core/claude_chefe.py`) e as descrições dos agentes em `claude/skills` e `hermes/`.
- **A tela antiga (F2)**: "STARK INDUSTRIES", "MARK XXXIX" e outros nomes da Marvel, que a Etapa 19 da
  reorganização pode aposentar.
- **Nomes e licenças**: "Jarvis" e "Ultron" são personagens da Marvel; um produto pago com esses nomes
  é um risco de marca. O projeto veio do JARVIS-OS (MIT, veja `LICENSE`): o aviso de autoria fica.
