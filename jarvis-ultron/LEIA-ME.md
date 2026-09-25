# Jarvis Ultron

Cópia do projeto **JARVIS-OS V.2** (licença MIT, veja `LICENSE`), com ajustes para o Erton:

- **Voz Ultron**: a voz do Gemini ao vivo passa por um efeito metálico (`core/efeito_ultron.py`).
- **Voz grave "Charon"** como padrão.
- **Português do Brasil** como idioma padrão e saudação em português.
- **Sem palmas para abrir o programa** (o original exigia bater palmas duas vezes).
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
- **Chamar o Jarvis** (`core/palavra_ativacao.py`): no **modo chamada**, diga **"Hey Jarvis"** (dá para
  emendar o pedido: "Hey Jarvis, que horas são?"). O reconhecimento roda no seu computador, sem
  internet: **nada do que você fala antes disso vai para o Google**. Depois de ~20 segundos de
  silêncio ele volta a esperar.
  - **Esperando o "Hey Jarvis" ele fica em silêncio**: não fala sozinho, não cumprimenta de novo quando
    a conexão reinicia e não fica anunciando o modo.
  - **Aviso:** um **som** curto (sobe = ouvindo, desce = voltou a esperar, três notas = mãos livres) e
    um **selo** embaixo do título. `JARVIS_SOM_AVISO=0` desliga o som.
- **Botões de modo** embaixo do selo: **☏ MODO CHAMADA** e **⛭ MÃOS LIVRES** (o aceso é o modo atual).
  Trocam na hora, sem passar pela IA.
- **Trocar o modo falando** (com a chamada ligada):
  - **"Jarvis, modo mãos livres"**: ele passa a responder a **tudo**, sem precisar chamar.
  - **"Jarvis, modo chamada"**: ele volta a esperar o **"Hey Jarvis"**.
  - Ao abrir, ele começa no modo chamada (mude com `JARVIS_PALAVRA_ATIVACAO=0` para começar em mãos livres).
- **IA reserva Groq** (`core/reserva_groq.py`): se o Gemini cair ou atingir o limite, o Jarvis
  entra no **modo reserva**: continua ouvindo (depois do "Hey Jarvis"), entende com o Whisper do
  Groq, responde pelo Groq e fala com a voz grátis da Microsoft. No modo reserva ele **conversa,
  mas não usa as ferramentas** (abrir apps, e-mail...). Quando o Gemini volta, tudo volta ao normal.
- Correção: quando a conexão falhava, o original tentava reconectar sem parar, várias vezes por
  segundo (gastando a cota). Agora ele espera entre as tentativas (2 s, 4 s, 8 s... até 1 minuto).

- **Voz ElevenLabs**: com `ELEVENLABS_API_KEY` no `.env`, o Jarvis fala as respostas pela ElevenLabs
  (com o efeito Ultron por cima, se ligado). Correção: no original, escolher a ElevenLabs deixava o
  Jarvis mudo, e a escolha não voltava ao reabrir.
- **Hermes Agent** (pasta `hermes`): orquestrador com sub-agentes, rotina diária das 8h, redes sociais
  pelo Metricool e navegador próprio. Veja a seção "Hermes" abaixo.

- **Tela Stark** (`ui_stark.py`): painéis no estilo do HUD do Homem de Ferro em volta da esfera —
  régua dos dias do mês, relógio em anel, disco, energia, internet, atalhos, STARK INDUSTRIES,
  clima, uso do computador, bloco de notas (fica salvo sozinho), notícias do Google e botões
  redondos (posts de hoje, clima, e-mails, música, mãos livres, modo chamada, suspender, pasta,
  resumo do dia). A **esfera do meio pulsa com o volume da voz** do Jarvis.

## Como usar no Windows

1. Dê dois cliques em **`Iniciar Jarvis Ultron`**.
   - Se aparecer "O Windows protegeu o computador": **Mais informações → Executar assim mesmo**.
   - Na primeira vez ele instala tudo. **Pode levar de 10 a 20 minutos** (são muitos componentes).
     Não feche a janela preta.
2. Quando pedir a chave do Gemini, o site do Google abre sozinho: entre com o Gmail, clique em
   **Create API key**, copie, volte à janela preta, **clique com o botão direito** para colar e aperte **Enter**.
3. Depois ele pergunta a chave do **Groq** (reserva grátis, opcional) e a **cidade** do clima.
4. A tela do Jarvis abre. Na primeira vez ele mostra uma apresentação (em inglês). Depois é só **falar**.
5. **Deixe a janela preta aberta** enquanto usa. Ela mostra o que o Jarvis está fazendo.
6. Para os agentes (posts, Metricool, rotina das 8h): dê dois cliques em **`Instalar Hermes`**.

### Reinstalar do zero
1. Se já tinha o Hermes: dê dois cliques em **`Desinstalar Hermes`** e digite **SIM**
   (apaga o Hermes e as configurações dele: login do Nous, Metricool, rotina).
2. Extraia este pacote numa pasta nova e siga os passos acima (Iniciar Jarvis Ultron → Instalar Hermes).
3. A pasta antiga do Jarvis pode ser apagada depois que a nova estiver funcionando.

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
- **Prefere que ele ouça sempre:** aperte **⛭ MÃOS LIVRES** (ou coloque `JARVIS_PALAVRA_ATIVACAO=0`
  para ele já abrir assim).

## Autodiagnóstico (o Jarvis confere a si mesmo)

Diga **"Jarvis, faça um autodiagnóstico"** (ou "o que está com defeito?"), ou aperte o botão **✚** na
tela. Ele confere internet, chave do Gemini e modelos, reserva Groq, Hermes, microfone, alto-falante,
memória/disco, navegador automático e o "Hey Jarvis", e **fala só o que está com problema e como
resolver**. O relatório completo aparece na tela e fica salvo em **Documentos\Jarvis Ultron\diagnostico.txt**.
Funciona até com o Gemini fora do ar (pelo botão, digitando "diagnóstico" ou falando no modo reserva).

## Se o Jarvis não conseguir abrir um site

- Para **clicar e digitar sozinho** nos sites, o Jarvis usa o **Chrome** ou o **Edge**. Peça:
  "Jarvis, abre o Instagram no Chrome" (ou "no Edge").
- O **Firefox** não pode ser controlado pelo Jarvis. Se você pedir o Firefox, ele abre o site
  numa janela normal do Firefox, mas não clica nem digita nela.
- Se o navegador automático não abrir por algum motivo, o Jarvis abre o site no seu navegador
  padrão, em vez de dar erro.

## Se o computador ficar lento (CPU ou memória alta)

- O que mais pesa é a **animação da tela**, não a inteligência. O Jarvis já economiza sozinho:
  parado, ele desenha a esfera mais devagar; minimizado, não desenha nada.
- Para deixar ainda mais leve, diga: **"Jarvis, qualidade gráfica baixa"**. Para voltar:
  "qualidade gráfica média" (ou "alta").
- Minimize a janela do Jarvis quando não estiver olhando para ela: ele continua ouvindo.
- Memória alta costuma ser o navegador com muitas abas, o Hermes e o próprio Jarvis juntos.
  Feche abas que não usa e reinicie o computador de vez em quando.
- Para desligar a economia automática (não recomendado), coloque `JARVIS_ECONOMIA=0` no `.env`.

## Configurações (arquivo `.env` nesta pasta)

Abra com o Bloco de Notas para mudar:

| Linha | O que faz |
|---|---|
| `GEMINI_VOICE_NAME="charon"` | Voz: charon, fenrir, orus, puck, kore, aoede, leda, schedar, zubenelgenubi |
| `JARVIS_EFEITO_ULTRON=1` | Efeito metálico. `0` desliga, `robo` deixa com voz de robô |
| `JARVIS_TEMA_STARK=1` | Tela Stark ligada. `0` = volta para a tela original |
| `JARVIS_CIDADE=Campina Grande` | Cidade do painel de clima |
| `JARVIS_VERSAO_MINIMA=3.0` | Modelos mais antigos que isso (ex.: Gemini 2.5, que o Google está aposentando) só são usados como última reserva |
| `JARVIS_PRIORIDADE=rapidez` | Padrão: modelos estáveis, mais rápidos e que travam menos. `versao` + `JARVIS_GEMINI_VERSAO=3.5` = usar a versão 3.5 mesmo em teste (preview) |
| `JARVIS_PALAVRA_ATIVACAO=1` | Começa no modo chamada (esperando o "Hey Jarvis"). `0` = começa em mãos livres |
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

## Hermes: agentes, rotina das 8h e redes sociais

O Hermes Agent (Nous Research, código aberto) é o "orquestrador" do Jarvis. Ele divide tarefas
entre sub-agentes, usa os **modelos grátis do Nous Portal** como cérebro e se conecta ao **Metricool** (posts em todas as
redes). Os **anúncios do Meta** ficam pelo app do Claude (veja "Limitações conhecidas").

### Instalar (uma vez)
1. Dê dois cliques em **`Instalar Hermes`** (nesta pasta). Ele:
   - instala o Hermes pelo instalador oficial (se ainda não tiver);
   - cria o perfil **"jarvis"** com as habilidades, a personalidade e a trava de aprovação;
   - usa o login do **Nous Portal** feito na instalação (se não tiver, abre o navegador para entrar)
     e pede a chave da **ElevenLabs** (opcional);
   - abre o navegador para você autorizar o **Metricool**;
   - cria a **rotina diária das 8h** e faz o Hermes ligar sozinho com o Windows.
2. Abra o Jarvis Ultron normalmente.

**Se o Jarvis disser "O Hermes está desligado":** dê dois cliques em **`Ligar Hermes`**. Ele liga o
serviço e testa a ligação; se o serviço automático não subir, ele liga o Hermes na própria janela
(deixe aberta, pode minimizar).

Pode rodar o **`Instalar Hermes`** de novo sempre que receber uma atualização: ele não reinstala
o que já existe e só pergunta do Metricool se você quiser reconectar.

### Como usar
- **"Hey Jarvis, quais são os posts de hoje?"**: ele lê as propostas que a rotina das 8h preparou.
- **"Ok, pode publicar os posts 1 e 3"**: ele registra o seu ok e manda publicar pelo Metricool.
- **"Entre no painel do Metricool e veja os seguidores desta semana"**: o Hermes usa o navegador sozinho.
- Tarefas longas não travam a conversa: se o Hermes demorar mais de ~25 segundos, o Jarvis avisa e
  traz a resposta quando ficar pronta (com o modo chamada esperando, ela aparece só na tela).

### Segurança
- A rotina das 8h **só prepara** os posts. **Nada é publicado sem o seu "ok".**
- A trava é garantida por um programa (`hermes/hooks/aprovacao_jarvis.py`), não só por instrução:
  publicar, agendar, editar, apagar ou mexer em anúncios é bloqueado, a não ser que você tenha dito
  "ok" ao Jarvis nos últimos 10 minutos. Se você disser "não pode publicar", ele não considera aprovado.
- No navegador, o Hermes não digita senhas, não paga nada e não envia mensagens sem o seu ok.
- Os posts ficam no perfil de atleta; nada da empresa ou de clientes.

### Custos
- **Hermes**: grátis. **Metricool**: o conector funciona inclusive no plano grátis.
- **Cérebro dos agentes**: modelos **grátis** do Nous Portal (os que terminam em `:free`). Se um estiver
  fora do ar, ele tenta outro grátis. Para trocar: `hermes -p jarvis model`.
- **ElevenLabs**: plano grátis pequeno; depois, pago.

### Limitações conhecidas
- Os sub-agentes compartilham os mesmos conectores do agente principal (o Hermes ainda não separa
  ferramentas por sub-agente); a trava de aprovação vale para todos.
- **Anúncios do Meta:** o conector oficial do Meta (mcp.facebook.com/ads) ainda não aceita login de
  programas como o Hermes (erro "Dynamic registration is not available for this client"). Use os
  anúncios pelo **app do Claude**: Configurações → Conectores → adicionar **Meta Ads**. Quando o Meta
  liberar, basta reativar as linhas `meta_ads` em `hermes/config-jarvis.yaml`.
