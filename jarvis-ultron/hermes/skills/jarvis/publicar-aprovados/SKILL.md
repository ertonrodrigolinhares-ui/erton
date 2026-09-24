---
name: publicar-aprovados
description: Publica ou agenda no Metricool somente os posts que o Erton aprovou (ele diz "ok" ao Jarvis). Use depois de uma aprovação explícita.
version: 1.0.0
metadata:
  hermes:
    tags: [redes-sociais, metricool, publicacao]
    category: jarvis
---
# Publicar posts aprovados

## Quando usar
Somente quando a mensagem disser que o Erton aprovou (ex.: "O Erton aprovou agora: posts 1 e 3").

## Procedimento
1. Abra o arquivo de propostas do dia: `__PASTA_JARVIS__/posts/AAAA-MM-DD.md`.
2. Pegue apenas os posts cujos números foram aprovados. Se a mensagem não disser quais, publique
   só se houver exatamente um post aguardando; senão, pergunte quais.
3. No Metricool, publique ou agende cada post aprovado na(s) rede(s) indicada(s), no horário
   sugerido (ou agora, se o Erton pediu "agora").
4. Atualize o arquivo: troque `Status: aguardando ok` por `Status: publicado <data/hora>` (ou
   `agendado para ...`).
5. Responda em uma frase: o que foi publicado/agendado e onde.

## Regras
- Uma trava automática só libera publicações por alguns minutos depois do "ok". Se ela bloquear,
  pare e diga: "Preciso que você confirme de novo, o tempo da aprovação acabou."
- Nunca publique texto diferente do que foi aprovado (correções de digitação são permitidas).
