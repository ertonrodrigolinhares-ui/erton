# O Jarvis como produto: a ideia, a partir do que já existe

Escrito em 20/10/2026 a partir do código que está no repositório, não de uma ideia nova. Tudo o que
está em "já existe" funciona hoje; o resto é o que falta para vender. Os pontos marcados com
**(decisão sua)** só você pode fechar.

## Em uma frase

Um assistente de voz para o PC com Windows que fala português, conhece quem o usa, faz tarefas de
verdade (agenda, e-mails, pesquisas, relatórios, redes sociais, lembretes, vídeos e imagens) e **nunca
age sem o "ok" da pessoa**, com um modo privado em que nada sai do computador.

## Para quem (hipótese) **(decisão sua)**

Profissionais liberais e donos de pequenos negócios que vivem no PC, querem um "assistente de verdade"
em português e se preocupam com privacidade. Não é um produto de contabilidade nem de nenhum setor:
o perfil (profissão, preferências e objetivos) é o que adapta o Jarvis a cada cliente.

## O que já existe (e vende)

| Peça | O que faz hoje |
|---|---|
| **Voz ao vivo** | Conversa por voz em tempo real (Gemini Live), em português, com a voz "Ultron"; "Hey Jarvis" reconhecido no próprio PC (nada vai para a nuvem antes disso); modo chamada e mãos livres; suspender por um tempo. |
| **Tela** | Tela azul com o anel desenhado pela placa de vídeo, campo para digitar, painéis (agenda, e-mails, clima, notícias, atalhos), briefing de "bom dia" com a câmera reconhecendo a pessoa (tudo local), modo compacto. Tela e cérebro são programas separados: a tela não trava. |
| **Perfil** | A tela "Sobre você" (nome, como chamar, cidade, profissão, preferências) alimenta todos os cérebros. Nenhum nome fica no código. |
| **Modo privado** | Gemma 4 no PC (Ollama) + Whisper local: conversa e executa tarefas sem internet para a IA; nada sai do computador. Troca por voz. |
| **Reserva** | Se o Gemini cair, continua pelo Groq (ou outra empresa) com voz da Microsoft. |
| **Claude chefe** | Pesquisas, análises de arquivos, relatórios, 282 especialistas (finanças, vendas, marketing, gestão, jurídico...), e mudanças no próprio código com plano, "ok", backup e desfazer. Usa a assinatura do próprio cliente. |
| **Hermes** | Agentes com modelos grátis (Nous): posts para redes sociais via Metricool (só publica com "ok"), leitura de painéis no navegador, Telegram (fala com o Jarvis do celular). |
| **Automações** | Lembretes falados, rotinas salvas por voz, vídeos (Google Veo, com preço dito antes), imagens, backup da memória em HD externo, proteção do PC, análise de segurança e reputação de sites, vigia do Wi-Fi, autoconserto e autodiagnóstico. Uma automação nova = um arquivo na pasta. |
| **Agentes prontos** | 22 agentes em português (briefing do dia, triagem de e-mails, resumo de reunião, proposta comercial, controle de gastos, viagens, investimentos, agenda...). Veja a seção "Agentes" abaixo. |
| **Segurança (diferencial)** | O "ok" é conferido no código, numa fala nova depois da pergunta: nada é publicado, enviado, comprado, digitado, apagado nem desligado sem ele. As ferramentas herdadas que agiam sozinhas foram desligadas. O mapa das travas está em `core/SEGURANCA.md`, com testes. |
| **Instalação** | `Iniciar Jarvis Ultron.bat` instala tudo e pede a chave; instaladores de Gemma, Claude, Hermes, Telegram, Gmail e voz local com dois cliques. |
| **Qualidade** | Centenas de testes automáticos, um roteiro de conferência de 5 minutos e um plano de reorganização em andamento (etapas 0 a 5 prontas). |

## O que foi feito nos últimos dias para virar produto

- Os 282 especialistas entraram sem pesar (índices lidos só quando precisa).
- A empresa do dono saiu de tudo; o perfil do cliente substituiu o nome fixo no Gemini, no Gemma, no
  Groq, no Claude, no Hermes e nas telas.
- O nome do produto ficou num lugar só (`core/marca.py`), com o guia `docs/RENOMEAR.md`.
- Código morto e peças sem uso saíram (etapa 5 da reorganização).

## Agentes: o que é do produto e o que é seu **(decisão sua)**

Dos 22 agentes do Claude (e os 6 do Hermes), três grupos:

- **Do produto (genéricos, ficam):** briefing-diario, email-triagem, resumo-reuniao,
  proposta-comercial, controle-gastos, viagens, investimentos, agenda-inteligente (tirando "da
  família"), relatorio-mensal, respostas-redes, linkedin-lideranca (virar "LinkedIn profissional").
- **Seus (atleta, família, escola), que não devem ir para o cliente:** conteudo-atleta,
  rotina-atleta-8h, treino-semana, treinador-dados, nutricao-recuperacao, agente-provas; no Hermes,
  conteudo-atleta, rotina-atleta-8h e geekie-pendencias (e as rotinas automáticas das 8h e do Geekie
  que o instalador do Hermes cria). **Feito:** estão em `pacotes/erton`, ligados só no seu PC pela linha
  `JARVIS_PACOTE=erton` no `.env`, fora do que o cliente recebe.
- **De contabilidade, fora do produto** (regra do projeto: o Jarvis não é de contabilidade):
  clientes-grupos, holding-sucessao, prazos-fiscais, legislacao, noticias-setor. **Feito:** também
  estão em `pacotes/erton`.

## O que falta para vender (na ordem)

1. **Separar o pacote do dono e tirar a contabilidade**: feito (`pacotes/erton`, `JARVIS_PACOTE`).
2. **Nome e marca** **(decisão sua)**: "Jarvis" e "Ultron" são da Marvel; um produto pago com esses nomes
   é risco de marca. Trocar é um passo só no código (`core/marca.py`) mais o que `docs/RENOMEAR.md`
   lista (a palavra "Hey Jarvis" pede um modelo novo de ativação). Ícone e nome da pasta vêm junto.
3. **Contas e chaves do cliente**: cada cliente usa a própria chave do Gemini (grátis), do Groq
   (grátis) e a própria assinatura do Claude. As telas já pedem isso. Conferir as regras de uso
   comercial do Google e da Anthropic antes de vender.
4. **Código fechado**: o repositório é público no GitHub; quem quiser baixa de graça. Tornar privado
   (ou decidir vender serviço, não software) **(decisão sua)**.
   Observação: nada que o cliente vê (telas, falas, manual, instruções das IAs) tem nome de dono; os
   comentários internos do código ainda dizem "o Erton" no sentido de "quem usa". Só vale limpar isso se
   o código for entregue aberto.
5. **Instalação e atualização**: hoje é .bat + Python (10 a 20 minutos na primeira vez) e a versão
   nova é "extrair numa pasta nova e copiar o .env". Para vender: um instalador único (já existe um
   começo em `JARVIS.spec`) e atualização sem perder dados: o perfil já sobrevive; a memória
   (`memory/long_term.json`) ainda não, e deve ir para `Documentos\Jarvis Ultron`.
6. **Tudo em português e sem a tela antiga**: etapas 8 e 19 da reorganização (a tela F2 ainda tem
   "STARK INDUSTRIES", "MARK XXXIX" e textos em inglês).
7. **Termos de uso e privacidade (LGPD)**: uma página simples dizendo o que fica no PC (memória, perfil,
   chaves), o que sai (voz e pedidos para o Google, Groq, Claude; o modo privado não manda nada) e que
   nada é publicado sem o "ok".
8. **Piloto**: 3 a 5 clientes de confiança usando por duas semanas, com o roteiro de 5 minutos e o
   autodiagnóstico como suporte.

## Como cobrar (sugestões) **(decisão sua)**

- **Licença por PC** (pagamento único) + **plano de atualizações** anual; ou
- **Assinatura mensal** com suporte pelo Telegram; ou
- **Implantação paga** (instala, configura chaves, Hermes, Telegram) + mensalidade.

Custos que o cliente paga direto: Gemini (grátis até a cota; o Google pode usar as conversas no plano
grátis), Veo e ElevenLabs (pagos), Claude (assinatura própria). Custos seus: nenhum por cliente, se o
código ficar fechado e o suporte for seu.

## Os diferenciais para falar na venda

1. **"Ele pergunta antes."** Segurança conferida no código, não só prometida.
2. **Modo privado de verdade**: roda no PC, sem nuvem. Bom para quem lida com dados sigilosos.
3. **Conhece você**: perfil, memória e preferências em cada conversa.
4. **282 especialistas** de bolso (finanças, vendas, marketing, jurídico...) pelo Claude.
5. **Faz, não só responde**: agenda, e-mails, posts, lembretes, vídeos, relatórios.
6. **Do celular também**: pelo Telegram.

## Plano por fases

| Fase | O quê | Depende de |
|---|---|---|
| 0 (feita) | Tirar a contabilidade; criar o pacote do dono; manual sem exemplos pessoais | Feito em 20/10/2026 |
| 1 | Nome novo, ícone, repositório privado | Sua decisão de nome e de código fechado |
| 2 | Memória em Documentos; instalador único; atualização sem perder dados | Trabalho |
| 3 | Tela toda em português; aposentar a tela antiga (etapas 6 a 8 e 19 da reorganização) | Trabalho + alguns dias de uso por etapa |
| 4 | Termos de uso; piloto com 3 a 5 clientes | Clientes de confiança |
| 5 | Preço, página de venda, venda | Sua decisão de preço |

## Decisões que só você pode tomar

1. Nome novo do produto (e se "Hey Jarvis" continua como palavra de ativação por enquanto).
2. Código fechado (repositório privado) ou venda de serviço com código aberto?
3. Público-alvo e preço.
