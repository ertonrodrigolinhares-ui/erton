---
name: rotina-atleta-8h
description: Rotina diária das 8h do perfil de atleta do Erton. Pesquisa, cria as propostas de posts do dia e salva para aprovação. Nunca publica.
version: 1.0.0
metadata:
  hermes:
    tags: [redes-sociais, rotina, atleta, metricool]
    category: jarvis
---
# Rotina diária do atleta (8h)

## Quando usar
Todo dia às 8h (tarefa agendada) ou quando o Erton pedir "prepare os posts de hoje".

## Procedimento
1. **Pesquisa (sub-agente 1)** — `delegate_task` com a meta: "Pesquise 3 assuntos atuais e
   interessantes para um triatleta amador de alto rendimento (treino, provas, nutrição,
   recuperação, mentalidade, Ironman). Traga fonte e data de cada um."
2. **Desempenho (sub-agente 2)** — `delegate_task` com a meta: "No Metricool, leia (sem alterar
   nada) os posts dos últimos 14 dias do perfil de atleta e o melhor horário para postar em cada
   rede. Diga o que funcionou melhor." Use só ferramentas de leitura.
3. **Criação (sub-agente 3)** — `delegate_task` com os resultados dos passos 1 e 2 e a meta:
   "Siga a skill conteudo-atleta e escreva 3 propostas de post para hoje."
4. **Salvar para aprovação** — grave as propostas em
   `__PASTA_JARVIS__/posts/AAAA-MM-DD.md`, no formato:
   ```
   ## Post 1 — <rede(s)> — sugestão de horário <HH:MM>
   Texto: ...
   Hashtags: ...
   Imagem sugerida: ...
   Status: aguardando ok
   ```
5. **Resumo** — responda com um resumo curto em português, pronto para ser falado:
   "Bom dia, Erton. Preparei 3 posts para hoje: 1) ..., 2) ..., 3) .... Diga 'ok' com os números
   que quer publicar."

## Regras
- NUNCA publique nem agende nesta rotina. Publicar é trabalho da skill `publicar-aprovados`,
  depois do "ok" do Erton.
- Se o Metricool não estiver conectado, faça os passos 1, 3 e 4 mesmo assim e avise no resumo.
