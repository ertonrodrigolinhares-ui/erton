# Jarvis Ultron

Cópia do projeto **JARVIS-OS V.2** (licença MIT, veja `LICENSE`), com ajustes para o Erton:

- **Voz Ultron**: a voz do Gemini ao vivo passa por um efeito metálico (`core/efeito_ultron.py`).
- **Voz grave "Charon"** como padrão.
- **Português do Brasil** como idioma padrão e saudação em português.
- **Sem palmas para ligar**: o original exige bater palmas duas vezes; aqui já vem desligado.
- **Iniciador para Windows** (`Iniciar Jarvis Ultron.bat`) que instala tudo e pede a chave.
- Correção: o iniciador original do Windows não abria o programa (faltava `JARVIS_CLI=1`).
- **Central de modelos** (`core/modelos.py`): o Jarvis pergunta ao Google quais modelos a sua chave
  pode usar e escolhe sempre o **Gemini mais novo e estável** (ex.: Gemini 3.1). Modelos "preview"
  e antigos (antes do 2.5) ficam só como reserva. Se um modelo sair do ar ou acabar a cota grátis,
  ele **passa sozinho para o próximo**. Isso corrige o problema do "gemini-2.5-flash não pega".
- **Suspender por um tempo**: "Jarvis, fique suspenso por 10 minutos". Ele para de ouvir e volta
  sozinho, avisando. Para voltar antes, clique no botão de microfone.
- **Gerar imagens (Nano Banana)**: "Jarvis, crie uma imagem de um leão de armadura".
  A imagem abre na hora e fica salva em **Documentos\Jarvis Ultron\Imagens**.
  Atenção: o Google pode não liberar cota grátis de imagens para a sua chave; nesse caso o Jarvis avisa.
- **Palavra de ativação "Hey Jarvis"** (`core/palavra_ativacao.py`): o Jarvis só começa a ouvir
  depois que você diz **"Hey Jarvis"** (pronúncia em inglês funciona melhor). A detecção roda no
  seu computador, sem internet: **nada do que você fala antes disso vai para o Google**.
  Depois de ativado, ele continua ouvindo durante a conversa e volta a dormir após ~20 segundos
  de silêncio. A tela mostra "Estou ouvindo" e "Aguardando Hey Jarvis".
- **IA reserva Groq** (`core/reserva_groq.py`): se o Gemini cair ou atingir o limite, o Jarvis
  entra no **modo reserva**: continua ouvindo (depois do "Hey Jarvis"), entende com o Whisper do
  Groq, responde pelo Groq e fala com a voz grátis da Microsoft. No modo reserva ele **conversa,
  mas não usa as ferramentas** (abrir apps, e-mail...). Quando o Gemini volta, tudo volta ao normal.
- Correção: quando a conexão falhava, o original tentava reconectar sem parar, várias vezes por
  segundo (gastando a cota). Agora ele espera entre as tentativas (2 s, 4 s, 8 s... até 1 minuto).

## Como usar no Windows

1. Dê dois cliques em **`Iniciar Jarvis Ultron`**.
   - Se aparecer "O Windows protegeu o computador": **Mais informações → Executar assim mesmo**.
   - Na primeira vez ele instala tudo. **Pode levar de 10 a 20 minutos** (são muitos componentes).
     Não feche a janela preta.
2. Quando pedir a chave do Gemini, o site do Google abre sozinho: entre com o Gmail, clique em
   **Create API key**, copie, volte à janela preta, **clique com o botão direito** para colar e aperte **Enter**.
3. A tela do Jarvis abre. Na primeira vez ele mostra uma apresentação (em inglês). Depois é só **falar**.
4. **Deixe a janela preta aberta** enquanto usa. Ela mostra o que o Jarvis está fazendo.

## Trocar a chave do Gemini

- **Jeito mais fácil:** apague o arquivo **`.env`** desta pasta e abra o `Iniciar Jarvis Ultron`.
  Ele pede a chave de novo.
- **Ou:** abra o `.env` com o Bloco de Notas, troque o que está entre aspas na linha
  `GEMINI_API_KEY="..."` e salve.
- **Atualizando para uma versão nova:** copie o arquivo `.env` da pasta antiga para a nova,
  assim ele não pede a chave de novo.
- **Chave do Groq:** o iniciador pergunta uma vez. Para colocar ou trocar depois, abra o `.env`
  no Bloco de Notas e edite a linha `GROQ_API_KEY="..."` (chave grátis em https://console.groq.com/keys).

## Se o "Hey Jarvis" não funcionar bem

- **Ele não acorda:** fale "Hey Jarvis" com pronúncia em inglês, perto do microfone. Se ainda
  falhar, coloque `JARVIS_SENSIBILIDADE=0.3` no `.env`.
- **Ele acorda sozinho:** aumente para `JARVIS_SENSIBILIDADE=0.7`.
- **Prefere que ele ouça sempre:** coloque `JARVIS_PALAVRA_ATIVACAO=0`.

## Configurações (arquivo `.env` nesta pasta)

Abra com o Bloco de Notas para mudar:

| Linha | O que faz |
|---|---|
| `GEMINI_VOICE_NAME="charon"` | Voz: charon, fenrir, orus, puck, kore, aoede, leda, schedar, zubenelgenubi |
| `JARVIS_EFEITO_ULTRON=1` | Efeito metálico. `0` desliga, `robo` deixa com voz de robô |
| `JARVIS_SKIP_CLAP_GATE=1` | Mude para `0` para ligar o Jarvis batendo **duas palmas** 👏👏 |
| `JARVIS_PALAVRA_ATIVACAO=1` | "Hey Jarvis" ligado. `0` = ouve sempre, como no original |
| `JARVIS_SENSIBILIDADE=0.5` | Menor (ex.: `0.3`) = aceita o "Hey Jarvis" com mais facilidade; maior = mais rigoroso |
| `JARVIS_JANELA_CONVERSA=20` | Segundos que ele continua ouvindo depois da última fala |
| `GROQ_API_KEY="gsk_..."` | Chave do Groq (reserva grátis). O iniciador pergunta uma vez |
| `JARVIS_VOZ_RESERVA=pt-BR-AntonioNeural` | Voz do modo reserva (ex.: `pt-BR-FranciscaNeural`) |
| `JARVIS_MODELO_TEXTO=` | (Opcional) força um modelo de texto, ex.: `gemini-3.1-flash`. Vazio = automático |
| `JARVIS_MODELO_LEVE=` | (Opcional) força o modelo das tarefas rápidas, ex.: `gemini-3.1-flash-lite` |
| `JARVIS_MODELO_PRO=` | (Opcional) força o modelo "pro" |
| `JARVIS_MODELO_IMAGEM=` | (Opcional) força o modelo de imagens (Nano Banana) |
| `GEMINI_LIVE_MODEL=` | (Opcional) força o modelo da conversa por voz |

Deixe essas linhas de fora para o Jarvis escolher sozinho. Esse é o recomendado.

## Observações

- A interface original é em **inglês**. O Jarvis fala e entende português.
- Algumas funções exigem configuração extra (Gmail, Instagram, Spotify). Veja `docs/USAGE.md`.
- Os testes do projeto original já vinham com 71 falhas (testes desatualizados em relação ao código).
  Os ajustes do Jarvis Ultron não mudaram nenhum resultado.
