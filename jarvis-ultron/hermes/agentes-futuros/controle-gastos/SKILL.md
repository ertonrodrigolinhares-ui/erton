---
name: controle-gastos
description: "Controle de gastos: lê a fatura do cartão (PDF) e monta a planilha do mês por categoria."
version: 1.0.0
metadata:
  hermes:
    tags: [jarvis, futuro]
    category: jarvis
---
# Controle de gastos

Controle de gastos: lê a fatura do cartão (PDF) e monta a planilha do mês por categoria.

## Requisitos
- Salvar as faturas em PDF na pasta Documentos\Jarvis Ultron\Faturas.

## Procedimento
1. Leia a fatura mais recente da pasta de faturas.
2. Classifique cada gasto: moradia, alimentação, transporte, esporte, saúde, educação, lazer, assinaturas, outros.
3. Crie a planilha Documentos\Jarvis Ultron\Gastos\AAAA-MM.xlsx com os itens e o total por categoria.
4. Compare com o mês anterior e aponte as 3 maiores variações e assinaturas esquecidas.

## Regras
- Nunca envie a fatura para lugar nenhum nem faça pagamentos.
