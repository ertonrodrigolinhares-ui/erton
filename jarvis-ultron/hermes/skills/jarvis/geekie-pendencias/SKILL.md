---
name: geekie-pendencias
description: "Lê (sem alterar nada) as atividades pendentes e os prazos do aluno no Geekie One e salva a lista para o Jarvis. Nunca responde, entrega ou marca atividades."
version: 1.0.0
metadata:
  hermes:
    tags: [escola, geekie, pendencias, lembretes]
    category: jarvis
---
# Pendências do Geekie One (somente leitura)

## Quando usar
Às 7h e às 18h (tarefa agendada) ou quando o Erton pedir "o que tem pendente no Geekie?".

## Procedimento
1. Abra https://one.geekie.com.br/ no navegador do Hermes.
2. Se pedir login, NÃO digite senha. Pare e responda: "Preciso que você entre uma vez no Geekie One
   no navegador do Hermes; depois disso eu consigo ler as pendências sozinho."
3. Vá até a área de atividades/tarefas do aluno e leia, SEM clicar em responder, entregar,
   enviar ou concluir nada:
   - disciplina, título da atividade, prazo (data de entrega) e situação (pendente, atrasada, feita).
4. Salve em `__PASTA_JARVIS__/geekie/pendencias.json` exatamente neste formato (datas AAAA-MM-DD):
   ```json
   {"atualizado_em": "AAAA-MM-DDTHH:MM", "atividades": [
     {"disciplina": "Matemática", "titulo": "Lista 3", "prazo": "AAAA-MM-DD", "status": "pendente"}
   ]}
   ```
   Use status "pendente", "atrasada" ou "feita". Se não houver prazo, use "prazo": "".
5. Responda com um resumo curto em português, pronto para ser falado, com as que vencem primeiro:
   "No Geekie há 3 atividades pendentes: Matemática, Lista 3, até sexta; ..."

## Regras (obrigatórias)
- SOMENTE LEITURA. Nunca responda questões, nunca envie, entregue, conclua ou marque atividades
  como feitas, nem altere nada na conta do aluno. Se uma tela pedir confirmação, cancele.
- Nunca digite senhas nem códigos. Nunca mude configurações da conta.
- Não salve o conteúdo das questões, só a lista (disciplina, título, prazo, situação).
