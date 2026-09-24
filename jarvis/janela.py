"""Janela do Jarvis: conversa, microfone, modo mãos livres e configuração da chave.

Feita com tkinter, que já vem junto com o Python no Windows.
"""

import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, simpledialog

from . import ao_vivo, voz
from .assistente import remover_palavra_ativacao, responder, saudacao
from .config import SITE_CHAVE_GROQ, Config, salvar_no_env
from .ia import criar_cerebro

FUNDO = "#0b1220"
PAINEL = "#111a2e"
DESTAQUE = "#22d3ee"
TEXTO = "#e2e8f0"
APAGADO = "#94a3b8"
FONTE = ("Segoe UI", 11)

# O que aparece no topo da janela enquanto a IA usa cada ferramenta.
ACOES = {
    "listar_arquivos": "Olhando a pasta...", "ler_arquivo_texto": "Lendo o arquivo...",
    "salvar_arquivo_texto": "Salvando arquivo...", "abrir": "Abrindo...",
    "ler_planilha": "Lendo a planilha...", "criar_planilha": "Criando a planilha...",
    "adicionar_linhas_planilha": "Atualizando a planilha...",
    "executar_codigo_python": "Executando código...", "salvar_contato": "Salvando contato...",
    "preparar_whatsapp": "Preparando o WhatsApp...", "preparar_email": "Preparando o e-mail...",
    "criar_lembrete": "Criando lembrete...", "pesquisar_internet": "Pesquisando na internet...",
    "lembrar_informacao": "Guardando na memória...", "esquecer_informacao": "Apagando da memória...",
    "ver_tela": "Olhando a tela...",
}

PASSOS_GROQ = (
    "Se o Gemini travar ou atingir o limite, o Groq responde no lugar.\n"
    "1. Clique em \"Abrir site do Groq\" e entre com a sua conta do Google.\n"
    "2. Clique em \"Create API Key\", dê o nome Jarvis e copie a chave (começa com gsk_).\n"
    "3. Cole no campo abaixo."
)

PASSOS_CHAVE = {
    "gemini": (
        "1. Clique em \"Abrir site do Google\" e entre com a sua conta Gmail.\n"
        "2. Clique em \"Create API key\" (Criar chave de API).\n"
        "3. Copie a chave (começa com AIza...) e cole no campo abaixo.\n\n"
        "É gratuito e não pede cartão de crédito."
    ),
    "claude": (
        "1. Clique em \"Abrir site\" e entre na sua conta da Anthropic.\n"
        "2. Clique em \"Create Key\".\n"
        "3. Copie a chave (começa com sk-ant-...) e cole no campo abaixo."
    ),
}


class JanelaJarvis:
    def __init__(self, raiz: tk.Tk):
        self.raiz = raiz
        self.config = Config.carregar()
        self.cerebro = None
        self.ocupado = False
        self.eventos: queue.Queue = queue.Queue()
        self.falador = voz.Falador.da_config(self.config)
        self.falar_respostas = tk.BooleanVar(value=voz.fala_disponivel())
        self.maos_livres = tk.BooleanVar(value=False)
        self.escuta_ativa = False  # cópia simples de maos_livres, lida pela thread do microfone
        self.thread_escuta = None
        self.sessao_ao_vivo = None

        self._montar_tela()
        self.raiz.protocol("WM_DELETE_WINDOW", self.fechar)
        self._carregar_cerebro()
        self.raiz.after(100, self._atender_eventos)

        self.mostrar("Jarvis", saudacao(self.config.nome_usuario), falar=True)
        if self.cerebro is None:
            self.raiz.after(400, self.pedir_chave)

    # ---------- montagem da tela ----------

    def _montar_tela(self) -> None:
        r = self.raiz
        r.title("Jarvis")
        r.geometry("720x760")
        r.minsize(420, 480)
        r.configure(bg=FUNDO)

        topo = tk.Frame(r, bg=FUNDO)
        topo.pack(fill="x", padx=16, pady=(14, 6))
        tk.Label(topo, text="J.A.R.V.I.S.", font=("Segoe UI", 20, "bold"),
                 fg=DESTAQUE, bg=FUNDO).pack(side="left")
        self.status = tk.Label(topo, text="Pronto", font=("Segoe UI", 10), fg=APAGADO, bg=FUNDO)
        self.status.pack(side="right")

        barra_ao_vivo = tk.Frame(r, bg=FUNDO)
        barra_ao_vivo.pack(fill="x", padx=16, pady=(0, 4))
        self.botao_ao_vivo = self._botao(barra_ao_vivo, "⚡ Ligar conversa ao vivo",
                                         self.alternar_ao_vivo, destaque=True)
        self.botao_ao_vivo.pack(side="left")
        tk.Label(barra_ao_vivo, text="Voz ao vivo:", bg=FUNDO, fg=APAGADO,
                 font=("Segoe UI", 10)).pack(side="left", padx=(12, 0))
        voz_inicial = self.config.voz_ao_vivo if self.config.voz_ao_vivo in ao_vivo.VOZES_AO_VIVO else "Charon"
        self.escolha_voz_ao_vivo = tk.StringVar(value=ao_vivo.VOZES_AO_VIVO[voz_inicial])
        self._lista(barra_ao_vivo, self.escolha_voz_ao_vivo, list(ao_vivo.VOZES_AO_VIVO.values()),
                    self.trocar_voz_ao_vivo).pack(side="left", padx=(6, 0))

        quadro = tk.Frame(r, bg=PAINEL)
        quadro.pack(fill="both", expand=True, padx=16, pady=6)
        barra = tk.Scrollbar(quadro)
        barra.pack(side="right", fill="y")
        self.conversa = tk.Text(quadro, wrap="word", font=FONTE, bg=PAINEL, fg=TEXTO,
                                relief="flat", padx=12, pady=10, state="disabled",
                                yscrollcommand=barra.set, cursor="arrow")
        self.conversa.pack(fill="both", expand=True)
        barra.config(command=self.conversa.yview)
        self.conversa.tag_configure("Jarvis", foreground=DESTAQUE, font=("Segoe UI", 11, "bold"))
        self.conversa.tag_configure("Você", foreground="#a5b4fc", font=("Segoe UI", 11, "bold"))

        entrada = tk.Frame(r, bg=FUNDO)
        entrada.pack(fill="x", padx=16, pady=6)
        self.caixa = tk.Entry(entrada, font=("Segoe UI", 12), bg=PAINEL, fg=TEXTO,
                              insertbackground=TEXTO, relief="flat")
        self.caixa.pack(side="left", fill="x", expand=True, ipady=8)
        self.caixa.bind("<Return>", lambda _e: self.enviar_digitado())
        self.caixa.focus_set()
        self._botao(entrada, "Enviar", self.enviar_digitado).pack(side="left", padx=(8, 0))
        self.botao_microfone = self._botao(entrada, "🎤 Falar", self.ouvir, destaque=True)
        self.botao_microfone.pack(side="left", padx=(8, 0))

        linha_voz = tk.Frame(r, bg=FUNDO)
        linha_voz.pack(fill="x", padx=16, pady=(0, 6))
        tk.Label(linha_voz, text="Voz:", bg=FUNDO, fg=APAGADO, font=("Segoe UI", 10)).pack(side="left")
        self.escolha_voz = tk.StringVar(value=voz.VOZES[self.falador.voz][0])
        self._lista(linha_voz, self.escolha_voz, [n for n, _ in voz.VOZES.values()],
                    self.trocar_voz).pack(side="left", padx=(6, 10))
        tk.Label(linha_voz, text="Efeito:", bg=FUNDO, fg=APAGADO, font=("Segoe UI", 10)).pack(side="left")
        self.escolha_efeito = tk.StringVar(value=voz.EFEITOS[self.falador.efeito][0])
        self._lista(linha_voz, self.escolha_efeito, [n for n, *_ in voz.EFEITOS.values()],
                    self.trocar_efeito).pack(side="left", padx=(6, 10))
        self._botao(linha_voz, "▶ Testar", self.testar_voz).pack(side="right")

        rodape = tk.Frame(r, bg=FUNDO)
        rodape.pack(fill="x", padx=16, pady=(0, 12))
        tk.Checkbutton(rodape, text="Falar as respostas", variable=self.falar_respostas,
                       bg=FUNDO, fg=APAGADO, selectcolor=PAINEL, activebackground=FUNDO,
                       activeforeground=TEXTO, font=("Segoe UI", 10)).pack(side="left")
        self.caixa_maos_livres = tk.Checkbutton(rodape, text="Mãos livres", variable=self.maos_livres,
                       command=self.alternar_maos_livres, bg=FUNDO, fg=APAGADO, selectcolor=PAINEL,
                       activebackground=FUNDO, activeforeground=TEXTO,
                       font=("Segoe UI", 10))
        self.caixa_maos_livres.pack(side="left", padx=(10, 0))
        self._botao(rodape, "Trocar chave", self.pedir_chave).pack(side="right")
        self._botao(rodape, "Nova conversa", lambda: self.enviar("nova conversa")).pack(side="right", padx=8)

    def _lista(self, pai, variavel, opcoes, ao_escolher) -> tk.OptionMenu:
        menu = tk.OptionMenu(pai, variavel, *opcoes, command=ao_escolher)
        menu.config(bg=PAINEL, fg=TEXTO, activebackground=DESTAQUE, activeforeground=FUNDO,
                    relief="flat", highlightthickness=0, font=("Segoe UI", 10))
        menu["menu"].config(bg=PAINEL, fg=TEXTO, activebackground=DESTAQUE,
                            activeforeground=FUNDO, font=("Segoe UI", 10))
        return menu

    def _botao(self, pai, texto, comando, destaque=False) -> tk.Button:
        return tk.Button(pai, text=texto, command=comando, font=("Segoe UI", 10, "bold"),
                         bg=DESTAQUE if destaque else PAINEL, fg=FUNDO if destaque else TEXTO,
                         activebackground=DESTAQUE, activeforeground=FUNDO,
                         relief="flat", padx=12, pady=6, cursor="hand2")

    # ---------- conversa ----------

    def mostrar(self, quem: str, texto: str, falar: bool = False) -> None:
        self.conversa.configure(state="normal")
        self.conversa.insert("end", f"{quem}: ", quem)
        self.conversa.insert("end", f"{texto}\n\n")
        self.conversa.configure(state="disabled")
        self.conversa.see("end")
        if falar and self.falar_respostas.get():
            self.falador.falar(texto)

    def enviar_digitado(self) -> None:
        texto = self.caixa.get().strip()
        if texto:
            self.caixa.delete(0, "end")
            self.enviar(texto)

    def enviar(self, texto: str) -> None:
        if self.sessao_ao_vivo:
            self.mostrar("Você", texto)
            self.sessao_ao_vivo.enviar_texto(texto)
            return
        if self.ocupado:
            return
        self.ocupado = True
        self.mostrar("Você", texto)
        self.status.config(text="Pensando...", fg=DESTAQUE)
        threading.Thread(target=self._processar, args=(texto,), daemon=True).start()

    def _processar(self, texto: str) -> None:
        try:
            resposta, acao = responder(texto, self.cerebro, self.config.nome_usuario)
        except Exception as erro:  # nunca deixar a janela travada em "Pensando..."
            resposta, acao = f"Tive um problema inesperado: {erro}", None
        self.eventos.put(lambda: self._concluir(resposta, acao))

    def _concluir(self, resposta: str, acao: str | None) -> None:
        self.ocupado = False
        self._status_normal()
        if getattr(self.cerebro, "respondeu_pela_reserva", False):
            self.status.config(text="Gemini indisponível: respondi pelo Groq (reserva)", fg=APAGADO)
        self.mostrar("Jarvis", resposta, falar=True)
        if acao == "sair":
            self.raiz.after(2500, self.raiz.destroy)

    # ---------- microfone ----------

    def ouvir(self) -> None:
        if self.ocupado:
            return
        problema = voz.diagnostico_microfone()
        if problema:
            messagebox.showinfo("Microfone", problema)
            return
        self.ocupado = True
        self.botao_microfone.config(state="disabled")
        self.status.config(text="Ouvindo... pode falar", fg=DESTAQUE)
        threading.Thread(target=self._escutar, daemon=True).start()

    def _escutar(self) -> None:
        self.falador.aguardar()
        try:
            texto = voz.ouvir_microfone(self.config.idioma)
        except Exception:
            texto = ""
        self.eventos.put(lambda: self._escutou(texto))

    def _escutou(self, texto: str) -> None:
        self.ocupado = False
        self.botao_microfone.config(state="normal")
        if texto:
            self.enviar(texto)
        else:
            self.status.config(text="Não entendi. Clique em Falar e tente de novo.", fg=APAGADO)

    # ---------- mãos livres: fica ouvindo e responde quando escuta "Jarvis" ----------

    def alternar_maos_livres(self) -> None:
        self.escuta_ativa = self.maos_livres.get()
        if not self.escuta_ativa:
            self.botao_microfone.config(state="normal")
            self._status_normal()
            return
        problema = voz.diagnostico_microfone()
        if problema:
            self.maos_livres.set(False)
            self.escuta_ativa = False
            messagebox.showinfo("Microfone", problema)
            return
        self.falar_respostas.set(voz.fala_disponivel())
        self.botao_microfone.config(state="disabled")
        palavra = self.config.palavra_ativacao.capitalize()
        self.mostrar("Jarvis", f"Modo mãos livres ligado. É só dizer \"{palavra}\" e o seu pedido.", falar=True)
        self._status_normal()
        if self.thread_escuta is None or not self.thread_escuta.is_alive():
            self.thread_escuta = threading.Thread(target=self._escutar_sempre, daemon=True)
            self.thread_escuta.start()

    def _escutar_sempre(self) -> None:
        palavra = self.config.palavra_ativacao
        aguardando_pedido = False
        while self.escuta_ativa:
            if self.ocupado:
                threading.Event().wait(0.3)
                continue
            self.falador.aguardar()
            try:
                ouvido = voz.ouvir_microfone(self.config.idioma)
            except Exception:
                threading.Event().wait(1)
                continue
            if not ouvido or not self.escuta_ativa:
                continue
            pedido = ouvido if aguardando_pedido else remover_palavra_ativacao(ouvido, palavra)
            if aguardando_pedido or pedido:
                aguardando_pedido = False
                self.eventos.put(lambda p=pedido: self.enviar(p))
            elif palavra in ouvido.lower():
                # Disse só "Jarvis": responde e escuta o próximo pedido.
                aguardando_pedido = True
                self.eventos.put(lambda: self.mostrar("Jarvis", "Pois não?", falar=True))

    def _status_normal(self) -> None:
        if self.escuta_ativa:
            texto = f"Ouvindo... diga \"{self.config.palavra_ativacao.capitalize()}\""
            self.status.config(text=texto, fg=DESTAQUE)
        else:
            self.status.config(text="Pronto", fg=APAGADO)

    # ---------- chamadas das ferramentas (vêm de outra thread) ----------

    def _na_janela(self, funcao):
        """Roda `funcao` na thread da janela e espera o resultado."""
        pronto = threading.Event()
        resultado = {}

        def executar():
            resultado["valor"] = funcao()
            pronto.set()

        self.eventos.put(executar)
        pronto.wait()
        return resultado["valor"]

    def confirmar(self, titulo: str, detalhe: str) -> bool:
        def perguntar():
            self.raiz.deiconify()
            self.raiz.lift()
            if self.falar_respostas.get() and not self.sessao_ao_vivo:
                self.falador.falar("Preciso da sua confirmação na tela.")
            return messagebox.askyesno(titulo, detalhe, parent=self.raiz)
        return self._na_janela(perguntar)

    def avisar(self, texto: str) -> None:
        def mostrar_aviso():
            self.raiz.deiconify()
            self.raiz.lift()
            self.raiz.attributes("-topmost", True)
            self.raiz.after(1500, lambda: self.raiz.attributes("-topmost", False))
            if self.sessao_ao_vivo:  # no modo ao vivo, quem avisa é a própria voz do Gemini
                self.mostrar("Jarvis", texto)
                self.sessao_ao_vivo.enviar_texto(f"(Aviso do sistema, diga ao usuário agora: {texto})")
            else:
                self.mostrar("Jarvis", texto, falar=True)
        self.eventos.put(mostrar_aviso)

    def ao_usar(self, ferramenta: str) -> None:
        texto = ACOES.get(ferramenta, "Trabalhando...")
        self.eventos.put(lambda: self.status.config(text=texto, fg=DESTAQUE))

    # ---------- conversa ao vivo (Gemini Live) ----------

    def alternar_ao_vivo(self) -> None:
        if self.sessao_ao_vivo:
            self.botao_ao_vivo.config(text="Desligando...", state="disabled")
            self.sessao_ao_vivo.parar()
            return
        if self.config.ia != "gemini" or not self.config.chave_api or self.cerebro is None:
            messagebox.showinfo("Ao vivo", "O modo ao vivo usa o Gemini. Configure a chave do Gemini primeiro.")
            return
        problema = voz.diagnostico_microfone()
        if problema:
            messagebox.showinfo("Microfone", problema)
            return
        if self.escuta_ativa:
            self.maos_livres.set(False)
            self.alternar_maos_livres()
        voz_escolhida = next(k for k, v in ao_vivo.VOZES_AO_VIVO.items() if v == self.escolha_voz_ao_vivo.get())
        self.sessao_ao_vivo = ao_vivo.SessaoAoVivo(
            chave=self.config.chave_api, usuario=self.config.nome_usuario, voz_ao_vivo=voz_escolhida,
            efeito=self.falador.efeito, ferramentas=getattr(self.cerebro, "ferramentas", []),
            ao_texto=lambda quem, texto: self.eventos.put(lambda: self.mostrar(quem, texto)),
            ao_estado=lambda texto: self.eventos.put(lambda: self.status.config(text=texto, fg=DESTAQUE)),
            ao_terminar=lambda mensagem: self.eventos.put(lambda: self._ao_vivo_terminou(mensagem)),
            modelo=self.config.modelo_ao_vivo,
        )
        self.sessao_ao_vivo.iniciar()
        self.botao_ao_vivo.config(text="⏹ Desligar conversa ao vivo")
        self.botao_microfone.config(state="disabled")
        self.caixa_maos_livres.config(state="disabled")
        self.mostrar("Jarvis", "Modo ao vivo ligado: é só falar comigo, sem apertar nada. "
                               "Posso ser interrompido a qualquer momento.")

    def _ao_vivo_terminou(self, mensagem: str | None) -> None:
        self.sessao_ao_vivo = None
        self.botao_ao_vivo.config(text="⚡ Ligar conversa ao vivo", state="normal")
        self.botao_microfone.config(state="normal")
        self.caixa_maos_livres.config(state="normal")
        self._status_normal()
        self.mostrar("Jarvis", mensagem or "Modo ao vivo desligado.")

    def trocar_voz_ao_vivo(self, nome: str) -> None:
        chave = next(k for k, v in ao_vivo.VOZES_AO_VIVO.items() if v == nome)
        salvar_no_env("JARVIS_VOZ_AO_VIVO", chave)
        if self.sessao_ao_vivo:
            self.mostrar("Jarvis", f"A voz {chave} vale na próxima vez que você ligar o modo ao vivo.")

    def fechar(self) -> None:
        if self.sessao_ao_vivo:
            self.sessao_ao_vivo.parar()
        self.raiz.destroy()

    # ---------- voz ----------

    def trocar_voz(self, nome: str) -> None:
        chave = next(k for k, (n, _) in voz.VOZES.items() if n == nome)
        if chave == "elevenlabs" and not self._configurar_elevenlabs():
            self.escolha_voz.set(voz.VOZES[self.falador.voz][0])
            return
        self.falador.voz = chave
        salvar_no_env("JARVIS_VOZ", chave)
        self.testar_voz()

    def trocar_efeito(self, nome: str) -> None:
        chave = next(k for k, (n, *_) in voz.EFEITOS.items() if n == nome)
        self.falador.efeito = chave
        salvar_no_env("JARVIS_EFEITO_VOZ", chave)
        self.testar_voz()

    def testar_voz(self) -> None:
        if not voz.fala_disponivel():
            messagebox.showinfo("Voz", "Faltam componentes de voz: " + ", ".join(voz.componentes_faltando()) +
                                ".\n\nFeche o Jarvis e abra o 'Iniciar Jarvis' de novo para reinstalar. "
                                "Se continuar, envie o arquivo instalacao-log.txt da pasta do Jarvis.")
            return
        self.falador.falar(f"Olá, {self.config.nome_usuario}. Esta é a minha nova voz. Como posso ajudar?")
        self.raiz.after(8000, self._verificar_voz)

    def _verificar_voz(self) -> None:
        if self.falador.ultimo_erro:
            motivo = "sem internet?" if "connect" in self.falador.ultimo_erro.lower() else "veja a chave"
            self.status.config(text=f"A voz escolhida falhou ({motivo}); usei a do Windows.", fg=APAGADO)

    def _configurar_elevenlabs(self) -> bool:
        chave = simpledialog.askstring(
            "ElevenLabs",
            "Cole a sua chave da ElevenLabs.\n\nCrie de graça em elevenlabs.io:\n"
            "entre na conta > clique no seu nome > API Keys > Create.",
            initialvalue=self.falador.chave_elevenlabs, show="•", parent=self.raiz)
        if not chave:
            return False
        voz_id = simpledialog.askstring(
            "ElevenLabs",
            "Opcional: cole o ID da voz que você escolheu na biblioteca da ElevenLabs\n"
            "(Voices > escolha a voz > copiar Voice ID).\n\nDeixe em branco para usar a voz padrão.",
            initialvalue=self.falador.voz_elevenlabs, parent=self.raiz) or ""
        salvar_no_env("ELEVENLABS_API_KEY", chave.strip())
        salvar_no_env("ELEVENLABS_VOZ_ID", voz_id.strip())
        self.falador.chave_elevenlabs = chave.strip()
        self.falador.voz_elevenlabs = voz_id.strip()
        return True

    # ---------- chave da IA ----------

    def _carregar_cerebro(self) -> None:
        try:
            self.cerebro = criar_cerebro(self.config, confirmar=self.confirmar,
                                         avisar=self.avisar, ao_usar=self.ao_usar)
        except Exception as erro:
            self.cerebro = None
            messagebox.showerror("Jarvis", f"Não consegui iniciar a IA: {erro}")

    def pedir_chave(self) -> None:
        janela = tk.Toplevel(self.raiz, bg=FUNDO, padx=20, pady=16)
        janela.title("Chaves da IA")
        janela.transient(self.raiz)
        janela.grab_set()
        nome_ia = "Google Gemini" if self.config.ia == "gemini" else "Claude"

        tk.Label(janela, text=f"Configurar a chave do {nome_ia}", font=("Segoe UI", 13, "bold"),
                 fg=DESTAQUE, bg=FUNDO).pack(anchor="w")
        tk.Label(janela, text=PASSOS_CHAVE[self.config.ia], justify="left", font=FONTE,
                 fg=TEXTO, bg=FUNDO).pack(anchor="w", pady=10)
        rotulo_site = "Abrir site do Google" if self.config.ia == "gemini" else "Abrir site"
        self._botao(janela, rotulo_site, lambda: webbrowser.open(self.config.site_chave),
                    destaque=True).pack(anchor="w")

        campo = tk.Entry(janela, font=("Segoe UI", 12), width=48, bg=PAINEL, fg=TEXTO,
                         insertbackground=TEXTO, relief="flat", show="•")
        campo.pack(fill="x", pady=(14, 8), ipady=6)
        campo.insert(0, self.config.chave_api)
        campo.focus_set()

        # ---- reserva opcional: Groq ----
        tk.Frame(janela, bg=PAINEL, height=1).pack(fill="x", pady=(10, 10))
        tk.Label(janela, text="Reserva (opcional): Groq, grátis", font=("Segoe UI", 12, "bold"),
                 fg=DESTAQUE, bg=FUNDO).pack(anchor="w")
        tk.Label(janela, text=PASSOS_GROQ, justify="left", font=FONTE, fg=TEXTO,
                 bg=FUNDO).pack(anchor="w", pady=8)
        self._botao(janela, "Abrir site do Groq", lambda: webbrowser.open(SITE_CHAVE_GROQ)).pack(anchor="w")
        campo_groq = tk.Entry(janela, font=("Segoe UI", 12), width=48, bg=PAINEL, fg=TEXTO,
                              insertbackground=TEXTO, relief="flat", show="•")
        campo_groq.pack(fill="x", pady=(10, 8), ipady=6)
        campo_groq.insert(0, self.config.chave_groq)

        def salvar() -> None:
            chave = campo.get().strip()
            chave_groq = campo_groq.get().strip()
            if not chave and not chave_groq:
                messagebox.showwarning("Chave", "Cole pelo menos uma chave antes de salvar.", parent=janela)
                return
            if chave:
                salvar_no_env(self.config.nome_chave, chave)
            if chave_groq != self.config.chave_groq:
                salvar_no_env("GROQ_API_KEY", chave_groq)
            self.config = Config.carregar()
            self._carregar_cerebro()
            janela.destroy()
            if self.cerebro:
                reserva = " O Groq está pronto como reserva." if chave and chave_groq else ""
                self.mostrar("Jarvis", "Chaves salvas. Agora posso conversar sobre qualquer assunto." + reserva,
                             falar=True)

        campo.bind("<Return>", lambda _e: salvar())
        campo_groq.bind("<Return>", lambda _e: salvar())
        self._botao(janela, "Salvar", salvar).pack(anchor="e")

    # ---------- infraestrutura ----------

    def _atender_eventos(self) -> None:
        """Executa na thread da janela o que as threads de fundo pediram."""
        while not self.eventos.empty():
            self.eventos.get()()
        self.raiz.after(100, self._atender_eventos)


def abrir() -> None:
    raiz = tk.Tk()
    JanelaJarvis(raiz)
    raiz.mainloop()


if __name__ == "__main__":
    abrir()
