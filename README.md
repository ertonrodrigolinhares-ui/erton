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

- **Na hora, sem internet de IA:** "que horas são", "que dia é hoje", "abra o YouTube",
  "pesquise holding familiar", "pesquisar no youtube ironman havaí", "calcule 1500 vezes 12", "conte uma piada".
- **Qualquer outra pergunta** vai para o Gemini, que lembra o que foi dito antes na conversa.
- Botão **Nova conversa**: começa do zero. **Trocar chave**: cola uma chave nova.
- **Falar as respostas**: liga ou desliga a voz do Jarvis.

## Para programadores

| Arquivo | Função |
|---|---|
| `Iniciar Jarvis.bat` | Instala o Python e as dependências, e abre a janela |
| `jarvis/janela.py` | Janela (tkinter) com microfone e configuração da chave |
| `jarvis/assistente.py` | Decide se o pedido é um comando local ou vai para a IA |
| `jarvis/comandos.py` | Comandos rápidos (hora, data, sites, pesquisas, contas, piadas) |
| `jarvis/cerebro_gemini.py` | IA com Google Gemini (padrão, gratuito) |
| `jarvis/cerebro_claude.py` | IA com Claude (opcional, pago) — use `JARVIS_IA=claude` no `.env` |
| `jarvis/voz.py` | Fala (pyttsx3) e reconhecimento de voz (SpeechRecognition) |
| `jarvis/config.py` | Configurações e chave, guardadas no arquivo `.env` |

```bash
pip install -r requirements.txt -r requirements-voz.txt
python -m jarvis                    # janela
python -m jarvis --terminal         # conversa pelo terminal
python -m jarvis --terminal --voz   # terminal + microfone ("Jarvis, que horas são?")
python -m pytest                    # testes (pip install pytest)
```

Para criar um comando novo, escreva uma função em `jarvis/comandos.py` que recebe o texto
(minúsculo e sem acentos) e retorna a resposta ou `None`. Depois, inclua a função na lista `COMANDOS`.
