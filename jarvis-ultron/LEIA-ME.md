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
- **Clima falado**: "Jarvis, como está o tempo?" responde falando, em português, com dados de verdade
  (temperatura, sensação, umidade, mínima e máxima, chance de chuva) da cidade do `.env`
  (`JARVIS_CIDADE`) ou da que você disser. Sem IA: funciona na reserva e no modo privado. Só abre o
  navegador se você pedir.
- **Notícias**: "Jarvis, quais são as notícias?" lê de 3 a 5 manchetes (Google Notícias, sem chave).
  Ele só abre a matéria no navegador depois do seu "sim"; um "não" não abre nada.
- **Mapa**: "Jarvis, mostra no mapa a praia de Tambaú" abre o Google Maps no lugar pedido.
- O cartão do "bom dia" diz "Bom dia", "Boa tarde" ou "Boa noite" conforme a hora.
- **Print salvo**: "Jarvis, tira um print" salva a tela inteira em **Documentos\Jarvis Ultron\Capturas**
  (nome com data e hora) e diz onde ficou. O print fica só no PC: não é enviado a ninguém e a memória do
  HD externo não copia essa pasta. "Captura de tela" (o recorte do Windows) continua existindo.
- **Música do seu PC**: "Jarvis, toca Evidências do meu PC" procura na pasta Música (e subpastas), por
  palavra inteira, e abre no programa de música padrão, sem internet. Achando várias, ele diz quantas
  achou e pergunta qual. Outra pasta: `JARVIS_PASTA_MUSICA` no `.env`.
- **"Você quis dizer…?"**: quando o microfone entende errado o nome de uma rotina ("rotina trein0") ou o
  texto de um lembrete para cancelar, o Jarvis sugere o mais parecido e pergunta antes de fazer.
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
  Groq, responde pelo Groq e fala com a voz grátis da Microsoft. No modo reserva ele **conversa e
  executa as tarefas principais** (abrir apps e sites, e-mail, lembretes, Hermes, automações...);
  com `JARVIS_RESERVA_FERRAMENTAS=0` no `.env` ele fica só na conversa. A sua voz e os pedidos vão
  para o Groq (nuvem, nível grátis): para assunto de cliente, use o modo privado (Gemma 4).
  Quando o Gemini volta, tudo volta ao normal.
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
4. A tela do Jarvis abre. Na primeira vez ele pede a chave do Gemini, a voz e como chamar você (tudo em
   português). Depois é só **falar**.
5. **Deixe a janela preta aberta** enquanto usa. Ela mostra o que o Jarvis está fazendo.
6. Para os agentes (posts, Metricool, rotina das 8h): dê dois cliques em **`Instalar Hermes`**.

### Reinstalar do zero
1. Se já tinha o Hermes: dê dois cliques em **`Desinstalar Hermes`** e digite **SIM**
   (apaga o Hermes e as configurações dele: login do Nous, Metricool, rotina).
2. Extraia este pacote numa pasta nova e siga os passos acima (Iniciar Jarvis Ultron → Instalar Hermes).
3. A pasta antiga do Jarvis pode ser apagada depois que a nova estiver funcionando.

## Tela limpa, como no vídeo

O Jarvis abre só com o anel no centro, como no vídeo que serviu de modelo. Os cartões do "bom dia"
aparecem dentro do anel. Para digitar, use o campo embaixo do anel; a resposta sai em voz, mesmo no
modo chamada.

- Botão **PAINÉIS** (canto de baixo, à esquerda): mostra os painéis dos lados (sistema, status,
  botões do Ultron e o histórico da conversa, que mostra também os avisos do sistema). **ESCONDER
  PAINÉIS** volta à tela limpa.
- Quando o Jarvis está fazendo algo demorado (pesquisa profunda, apresentação, uma ferramenta rodando),
  o andamento aparece num cartão **Andamento**, acima do campo de digitar, e some quando termina.
- Para abrir sempre com os painéis: `JARVIS_TELA="paineis"` no `.env`.

## Tela e cérebro separados (o Jarvis não trava)

O Jarvis agora roda como **dois programas** que conversam entre si, só dentro do seu PC:
- a **tela** (a janela, o anel, os painéis e os botões);
- o **cérebro** (microfone, voz, Gemini/Groq/Gemma, ferramentas, Hermes e lembretes).

Assim a animação da tela não atrasa as tarefas, e uma tarefa pesada não congela a tela. Você
continua abrindo só o "Iniciar Jarvis Ultron": a tela abre o cérebro sozinha. Na janela preta
aparece `[Ponte] Cérebro conectado`.

- Se o cérebro parar, a tela avisa e **religa ele sozinha** (até 3 vezes em 5 minutos).
- O **X** da janela **não fecha** o Jarvis: ele fica escondido no ícone perto do relógio (se não
  aparecer, clique na setinha ^ ao lado do relógio) e **continua ouvindo**. Para fechar de verdade:
  botão direito nesse ícone → **Sair do Jarvis** (ou o botão **QUIT** da tela antiga, ou feche a janela
  preta). Aí o cérebro fecha junto. Feche assim antes de abrir o Jarvis de novo: senão ficam dois
  Jarvis ouvindo e respondendo ao mesmo tempo.
- Para voltar ao jeito antigo (um programa só), ponha `JARVIS_UM_PROCESSO=1` no `.env`.

## Anel desenhado pela placa de vídeo

O anel de energia agora é desenhado pela **placa de vídeo** (OpenGL), inclusive numa placa comum
como a Intel de notebook: fica a 30 quadros por segundo parado e 60 falando, com os 18 fios
completos e um brilho suave a mais, e quase não usa o processador. Na janela preta aparece
`[Orbe GPU] Anel desenhado pela placa de vídeo.`

- Se a placa de vídeo não aceitar o desenho (ou não desenhar nada), o Jarvis volta sozinho para o
  desenho normal.
- Sem driver de vídeo, na Área de Trabalho Remota ou numa máquina virtual, o "OpenGL" é feito pelo
  processador: aí o Jarvis usa o desenho normal naquela abertura (para não pesar) e tenta a placa
  de vídeo de novo na próxima.
- Se o Jarvis fechar sozinho na hora de ligar a placa de vídeo, na próxima abertura ele usa o
  desenho normal (cria o arquivo `orbe_gpu_falhou` na pasta `.jarvis` do seu usuário; apague para
  tentar de novo). Abrir o Jarvis duas vezes seguidas não conta como queda.
- Para desligar: `JARVIS_ORBE_GPU=0` no `.env`.

## Cérebro Gemma 4 no seu PC (sem Gemini, privado)

O Jarvis pode pensar com o **Gemma 4** rodando no seu próprio computador, pelo Ollama. O raciocínio
não sai do PC, então dá para usar com dados de clientes, sem limite e sem chave.

1. Dê dois cliques em **"Instalar Gemma 4"**. Ele vê a memória do PC e escolhe o tamanho certo
   (26B com 32 GB ou mais, E4B com 16 GB, E2B abaixo disso), instala o Ollama, baixa o Gemma
   (10 a 18 GB, demora na primeira vez), instala o Whisper para transcrever sua voz no PC e liga
   o Jarvis no Gemma.
2. Se o Jarvis estiver aberto, feche de verdade: botão direito no ícone perto do relógio →
   **Sair do Jarvis** (o X só esconde, e o Jarvis que já estava aberto continuaria no Gemini,
   ouvindo). Depois abra o **"Iniciar Jarvis Ultron"**.

Para voltar ao Gemini: **"Voltar para o Gemini"** (e, do mesmo jeito, feche em **Sair do Jarvis** e
abra de novo). Para usar o Gemma de novo: rode o "Instalar Gemma 4" (ele pula o que já está pronto).

Bom saber:
- A voz e a conversa ficam como no modo reserva: ele ouve, pensa e responde em frases curtas, e
  executa as tarefas (sites, lembretes, automações). Sem placa de vídeo, cada resposta leva
  alguns segundos.
- Voz: a da Microsoft (internet) é mais natural, mas o texto da resposta passa por ela. Com
  `JARVIS_VOZ_PRIVADA=1` no `.env`, usa a voz do Windows e nada sai do PC.
- Ferramentas que usam a internet sem IA (clima, sites) continuam usando a internet. As que mandam
  o pedido para uma IA na nuvem ficam **desligadas** no modo Gemma: pesquisa pelo Gemini, Hermes,
  Claude, imagens, vídeos, resumo de vídeos do YouTube e agentes. Nesse modo o Jarvis também não
  grava nada na memória (que depois iria para o Gemini). Lembretes e rotinas marcados no modo
  privado ficam marcados como privados: o lembrete é falado com a voz do Windows, e fora do modo
  privado nenhum dos dois aparece nas listas nem vai para o Gemini (e o Claude nunca lê os arquivos
  de lembretes e rotinas).
- Sem o Whisper local, a voz **não** vai para a internet: o Jarvis avisa e você digita. O instalador
  só liga o Gemma quando o Whisper ficou pronto.

### Modo privado por voz (sem fechar o Jarvis)

Com o Gemma 4 instalado, diga **"Jarvis, modo privado"**: o Jarvis troca o cérebro para o Gemma
na hora e nada mais vai para IA na nuvem — nem para o Gemini, nem para o Claude. Só a **voz da
Microsoft** (internet), se estiver ligada, ainda recebe o texto das respostas para falar. Para nada
sair do PC (o certo para falar de clientes), ponha `JARVIS_VOZ_PRIVADA=1` no `.env`: ele fala com a
voz do Windows. Para voltar: **"Jarvis, modo normal"** (ou "sair do modo privado"), dito sozinho;
uma frase com "não" ("não quero sair do modo privado") não troca nada. A escolha fica gravada para a
próxima vez que abrir.

Como saber que ligou: na tela azul (a padrão) aparece o selo **🔒 MODO PRIVADO** no alto da tela. Na
tela antiga (`JARVIS_VISUAL=classico`, `JARVIS_CENA=0` ou depois do **F2**) não tem selo: espere a
linha **"🔒 Modo privado ligado"** no registro da tela (depois ele diz "Estou rodando no Gemma 4").
Até isso aparecer, o microfone não manda nada para a nuvem; se a troca não der certo, o Jarvis avisa
na tela e em voz alta.

## Claude como chefe de tarefas (pesquisas, relatórios, agentes e o próprio código)

O Gemini continua sendo a **voz** do Jarvis. Quando o pedido é grande, o Jarvis entrega para o
**Claude Code** rodando no seu PC, com a sua assinatura do Claude (Pro ou Max), sem chave de API.

1. Dê dois cliques em **"Instalar Claude"**. Ele instala o Claude Code (instalador oficial, sem
   administrador), prepara a pasta `Documentos\Jarvis Ultron\Claude` com os 22 agentes e abre o
   Claude para você **entrar com a sua conta** (no fim, digite `/exit`).
2. Abra o Jarvis (se ele estava aberto, feche de verdade, em **Sair do Jarvis**, e abra de novo) e peça,
   por exemplo:
   - "Jarvis, pede para o Claude pesquisar as novidades da reforma tributária para holdings."
   - "Jarvis, manda o Claude analisar a planilha que deixei na pasta Entrada."
   - "Jarvis, usa o agente proposta-comercial para o grupo tal."
   - "Jarvis, e sobre o ITCMD?" (continua a mesma pesquisa)

O Claude trabalha em segundo plano (dá para continuar conversando). Quando termina, o Jarvis fala
o resumo e abre o relatório completo (fica em `Claude\Relatorios`).

**Especialistas extras (282 agentes da coleção [agency-agents](https://github.com/msitarzewski/agency-agents),
licença MIT):** ficam em `claude\agency` e o Jarvis copia para `Claude\Agency`. O Gemini continua vendo
só os 22 agentes acima (assim ele não fica lento nem confuso); quem conhece os 282 é o Claude, que
consulta os índices (`INDICE.md` com as áreas e um `INDICE.md` por área) quando o pedido precisa de um
especialista. O Claude só lê essa pasta: não consegue mudar os agentes, e se algo mudar a cópia volta
ao original na próxima tarefa. Também dá para pedir um pelo nome em inglês, por exemplo:
- "Jarvis, usa o agente Tax Strategist para a holding do grupo tal."
- "Jarvis, pede para o Claude, com o especialista Legal Document Review, revisar o contrato da pasta Entrada."

Eles são em inglês e de outros países: o Claude responde em português e usa as leis e impostos do
Brasil. Agentes de programação, jogos e 3D estão na coleção, mas aqui não rodam comandos nem mexem no
PC (as travas de sempre valem). Se o nome pedido não bater com nenhum, o Claude procura o mais
parecido nos índices. Para atualizar a coleção: troque os arquivos de `claude\agency`, rode
`python scripts\gerar_indice_agency.py` e feche e abra o Jarvis.

**Mudar o código do Jarvis**: "Jarvis, pede para o Claude mudar o seu código para ...".
1. O Claude **só lê e faz um plano** (ele não tem permissão para editar nessa hora).
2. O Jarvis conta o plano e espera o seu **"ok, pode fazer"** (conferido no código, numa fala sua
   depois do plano; um "pode fazer" dito junto com o pedido não vale).
3. O Jarvis faz um **backup** (`Documentos\Jarvis Ultron\Backups`), roda os testes, o Claude
   aplica, e o Jarvis confere a escrita do código e roda os testes de novo.
4. Se algo quebrar, o Jarvis **desfaz sozinho**, arquivo por arquivo. As mudanças valem quando
   você fechar o Jarvis de verdade (botão direito no ícone perto do relógio → **Sair do Jarvis**; o X
   só esconde) e abrir de novo. O registro de cada mudança fica em `Claude\Mudancas`.
5. Enquanto o Claude muda o código, o Jarvis não troca de modo (privado/normal). Se o Jarvis fechar
   ou o PC desligar no meio, o Claude para junto e, na próxima vez que você abrir, o Jarvis desfaz
   a mudança que ficou pela metade e avisa.

Travas (no código, conferidas com o Claude Code de verdade):
- Nas **tarefas** (pesquisas, relatórios, agentes), o Claude só **escreve** em
  `Documentos\Jarvis Ultron\Claude` e só **lê** a pasta `Documentos\Jarvis Ultron` (clientes.txt,
  carteira.txt, Faturas...), menos os arquivos de lembretes e rotinas. Dentro de `Claude`, ele não
  muda a pasta `Agency` nem os `CLAUDE.md` (as instruções que toda tarefa segue): assim uma página da
  internet com instruções escondidas não vira regra permanente. Você continua podendo editar o
  `CLAUDE.md` à mão. Pelo mesmo motivo, em todo pedido ao Claude (tarefas e mudanças de código) a
  "memória" do Claude Code fica desligada e ele não escreve na pasta `.claude` do seu usuário.
- Para **mudar o código**, ele **lê** a pasta do programa do Jarvis (no plano) e, só depois do seu
  "ok", **muda** essa pasta. Mesmo aí ele nunca lê o `.env`, as chaves (`config/api_keys.json`, as
  credenciais do Gmail), a memória do Jarvis nem a pasta `.git`, e nunca muda a `.venv`, `tmp`,
  `outputs` nem as travas dele. Não guarde arquivos seus (de clientes, senhas) na pasta do programa.
- Não roda comandos no PC e não usa conectores (Gmail, Agenda, Metricool, Meta): **não consegue
  publicar, enviar, comprar nem apagar nada**. Publicar continua com o Hermes, com o seu "ok".
- Nunca lê as suas senhas (nem as do Hermes, em `AppData`, nem o login do Claude): fora dessas
  pastas, não lê nada.
- No **modo privado** nada vai para o Claude.
- Se existir `ANTHROPIC_API_KEY` no Windows, o Jarvis a tira quando chama o Claude (com ela o
  Claude cobraria pela API em vez de usar a sua assinatura).

Bom saber:
- O uso conta no limite do seu plano do Claude; se acabar, o Jarvis avisa quando ele volta.
- Privacidade: em claude.ai → Configurações → Privacidade, desligue "Ajudar a melhorar o Claude"
  se não quiser que as conversas sejam usadas para treinar modelos. Para dados sensíveis de
  clientes, prefira o modo privado (Gemma 4).
- Uso pessoal: o Jarvis usa o Claude Code que **você** instalou, com a **sua** conta. Não
  distribua o Jarvis para outras pessoas usarem as contas delas por ele.
- Os agentes que publicam ou usam o navegador sozinhos (anúncios, Geekie, painéis, publicar
  aprovados) continuam no Hermes.

## Vídeos com IA (Google Veo)

"Jarvis, faz um vídeo de 8 segundos de um triatleta cruzando a linha de chegada no Havaí" (ou
"vertical para o Instagram"). O Jarvis **diz o preço antes** (mais ou menos US$ 0,96 / R$ 5 por um
vídeo de 8 segundos na qualidade padrão) e só faz com o seu **"ok, pode fazer"** dito depois de
ouvir o preço. O vídeo fica pronto em 1 a alguns minutos, em segundo plano; ele salva em
`Documentos\Jarvis Ultron\Videos`, abre e avisa. Qualidades: econômico, rápido (padrão) e máximo;
o Jarvis nunca troca sozinho para um modelo mais caro do que o do preço aprovado. Vídeos de 4 ou 6
segundos saem em 720p (o Google só faz 1080p com 8 segundos).
Precisa da chave do Gemini com **faturamento ativado** no Google (o Veo não tem uso grátis). O
preço falado é uma estimativa; o valor certo é o da sua conta do Google Cloud.
Se a internet cair enquanto o vídeo é feito, o Jarvis continua tentando. Se mesmo assim o vídeo não
chegar, ele avisa que o Google pode cobrar por ele e anota o pedido em `Videos\pendentes.txt`:
confira a conta do Google antes de pedir outro. Se você trocar de modo ("modo privado") no meio do
vídeo, ele avisa antes. Se o Jarvis fechar, cair ou trocar de modo no meio do vídeo, o pedido fica
anotado (sem aviso na hora, quando ele fecha ou cai): quando abrir de novo no modo normal, busca o
vídeo no Google, abre e avisa (no modo privado ele só lembra que o vídeo está esperando).

## Reserva quando o Gemini cai (Groq ou outra empresa)

Se o Gemini cair, o Jarvis continua pela **reserva**. Quando o limite grátis do Groq acaba, dá para
usar outra empresa no lugar dele (ou junto: elas ficam em fila e, quando o limite de uma acaba, o
Jarvis passa sozinho para a outra). No `.env`:

```
JARVIS_RESERVA="cerebras"
JARVIS_RESERVA_CHAVE="cole_a_chave_aqui"
```

Empresas prontas: `cerebras`, `openrouter`, `mistral`, `deepseek`, `openai`, `together`. O Jarvis
escolhe o modelo sozinho (para escolher você: `JARVIS_RESERVA_MODELO`). Qualquer outra compatível
com a OpenAI: `JARVIS_RESERVA="outra"` e `JARVIS_RESERVA_URL="https://..."`.

- A voz é transcrita no PC se o Whisper local estiver instalado ("Instalar voz local"); senão, pelo
  Groq (se houver chave) ou pela OpenAI (se for ela).
- Planos grátis não devem receber dados de clientes: para isso, use o modo privado (Gemma 4).
- Nunca cole as chaves no chat; só no `.env`.

## Chave do Gemini que começa com "AQ." (conversa natural)

Desde 2026 o Google AI Studio só cria chaves que começam com **"AQ."**, e para muitas contas o
caminho normal recusa essas chaves (erro `ACCESS_TOKEN_TYPE_UNSUPPORTED`). O Jarvis agora sabe usar
um **segundo caminho, o Vertex AI** (o Gemini do Google Cloud), que é do tipo dessas chaves.

1. Crie a chave em https://aistudio.google.com/apikey ("Create API key") e copie.
2. Dê dois cliques em **"Testar chave do Gemini"**, cole a chave (botão direito; ela fica
   escondida) e aperte Enter. Ele testa o caminho normal, o Vertex AI e a conversa ao vivo, e
   grava no `.env` o que funcionou.
3. Se ele disser que a **"Vertex AI API" está desligada**: abra o link que ele mostra, escolha o
   mesmo projeto da chave, clique em **ATIVAR** e rode o teste de novo.
4. Se ele pedir **faturamento**: ative em https://console.cloud.google.com/billing (a conversa gasta
   pouco; vídeos são cobrados).

A chave nunca aparece na tela do testador: pode mandar print dela para o suporte.

## Trocar a chave do Gemini

- **Jeito mais fácil:** dê dois cliques em **"Testar chave do Gemini"** e cole a chave nova. Se ela
  funcionar, ele grava no `.env` só a chave (e o caminho que funcionou); o resto fica como está.
- **Ou:** abra o `.env` com o Bloco de Notas, troque o que está entre aspas na linha
  `GEMINI_API_KEY="..."` e salve.
- **Não apague o `.env`** para trocar a chave: ele guarda também o modo privado (Gemma), a ligação
  com o Hermes, a voz da ElevenLabs, o caminho do Claude e o do Vertex AI. Sem ele, o iniciador só
  pergunta a chave do Gemini, a do Groq e a cidade, e você teria de rodar de novo o "Instalar
  Gemma 4", o "Instalar Hermes", o "Instalar Claude" e o "Testar chave do Gemini".
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

## Hermes pelo Telegram (celular, de qualquer lugar)

Dê dois cliques em **`Ligar Telegram`** (na pasta do Jarvis). Ele abre o @BotFather para você criar
o seu robô, pede o código do robô e o seu número de usuário (@userinfobot) e liga tudo ao Hermes.
Depois é só mandar mensagens para o robô no Telegram. Só o **seu** usuário consegue usar o robô.

- Funciona enquanto o **PC estiver ligado** (o instalador oferece deixar o PC sem dormir na tomada).
- Mensagens mandadas com o PC desligado podem se perder: mande de novo quando ele ligar.
- Publicar, agendar ou mexer em anúncios continua precisando do seu "ok" dado ao Jarvis.
- **O robô não responde?** Dê dois cliques em **`Testar Telegram`**: ele confere o código, o seu
  número de usuário e se o Hermes está recebendo as mensagens, conserta o que der e salva um relatório
  em `Documentos/Jarvis Ultron/teste-telegram.txt`.
- Nunca mande o código do robô para ninguém. Se vazar, mande `/revoke` para o @BotFather e rode o
  `Ligar Telegram` de novo com o código novo.

## Automações novas: um arquivo só

Toda automação nova vem em **um arquivo**: salve na pasta **`automacoes`** (dentro da pasta do
Jarvis), feche o Jarvis de verdade (**Sair do Jarvis**, no ícone perto do relógio) e abra de novo.
Não precisa atualizar o resto do projeto. Veja
`automacoes/LEIA-ME.md`. Para desligar, apague o arquivo da pasta.

## Escola: Geekie One (pendências, tutor e lembretes)

- **Pendências:** "Jarvis, o que tem pendente no Geekie?". O Hermes lê o **Geekie One**
  (one.geekie.com.br) às **7h e às 18h**, **só lendo**: nunca responde, entrega ou marca atividades.
  Na primeira vez, entre uma vez no Geekie One no navegador do Hermes (ele não digita senhas).
- **Lembretes:** quando faltam **2 dias ou menos** (ou atrasou), o Jarvis lembra uma vez por dia.
  Com o modo chamada esperando o "Hey Jarvis", o lembrete aparece só na tela.
- **Modo tutor:** "Jarvis, me explica esse exercício". Ele explica passo a passo, dá dicas e confere
  a resposta do aluno, mas não entrega a resposta pronta de atividades avaliadas.

## Autodiagnóstico (o Jarvis confere a si mesmo)

Diga **"Jarvis, faça um autodiagnóstico"** (ou "o que está com defeito?"), ou aperte o botão **✚** na
tela. Ele confere internet, chave do Gemini e modelos, reserva Groq, Hermes, microfone, alto-falante,
memória/disco, o processador (o do computador inteiro e **quanto o próprio Jarvis está gastando**, tela
e cérebro, com a memória de cada um), a bateria (num computador de mesa, "sem bateria" é normal), o
navegador automático e o "Hey Jarvis", e **fala só o que está com problema e como resolver**. O relatório completo aparece na tela e fica salvo em **Documentos\Jarvis Ultron\diagnostico.txt**.
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
| `JARVIS_EFEITO_ULTRON=leve` | Voz metálica sem eco (padrão). `ultron` = com eco (mais "atrasada"), `robo` = robô, `0` = desliga |
| `JARVIS_LATENCIA_AUDIO=low` | Som com menos atraso (padrão). Se picotar, use `high` |
| `JARVIS_TEMA_STARK=1` | Tela Stark ligada. `0` = volta para a tela original |
| `JARVIS_CIDADE=Campina Grande` | Cidade do painel de clima e do clima falado |
| `JARVIS_PASTA_MUSICA=` | (Opcional) pasta onde "toca X do meu PC" procura as músicas. Vazio = a pasta Música do Windows |
| `JARVIS_VISUAL=orbe` | Tela azul com anel de energia e painéis de vidro (padrão). `classico` = volta para a esfera antiga |
| `JARVIS_CENA=1` | A tela azul ocupa a janela toda (padrão). `0` = anel dentro da tela antiga. A tecla **F2** também alterna |
| `JARVIS_BIOMETRIA=1` | No "bom dia", abre a câmera dentro do anel antes do resumo. `0` = pula a câmera |
| `JARVIS_NOME=Erton` | Nome usado no "Bom dia, ..." dos cartões do resumo |
| `JARVIS_VERSAO_MINIMA=3.0` | Modelos mais antigos que isso (ex.: Gemini 2.5, que o Google está aposentando) só são usados como última reserva |
| `JARVIS_PRIORIDADE=rapidez` | Padrão: modelos estáveis, mais rápidos e que travam menos. `versao` + `JARVIS_GEMINI_VERSAO=3.5` = usar a versão 3.5 mesmo em teste (preview) |
| `JARVIS_PALAVRA_ATIVACAO=1` | Começa no modo chamada (esperando o "Hey Jarvis"). `0` = começa em mãos livres |
| `JARVIS_SENSIBILIDADE=0.5` | Menor (ex.: `0.3`) = aceita o "Hey Jarvis" com mais facilidade; maior = mais rigoroso |
| `JARVIS_JANELA_CONVERSA=20` | Segundos que ele continua ouvindo depois da última fala |
| `GROQ_API_KEY="gsk_..."` | Chave do Groq (reserva grátis). O iniciador pergunta uma vez |
| `JARVIS_VOZ_RESERVA=pt-BR-AntonioNeural` | Voz do modo reserva (ex.: `pt-BR-FranciscaNeural`) |
| `JARVIS_RESERVA_FERRAMENTAS=1` | No modo reserva (Groq) ele executa as tarefas (padrão). `0` = só conversa |
| `JARVIS_VOZ_PRIVADA=0` | Reserva e Gemma falam com a voz da Microsoft (internet). `1` = voz do Windows (no modo privado, nada sai do PC; no modo reserva os pedidos continuam indo para o Groq) |
| `JARVIS_MODELO_TEXTO=` | (Opcional) força um modelo de texto, ex.: `gemini-3.1-flash`. Vazio = automático |
| `JARVIS_MODELO_LEVE=` | (Opcional) força o modelo das tarefas rápidas, ex.: `gemini-3.1-flash-lite` |
| `JARVIS_MODELO_PRO=` | (Opcional) força o modelo "pro" |
| `JARVIS_MODELO_IMAGEM=` | (Opcional) força o modelo de imagens (Nano Banana) |
| `GEMINI_LIVE_MODEL=` | (Opcional) força o modelo da conversa por voz |

Deixe essas linhas de fora para o Jarvis escolher sozinho. Esse é o recomendado.

## O que o Jarvis não faz mais (ferramentas antigas que agiam sem o seu "ok")

Algumas ferramentas antigas, que vieram do projeto original, agiam sozinhas, sem o seu "ok" conferido
no código. Elas foram **desligadas**: se você pedir, o Jarvis diz que não faz isso, e nada acontece.

- **Mensagens** (WhatsApp, Telegram, Discord, Instagram, iMessage): o Jarvis não envia, não responde e
  não lê mais mensagens. A ferramenta antiga de mensagens digitava e apertava Enter sozinha. Você
  disse que não usa. O Hermes pelo Telegram continua: ali é você que manda mensagem para o robô.
- **"Faça tal tarefa no PC"** (o agente antigo, de vários passos): ele escrevia e rodava programas
  feitos pela IA, sem mostrar nada antes. Para tarefas grandes, peça ao Claude ("Jarvis, pede para o
  Claude ...") ou ao Hermes.
- **O programador antigo** (escrever, rodar e montar programas, criar projetos e instalar
  componentes): ele rodava código e instalava coisas no PC sem o seu "ok". Para escrever um programa,
  peça ao Claude: ele escreve na pasta dele e não roda nada sozinho.
- **Controle livre do mouse** (clicar em qualquer ponto da tela, mover o mouse, procurar um botão na
  tela e clicar nele). Volume, brilho, janelas, atalhos e o resto das configurações do PC continuam
  funcionando, e digitar também, agora com o seu "ok" (veja a seção seguinte).
- **Atualizar jogos** (Steam e Epic): ele podia desligar o PC sozinho no fim do download.
- **Tarefas livres na área de trabalho** (pedir "faz tal coisa na área de trabalho"): ele pedia um programa
  à IA e o rodava com o teclado e o mouse, sem mostrar antes, e podia digitar e apertar Enter em qualquer
  janela. Papel de parede, organizar, limpar e listar a área de trabalho continuam.
- **Abrir ou criar programas pelo nome ou por arquivo**: o Jarvis continua abrindo programas pelo nome
  ("abre o Bloco de Notas", "abre o Git Bash"), mas não roda mais comandos (como "shutdown /s"), não abre
  os programas de desligar ou sair da conta e não abre nem cria programas, scripts e atalhos pelos
  arquivos (.exe, .bat, .ps1, .py, .lnk...). Antes, um pedido assim desligava o PC sem perguntar.
  Documentos, fotos, vídeos e pastas abrem normalmente. "Abre o Claude" abre o aplicativo Claude (e não o
  Claude Code de terminal), e "abre o Painel de Controle" abre o Painel de Controle. Um nome que começa
  com um comando do PC, como "PowerShell 7" ou "Python IDLE" ("powershell" e "python" são comandos), só
  abre por voz se o menu Iniciar tiver um atalho com esse nome exato, como o "Docker Desktop" (ele abre
  esse atalho). Sem o atalho, a busca do menu Iniciar rodaria o resto do nome como parte do comando: o
  Jarvis diz que não abriu, e você abre esses pelo menu Iniciar.

Os arquivos dessas ferramentas continuam na pasta por enquanto. Se alguma fizer falta, avise; para
voltar na hora, abra o "Iniciar Jarvis Ultron" da pasta da versão anterior.

## Antes de desligar, reiniciar, digitar ou apertar teclas, o Jarvis pergunta

Desligar ou reiniciar o PC, escrever um texto na janela da frente e apertar teclas nela (Enter, Esc,
colar, copiar, recortar, desfazer, refazer, salvar, selecionar tudo, fechar o programa, a janela ou a aba,
abrir aba nova, trocar de aba, voltar e avançar, ir para a barra de endereço, recarregar, zoom, procurar,
tela cheia, subir ou descer uma tela (Page Up/Page Down), ir para o começo ou o fim, pausar o vídeo com o
Espaço) **só acontecem com o seu "ok"**, conferido no código. Não é a IA que decide se você aprovou.

1. Você pede, por exemplo: "Jarvis, digita olá mundo" ou "Jarvis, reinicia o computador".
2. O Jarvis pergunta antes e diz exatamente o que vai digitar ou que teclas vai apertar, e em que janela.
   Por exemplo: *Posso digitar "olá mundo" na janela "Sem título - Bloco de Notas"?* A pergunta também
   aparece escrita num aviso do Windows, perto do relógio (e, por uns 15 segundos, no alto da janela do
   Jarvis).
3. Ele só faz se a sua **resposta seguinte** for um "ok" claro: **"ok"** ou **"ok, pode fazer"**. "Não",
   ou qualquer outra resposta, cancela. Um "ok" dito junto com o pedido, antes da pergunta, não vale.
   Para digitar ou apertar teclas, responda **falando**, com o programa certo na frente: se você clicar
   no campo do Jarvis para digitar o "ok", a janela da frente passa a ser a do Jarvis, e **na janela do
   próprio Jarvis ele nunca digita nem aperta teclas** (o que ele digitasse ali contaria como uma fala
   sua): ele diz que não fez. Aí é só pôr o programa certo na frente e pedir de novo. (Para desligar e
   reiniciar, o "ok" digitado também vale.)
4. O "ok" vale para aquilo, uma vez só. Outro texto, outra tecla ou outra janela na frente (também outra
   aba do navegador): ele pergunta de novo. Se a janela da frente mudar depois do seu "ok", ele não digita
   nada e avisa. Recarregar a página várias vezes vai até 20 de cada vez, e ele para no meio se a
   janela da frente mudar.
5. Uma coisa de cada vez: se você pedir duas ("digita olá mundo e aperta Enter"), ele pergunta uma, faz,
   e depois pergunta a outra. São dois "ok", uma de cada vez.
6. O texto vai numa linha só: com quebra de linha, tab ou caractere invisível no meio, ele não digita.

Reiniciar e desligar acontecem uns 10 segundos depois do "ok" (dá tempo de salvar algo). Para cancelar
nesse tempo: aperte Windows+R, digite `shutdown /a` e aperte Enter. Apertar a tecla Sleep, que suspende o
computador, também pergunta antes, e a pergunta diz que ele vai suspender o computador.

Continuam sem perguntar, porque não escrevem nem apertam teclas no programa da frente: volume, brilho,
Wi-Fi, tema escuro, apagar a tela, rolar a página com o mouse, minimizar, maximizar e encaixar janelas,
mostrar a área de trabalho, trocar de janela (Alt+Tab), bloquear a tela, tirar print e abrir as
Configurações, o Explorador de Arquivos, o Executar e o Gerenciador de Tarefas.

No **navegador que o Jarvis controla** (abrir sites, pesquisar, preencher), ele ainda digita e aperta Enter
sem esse "ok": só a instrução dada à IA o impede de mandar mensagem por ali. Por isso, não deixe uma
conversa do WhatsApp (ou de outro aplicativo de mensagem) aberta nesse navegador. No modo privado (Gemma),
o Jarvis não mexe nessas configurações do PC.

## Observações

- As telas, os avisos e o menu do ícone perto do relógio são em **português**. A tela antiga (a do F2)
  ainda tem partes em inglês.
- Algumas funções exigem configuração extra (Gmail, Spotify). Veja `docs/USAGE.md`.
- Os testes herdados do projeto original que cobravam telas do JARVIS-OS que não existem mais saíram
  (ficam guardados na etiqueta git `antes-da-reorganizacao`). Os testes que oscilam (hoje, só dois do
  anel na placa de vídeo numa tela virtual) ficam anotados, com o motivo, em
  `tests/dados/falhas_conhecidas.txt`. O `python dev/conferir_testes.py` roda todos os testes e avisa só
  das falhas novas.

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
2. Se o Jarvis estiver aberto, feche de verdade (botão direito no ícone perto do relógio →
   **Sair do Jarvis**) e abra o **"Iniciar Jarvis Ultron"**.

**Se o Jarvis disser "O Hermes está desligado":** dê dois cliques em **`Ligar Hermes`**. Ele liga o
serviço e testa a ligação; se o serviço automático não subir, ele liga o Hermes na própria janela
(deixe aberta, pode minimizar).

Pode rodar o **`Instalar Hermes`** de novo sempre que receber uma atualização: ele não reinstala
o que já existe e só pergunta do Metricool se você quiser reconectar.

### Como usar
- **"Hey Jarvis, quais são os posts de hoje?"**: ele lê as propostas que a rotina das 8h preparou.
- **"Ok, pode publicar os posts 1 e 3"**: ele repete o que vai publicar e pergunta; com o seu "ok" (dito
  depois de ouvir) ele registra a aprovação e manda publicar pelo Metricool.
- **"Entre no painel do Metricool e veja os seguidores desta semana"**: o Hermes usa o navegador sozinho.
- Tarefas longas não travam a conversa: se o Hermes demorar mais de ~25 segundos, o Jarvis avisa e
  traz a resposta quando ficar pronta (com o modo chamada esperando, ela aparece só na tela).

### Segurança
- A rotina das 8h **só prepara** os posts. **Nada é publicado sem o seu "ok".**
- A trava é garantida por um programa (`hermes/hooks/aprovacao_jarvis.py`), não só por instrução:
  publicar, agendar, editar, apagar ou mexer em anúncios é bloqueado. Com o seu "ok", a trava abre só
  enquanto o Hermes faz o que você aprovou (no máximo 10 minutos) e fecha assim que ele termina. Se
  você disser "não pode publicar", ele não considera aprovado.
- O "ok" só conta numa fala sua **depois** de ouvir o que vai ser feito, e tem que ser claro e curto
  ("ok", "sim, pode publicar", "ok, pode fazer"). "Ok, pode cancelar", "ok, entendi", "sim, mas tá
  caro", "ok, pode fazer amanhã", "peraí" ou uma pergunta não contam: o Jarvis pergunta de novo. Antes
  de gastar ou mudar algo, o Jarvis confere de novo a sua fala inteira (às vezes a transcrição chega
  aos pedaços). Vale também para vídeos e para o Claude.
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
