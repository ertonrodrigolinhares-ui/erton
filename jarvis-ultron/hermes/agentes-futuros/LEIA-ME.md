# Agentes guardados (desligados)

Estes agentes já estão escritos, mas **não fazem nada até você ligar**.
Para ligar ou desligar: dê dois cliques em **`Ativar Agentes`** (na pasta `jarvis-ultron`) e digite
os números. Precisa ter rodado o `Instalar Hermes` antes. Os agentes do dono do projeto (atleta, escola,
contabilidade) não estão aqui: ficam em `pacotes/erton` e só aparecem com `JARVIS_PACOTE=erton` no `.env`.

| Agente | O que faz | Precisa de |
|---|---|---|
| `agenda-inteligente` | Organiza o Google Agenda, conflitos e datas da família | Google Agenda conectado |
| `viagens` | Voos, hotéis e roteiro (sem comprar nada) | Nada |
| `controle-gastos` | Planilha do mês a partir da fatura em PDF | Faturas em `Documentos\Jarvis Ultron\Faturas` |
| `investimentos` | Cotações e notícias dos seus ativos | Lista em `Documentos\Jarvis Ultron\carteira.txt` |
| `linkedin-lideranca` | Posts de liderança a partir do dia a dia e da carreira (com o seu ok) | Metricool (já no kit) |
| `respostas-redes` | Sugere respostas a comentários e mensagens | Metricool (já no kit) |
| `relatorio-mensal` | Relatório de crescimento das redes | Metricool (já no kit) |
| `briefing-diario` | Agenda, e-mails e notícias logo cedo | Google Agenda e Gmail conectados |
| `proposta-comercial` | Rascunho de proposta de serviços | Nada |
| `resumo-reuniao` | Vira anotações em ata com tarefas | Texto da reunião |
| `email-triagem` | Separa e-mails e sugere respostas (não envia) | Rode o 'Ligar Gmail' |

Todos seguem a mesma regra dos agentes atuais: **nada é publicado, enviado, comprado ou alterado
sem o seu "ok"**.
