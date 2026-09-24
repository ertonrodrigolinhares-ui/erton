# Jarvis — assistente pessoal

Assistente com janela própria: você escreve ou fala 🎤, e ele responde, inclusive em voz alta.
A inteligência vem do **Google Gemini**, que tem plano gratuito.

## Instalação no Windows (só na primeira vez)

1. **Baixe o Jarvis:**
   [clique aqui para baixar o ZIP](https://github.com/ertonrodrigolinhares-ui/erton/archive/refs/heads/claude/jarvis-python-tivbd5.zip)
2. Abra a pasta **Downloads**, clique com o botão direito no arquivo baixado e escolha **"Extrair tudo..."**.
3. Na pasta extraída, dê dois cliques em **`Iniciar Jarvis`**.
   - Se o Windows mostrar "O Windows protegeu o computador", clique em **Mais informações → Executar assim mesmo**.
   - Se o Python não estiver instalado, o Jarvis instala sozinho. Depois é só abrir o `Iniciar Jarvis` de novo.
   - Na primeira vez, ele leva alguns minutos para se preparar. Nas próximas, abre na hora.
4. Quando a janela abrir, ela vai pedir a **chave do Gemini**:
   - clique em **"Abrir site do Google"** e entre com o seu Gmail;
   - clique em **"Create API key"** e copie a chave (começa com `AIza...`);
   - cole a chave na janela do Jarvis e clique em **Salvar**.

Pronto! Nas próximas vezes, é só dar dois cliques em `Iniciar Jarvis`.
Dica: clique com o botão direito em `Iniciar Jarvis` → **Enviar para → Área de trabalho (criar atalho)**.

> ⚠️ **Privacidade:** no plano gratuito, o Google pode usar as conversas para melhorar os produtos dele.
> Não coloque dados de clientes (balanços, CPFs, contratos) no Jarvis.

## O que ele sabe fazer

Fale ou escreva normalmente. Exemplos:

| Você pede | O Jarvis faz |
|---|---|
| "Crie uma planilha de despesas do mês com aluguel 1.500 e luz 320" | Cria `despesas.xlsx` em **Documentos\Jarvis** |
| "Leia a planilha despesas e me diga o total" | Lê a planilha e responde |
| "Acrescente internet 150 na planilha despesas" | Acrescenta a linha (pede sua confirmação) |
| "Mande no WhatsApp para a Emanuele: estou chegando" | Abre o WhatsApp com a mensagem pronta; você aperta enviar |
| "Escreva um e-mail para cliente@x.com sobre o balanço" | Abre o Gmail com o e-mail pronto; você revisa e envia |
| "Faça um programa em Python que renomeie os PDFs da pasta" | Gera o código e salva em Documentos\Jarvis |
| "Rode esse código" | Executa (pede sua confirmação antes) |
| "Me lembre de ligar para o cliente daqui a 30 minutos" | Avisa na tela e em voz alta |
| "Quais as notícias de hoje sobre a reforma tributária?" | Pesquisa no Google e resume, com as fontes |
| "Abra o Excel" / "abra a calculadora" | Abre o programa |
| "Que horas são?" / "calcule 1500 vezes 12" | Responde na hora |

- **⚡ Conversa ao vivo** (recomendado): clique no botão e converse por voz em tempo real,
  sem apertar nada, como numa ligação. Ele ouve direto, responde com voz natural, pode ser
  interrompido e continua usando todas as ferramentas. Escolha a voz em **"Voz ao vivo"**:
  Charon (grave), Fenrir, Orus, Puck, Kore, Aoede... O efeito escolhido (Ultron, robô) também vale aqui.
  Usa a mesma chave do Gemini (API Gemini Live).
- **Memória**: "Jarvis, lembre que o aniversário da Yvnna é em maio". Ele guarda e lembra nas próximas conversas.
- **Ver a tela**: "Jarvis, o que tem na minha tela?" ou "leia esse erro que apareceu".
- **🎤 Falar**: clique e fale um pedido.
- **Mãos livres**: marque a opção e o Jarvis fica ouvindo. É só dizer **"Jarvis, ..."** e o pedido, e ele responde em voz alta.
- **Voz e Efeito** (embaixo da conversa): escolha a voz e o efeito e clique em **▶ Testar**.
  - Vozes grátis da Microsoft: Antonio, Francisca e Thalita (Brasil), Duarte e Raquel (Portugal),
    e vozes com sotaque (Andrew, Brian, Ava, Emma, Rémy, Florian, Giuseppe).
  - Efeitos: **Ultron (metálico)**, **Mais grave**, **Robô** ou sem efeito.
  - **ElevenLabs**: vozes mais humanas, com a sua chave de elevenlabs.io (a janela pede).
  - **Windows**: funciona sem internet; também é usada automaticamente se as outras falharem.
- **Segurança**: antes de alterar um arquivo que já existe ou de executar um código, ele pede sua confirmação. Mensagens e e-mails **nunca** são enviados sozinhos.
- Se o Gemini estiver sobrecarregado, o Jarvis tenta de novo e troca sozinho para outro modelo gratuito.
- A chave e os arquivos ficam em **Documentos\Jarvis**. Ao baixar uma versão nova do Jarvis, a chave continua lá.

## Se algo não funcionar

- **"Faltam componentes de voz"**: feche o Jarvis e abra o `Iniciar Jarvis` de novo. Ele tenta
  instalar o que faltou. Se continuar, envie o arquivo `instalacao-log.txt` da pasta do Jarvis.
- **"Não encontrei um microfone"**: confira se o microfone está conectado e vá em
  **Configurações do Windows → Privacidade e segurança → Microfone**. Ative **"Acesso ao microfone"**
  e **"Permitir que aplicativos da área de trabalho acessem o microfone"**.
- **O Jarvis fechou sozinho**: envie o arquivo `jarvis-erro.txt` da pasta do Jarvis.

## Para programadores

| Arquivo | Função |
|---|---|
| `Iniciar Jarvis.bat` | Instala o Python e as dependências, e abre a janela |
| `jarvis/janela.py` | Janela (tkinter) com microfone e configuração da chave |
| `jarvis/ao_vivo.py` | Conversa por voz em tempo real com o Gemini Live |
| `jarvis/memoria.py` | Memória de longo prazo (Documentos\Jarvis\memoria.json) |
| `jarvis/ferramentas.py` | Ações que a IA pode fazer: planilhas, arquivos, código, WhatsApp, e-mail, lembretes, pesquisa |
| `jarvis/assistente.py` | Decide se o pedido é um comando local ou vai para a IA |
| `jarvis/comandos.py` | Comandos rápidos (hora, data, sites, pesquisas, contas, piadas) |
| `jarvis/cerebro_gemini.py` | IA com Google Gemini (padrão, gratuito) |
| `jarvis/cerebro_claude.py` | IA com Claude (opcional, pago) — use `JARVIS_IA=claude` no `.env` |
| `jarvis/voz.py` | Vozes (Microsoft edge-tts, ElevenLabs, Windows), efeitos, microfone (sounddevice) e reconhecimento |
| `jarvis/config.py` | Configurações e chave, guardadas em `Documentos\Jarvis\config.env` |

```bash
pip install -r requirements.txt -r requirements-voz.txt
python -m jarvis                    # janela
python -m jarvis --terminal         # conversa pelo terminal
python -m jarvis --terminal --voz   # terminal + microfone ("Jarvis, que horas são?")
python -m pytest                    # testes (pip install pytest)
```

Para criar um comando novo, escreva uma função em `jarvis/comandos.py` que recebe o texto
(minúsculo e sem acentos) e retorna a resposta ou `None`. Depois, inclua a função na lista `COMANDOS`.

## Créditos

O modo ao vivo (Gemini Live), a memória e a visão da tela foram inspirados no projeto
[JARVIS-OS V.2](https://github.com/MAL19INDUSTRIES/JARVIS-OS-V.2) (licença MIT).
