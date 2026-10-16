import sys
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
                                Table, TableStyle, PageBreak, NextPageTemplate, KeepTogether)

OUT = sys.argv[1]
W, H = A4
NAVY = colors.HexColor("#0B1B2E"); AZUL = colors.HexColor("#1E88E5"); CIANO = colors.HexColor("#4FC3F7")
LARANJA = colors.HexColor("#F57C00"); CINZA = colors.HexColor("#5B6676"); CLARO = colors.HexColor("#EEF4FA")
VERDE = colors.HexColor("#2E7D32")

st = {
 "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=22, leading=27, textColor=NAVY, spaceAfter=4),
 "kicker": ParagraphStyle("k", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=AZUL, spaceAfter=2),
 "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13, leading=17, textColor=NAVY, spaceBefore=8, spaceAfter=3),
 "p": ParagraphStyle("p", fontName="Helvetica", fontSize=9.8, leading=13.8, textColor=colors.HexColor("#1F2933"), spaceAfter=4),
 "lead": ParagraphStyle("lead", fontName="Helvetica", fontSize=11.5, leading=16, textColor=CINZA, spaceAfter=8),
 "cell": ParagraphStyle("c", fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor("#1F2933")),
 "cellb": ParagraphStyle("cb", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=colors.white),
 "quote": ParagraphStyle("q", fontName="Helvetica-Oblique", fontSize=12, leading=17, textColor=NAVY, alignment=TA_LEFT),
 "bul": ParagraphStyle("b", fontName="Helvetica", fontSize=10, leading=14.5, leftIndent=12, bulletIndent=0, spaceAfter=2),
}

def P(t, s="p"): return Paragraph(t, st[s])
def bullets(items): return [Paragraph(i, st["bul"], bulletText="•") for i in items]

def tabela(linhas, larguras, cab=AZUL):
    dados = [[Paragraph(c, st["cellb"]) for c in linhas[0]]] + \
            [[Paragraph(c, st["cell"]) for c in l] for l in linhas[1:]]
    t = Table(dados, colWidths=larguras, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), cab),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, CLARO]),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LINEBELOW", (0,0), (-1,-1), 0.3, colors.HexColor("#D5DEE8")),
        ("TOPPADDING", (0,0), (-1,-1), 3.5), ("BOTTOMPADDING", (0,0), (-1,-1), 3.5),
        ("LEFTPADDING", (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6),
    ]))
    return t

def destaque(texto, cor=AZUL):
    t = Table([[Paragraph(texto, st["quote"])]], colWidths=[170*mm])
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),CLARO),("LINEBEFORE",(0,0),(0,-1),4,cor),
        ("LEFTPADDING",(0,0),(-1,-1),12),("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8)]))
    return t

def capa(c, d):
    c.saveState()
    c.setFillColor(NAVY); c.rect(0, 0, W, H, fill=1, stroke=0)
    cx, cy = W/2, H*0.60
    for r, a in [(95, .9), (75, .6), (55, .35)]:
        c.setStrokeColor(CIANO); c.setStrokeAlpha(a); c.setLineWidth(2); c.circle(cx, cy, r)
    c.setStrokeAlpha(1); c.setFillColor(CIANO); c.setFillAlpha(.25); c.circle(cx, cy, 38, fill=1, stroke=0)
    c.setFillAlpha(1); c.setFillColor(CIANO); c.circle(cx, cy, 16, fill=1, stroke=0)
    c.setStrokeColor(LARANJA); c.setLineWidth(3); c.arc(cx-110, cy-110, cx+110, cy+110, 20, 70)
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 40); c.drawCentredString(W/2, H*0.36, "JARVIS")
    c.setFillColor(CIANO); c.setFont("Helvetica", 14); c.drawCentredString(W/2, H*0.36-26, "Briefing  ·  Pitch  ·  MVP")
    c.setFillColor(colors.HexColor("#B0BEC5")); c.setFont("Helvetica", 11)
    c.drawCentredString(W/2, H*0.36-56, "O assistente executivo por voz que trabalha como um chefe de gabinete")
    c.setFont("Helvetica", 9.5)
    c.drawCentredString(W/2, 60, "Erton Rodrigo Linhares Coelho  ·  Linhares Prudêncio Contabilidade e Gestão Empresarial")
    c.drawCentredString(W/2, 46, "Campina Grande/PB  ·  Outubro de 2026  ·  Documento interno")
    c.restoreState()

def pagina(c, d):
    c.saveState()
    c.setFillColor(NAVY); c.rect(0, H-14*mm, W, 14*mm, fill=1, stroke=0)
    c.setFillColor(CIANO); c.setFont("Helvetica-Bold", 9); c.drawString(20*mm, H-9*mm, "JARVIS")
    c.setFillColor(colors.white); c.setFont("Helvetica", 9); c.drawRightString(W-20*mm, H-9*mm, d.secao)
    c.setFillColor(CINZA); c.setFont("Helvetica", 8)
    c.drawString(20*mm, 10*mm, "Linhares Prudêncio · Projeto Jarvis")
    c.drawRightString(W-20*mm, 10*mm, f"p. {d.page}")
    c.restoreState()

class Doc(BaseDocTemplate):
    secao = ""
    def afterFlowable(self, f):
        if hasattr(f, "_secao"): self.secao = f._secao

doc = Doc(OUT, pagesize=A4, title="Jarvis - Briefing, Pitch e MVP", author="Erton Rodrigo Linhares Coelho",
          leftMargin=20*mm, rightMargin=20*mm, topMargin=22*mm, bottomMargin=18*mm)
fr = Frame(20*mm, 18*mm, W-40*mm, H-40*mm, id="f")
doc.addPageTemplates([PageTemplate("capa", [Frame(0,0,W,H)], onPage=capa),
                      PageTemplate("int", [fr], onPageEnd=pagina)])

def secao(nome, kicker, titulo):
    k = P(kicker, "kicker"); k._secao = nome
    return [k, P(titulo, "h1")]

s = [NextPageTemplate("int"), PageBreak()]

# ---------------- BRIEFING
s += secao("1 · Briefing", "PARTE 1 · BRIEFING", "O que estamos construindo e por quê")
s.append(P("O Jarvis é um assistente pessoal por voz que roda no computador do Erton. Ele conversa em tempo real, "
           "lembra do contexto, executa tarefas (planilhas, e-mails, WhatsApp, lembretes, pesquisas) e entrega "
           "um resumo do dia. O objetivo é devolver tempo de liderança: menos operação, mais estratégia.", "lead"))
s.append(P("Contexto", "h2"))
s += bullets([
 "O Erton lidera a Linhares Prudêncio: mais de 40 especialistas e clientes em 23 estados, com foco em grupos empresariais familiares.",
 "A agenda mistura M&amp;A, governança, compliance, sucessão, família e treino de endurance. A informação está espalhada entre Gmail, Agenda, Drive, WhatsApp e sistemas.",
 "Boa parte do dia vai em tarefas de baixo valor: procurar arquivo, redigir e-mail, lembrar prazo, montar planilha.",
])
s.append(P("Objetivos", "h2"))
s.append(tabela([
 ["Objetivo", "Como medimos"],
 ["Economizar tempo operacional do Erton", "Meta: 1 hora por dia a menos em tarefas repetitivas"],
 ["Nunca perder prazo ou compromisso", "Zero prazos fiscais ou reuniões esquecidas no mês"],
 ["Proteger dados de clientes (LGPD e sigilo do CRC)", "100% dos pedidos com dado sensível processados no cérebro privado"],
 ["Começar o dia com clareza", "Briefing das 7h entregue em pelo menos 9 de cada 10 dias úteis"],
], [85*mm, 85*mm]))
s.append(P("Público", "h2"))
s += bullets([
 "<b>Agora:</b> o Erton, como usuário único e principal testador.",
 "<b>Depois:</b> sócios e gestores da Linhares Prudêncio.",
 "<b>Futuro:</b> fundadores e conselheiros dos grupos familiares atendidos, como serviço premium.",
])
s.append(P("Restrições e princípios", "h2"))
s += bullets([
 "<b>Segurança primeiro:</b> o Jarvis nunca envia mensagem ou e-mail sozinho. Sempre prepara e o Erton confirma.",
 "<b>Privacidade por padrão:</b> dado de cliente nunca vai para IA gratuita, que pode usar as conversas para treino.",
 "<b>Custo baixo:</b> usar planos gratuitos onde for seguro (Gemini, Groq) e IA paga só onde agrega (Claude).",
 "<b>Simples de usar:</b> dois cliques para abrir e voz como interface principal.",
])
s.append(Spacer(1, 6))
s.append(destaque("“A gestão, como o Ironman, é uma prova de estratégia, resistência e foco absoluto no resultado.” "
                  "O Jarvis cuida do resto para que o foco fique no que importa."))

# ---------------- PITCH
s.append(PageBreak())
s += secao("2 · Pitch", "PARTE 2 · PITCH", "Chefe de gabinete digital, com sigilo")
s.append(destaque("O Jarvis entrega ao fundador o que um chefe de gabinete entrega: tempo, memória e sigilo.", LARANJA))
s.append(P("O problema", "h2"))
s.append(P("Fundadores e executivos de grupos familiares têm a agenda mais cara da empresa, e mesmo assim gastam horas "
           "com tarefas que não precisariam passar por eles. Os assistentes de IA disponíveis são genéricos, "
           "não entendem a realidade fiscal e societária brasileira e, nos planos gratuitos, podem usar as conversas "
           "para treino. Para quem lida com patrimônio, sucessão e M&amp;A, isso é inaceitável."))
s.append(P("A solução", "h2"))
s.append(P("O Jarvis é um assistente executivo por voz que fala português, conhece o negócio e decide sozinho onde "
           "cada pedido pode ser processado: conversa comum vai para a IA rápida e gratuita; dado de cliente fica "
           "no computador (Gemma 4) ou vai para IA paga sem uso para treino (Claude)."))
s.append(tabela([
 ["Diferencial", "Por que importa"],
 ["Porteiro de privacidade", "Detecta CPF, CNPJ, balanço, contrato e nome de cliente e desvia para o cérebro privado"],
 ["Voz em tempo real", "Conversa natural, pode ser interrompida, com “Hey Jarvis” reconhecido offline"],
 ["Executa, não só responde", "Planilhas, e-mails, WhatsApp, lembretes, pesquisas, posts (Metricool) e rotinas"],
 ["Briefing executivo diário", "Agenda, e-mails importantes e prazos fiscais, por voz ou no Telegram"],
 ["Nunca para", "Se uma IA cair, outra assume sozinha (Gemini, Groq, Gemma)"],
 ["DNA contábil", "Feito por quem vive governança, compliance e reforma tributária todos os dias"],
], [55*mm, 115*mm]))
s.append(P("Para quem", "h2"))
s += bullets([
 "Fundadores e herdeiros de grupos empresariais familiares, clientes da Linhares Prudêncio.",
 "Sócios de escritórios contábeis e de consultoria que querem ganhar escala sem aumentar a equipe.",
 "Executivos com agenda intensa que precisam de sigilo absoluto.",
])
s.append(P("Modelo de negócio (hipótese a validar)", "h2"))
s.append(tabela([
 ["Pacote", "O que inclui", "Como cobrar"],
 ["Jarvis Pessoal", "Assistente por voz, memória, tarefas do dia a dia", "Instalação + mensalidade"],
 ["Jarvis Executivo", "Pessoal + briefing diário + Gmail, Agenda, Drive e Telegram", "Mensalidade por executivo"],
 ["Jarvis Família", "Executivo + cérebro privado + integração com a governança do grupo", "Pacote dentro do contrato de consultoria"],
], [38*mm, 82*mm, 50*mm]))
s.append(P("Valores ainda não definidos. A recomendação é validar com 3 a 5 clientes antes de fixar preço.", "p"))
s.append(P("Por que nós", "h2"))
s.append(P("A Linhares Prudêncio já tem a confiança dos grupos familiares, presença em 23 estados e experiência "
           "em M&amp;A, governança e compliance. O Jarvis não é uma startup tentando conquistar clientes: é um "
           "serviço novo oferecido a quem já confia no escritório. E o produto já existe e funciona no dia a dia do Erton."))

# ---------------- MVP
s.append(PageBreak())
s += secao("3 · MVP", "PARTE 3 · MVP", "O menor Jarvis que já entrega valor")
s.append(P("A boa notícia: boa parte do MVP já está construída neste repositório (pastas <i>jarvis</i> e "
           "<i>jarvis-ultron</i>). O MVP fecha as lacunas que transformam um assistente pessoal em produto.", "lead"))
s.append(P("O que já existe", "h2"))
s.append(tabela([
 ["Recurso", "Situação"],
 ["Conversa por voz em tempo real (Gemini Live), “Hey Jarvis” offline", "Pronto"],
 ["Memória de longo prazo e visão da tela", "Pronto"],
 ["Planilhas, arquivos, código, WhatsApp, Gmail (rascunho), lembretes, pesquisa", "Pronto"],
 ["Reserva automática Groq e cérebro privado Gemma 4 no PC", "Pronto (troca manual)"],
 ["Telegram, Hermes (agentes, rotina das 8h) e Metricool", "Pronto, em teste"],
 ["Telas Orbe, Stark e Ultron", "Pronto"],
], [125*mm, 45*mm], cab=VERDE))
s.append(P("O que o MVP precisa ganhar", "h2"))
s.append(tabela([
 ["#", "Entrega", "Critério de pronto"],
 ["1", "<b>Porteiro de privacidade</b>: troca automática de cérebro quando houver dado sensível",
  "Pedidos com CPF, CNPJ ou nome de cliente nunca chegam ao Gemini gratuito"],
 ["2", "<b>Briefing das 7h</b> com Google Agenda, Gmail e prazos fiscais",
  "Resumo de até 1 minuto, por voz e no Telegram, todo dia útil"],
 ["3", "<b>Busca no Drive</b> por voz", "“Jarvis, ache o contrato do grupo X” abre o arquivo certo"],
 ["4", "<b>Agenda por voz</b>: consultar e marcar compromissos (com confirmação)",
  "Marca reunião em menos de 30 segundos"],
 ["5", "<b>Registro de uso</b> (local) para medir tempo economizado", "Relatório semanal simples"],
], [8*mm, 92*mm, 70*mm]))
s.append(P("Fora do MVP (fica para depois)", "h2"))
s += bullets([
 "Versão para vários usuários, login e painel de administração.",
 "Aplicativo de celular próprio (no MVP o Telegram cumpre esse papel).",
 "Integração com sistemas contábeis (Domínio/Onvio) e ERPs dos clientes.",
 "Envio automático de mensagens sem confirmação.",
])

s.append(PageBreak())
k = P("PARTE 3 · MVP", "kicker"); k._secao = "3 · MVP"; s.append(k)
s.append(P("Plano de 6 semanas", "h1"))
s.append(tabela([
 ["Semana", "Foco", "Resultado"],
 ["1", "Porteiro de privacidade", "Regras de detecção + troca automática Gemini / Gemma / Claude, com testes"],
 ["2", "Google Agenda e Gmail", "Leitura da agenda e dos e-mails importantes"],
 ["3", "Briefing das 7h", "Resumo por voz e no Telegram, com prazos fiscais do mês"],
 ["4", "Drive e agenda por voz", "Buscar arquivos e marcar compromissos com confirmação"],
 ["5", "Uso real pelo Erton", "Ajustes de voz, velocidade e respostas; registro de tempo economizado"],
 ["6", "Piloto com 2 ou 3 pessoas", "Sócios ou um cliente de confiança; coleta de feedback e preço"],
], [18*mm, 52*mm, 100*mm]))
s.append(P("Arquitetura do MVP", "h2"))
s.append(tabela([
 ["Camada", "Tecnologia"],
 ["Interface", "Janela Orbe/Stark no Windows + Telegram no celular"],
 ["Voz", "Gemini Live; “Hey Jarvis” offline; vozes Microsoft e ElevenLabs"],
 ["Porteiro", "Regras locais (CPF, CNPJ, palavras e lista de clientes) decidem o cérebro"],
 ["Cérebros", "Gemini (geral, grátis) · Groq (reserva) · Gemma 4 no PC (privado) · Claude (análises, pago)"],
 ["Ferramentas", "Planilhas, arquivos, WhatsApp, Gmail, Agenda, Drive, lembretes, pesquisa, Metricool"],
 ["Memória e dados", "Arquivos locais em Documentos\\Jarvis, sem nuvem de terceiros"],
], [35*mm, 135*mm]))
s.append(P("Indicadores de sucesso do MVP", "h2"))
s += bullets([
 "Pelo menos <b>1 hora por dia</b> economizada, medida pelo registro de uso.",
 "<b>Zero</b> vazamento de dado de cliente para IA gratuita.",
 "Briefing entregue em <b>90%</b> dos dias úteis.",
 "Uso diário por <b>4 semanas seguidas</b> sem abandono.",
 "Pelo menos <b>2 de 3</b> pilotos dizendo que pagariam pelo serviço.",
])
s.append(P("Riscos e como tratar", "h2"))
s.append(tabela([
 ["Risco", "Tratamento"],
 ["Cota gratuita do Gemini acabar", "Reserva automática no Groq e na Gemma"],
 ["PC sem memória para a Gemma", "Instalador escolhe o tamanho certo; alternativa Claude"],
 ["Dado sensível passar pelo porteiro", "Regras conservadoras: na dúvida, vai para o cérebro privado"],
 ["Ação errada (e-mail, mensagem)", "Toda ação externa exige confirmação"],
], [70*mm, 100*mm]))
s.append(Spacer(1, 8))
s.append(destaque("Próximo passo: começar pela semana 1, o porteiro de privacidade. "
                  "É ele que torna o Jarvis seguro para o trabalho com clientes."))

doc.build(s)
