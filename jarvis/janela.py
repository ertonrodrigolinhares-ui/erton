"""Janela do Jarvis: caixa de conversa, botão de microfone e configuração da chave.

Feita com tkinter, que já vem junto com o Python no Windows.
"""

import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox

from . import voz
from .assistente import responder, saudacao
from .config import Config, salvar_no_env
from .ia import criar_cerebro

FUNDO = "#0b1220"
PAINEL = "#111a2e"
DESTAQUE = "#22d3ee"
TEXTO = "#e2e8f0"
APAGADO = "#94a3b8"
FONTE = ("Segoe UI", 11)

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
        self.falador = voz.Falador()
        self.falar_respostas = tk.BooleanVar(value=voz.fala_disponivel())

        self._montar_tela()
        self._carregar_cerebro()
        self.raiz.after(100, self._atender_eventos)

        self.mostrar("Jarvis", saudacao(self.config.nome_usuario), falar=True)
        if self.cerebro is None:
            self.raiz.after(400, self.pedir_chave)

    # ---------- montagem da tela ----------

    def _montar_tela(self) -> None:
        r = self.raiz
        r.title("Jarvis")
        r.geometry("600x700")
        r.minsize(420, 480)
        r.configure(bg=FUNDO)

        topo = tk.Frame(r, bg=FUNDO)
        topo.pack(fill="x", padx=16, pady=(14, 6))
        tk.Label(topo, text="J.A.R.V.I.S.", font=("Segoe UI", 20, "bold"),
                 fg=DESTAQUE, bg=FUNDO).pack(side="left")
        self.status = tk.Label(topo, text="Pronto", font=("Segoe UI", 10), fg=APAGADO, bg=FUNDO)
        self.status.pack(side="right")

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

        rodape = tk.Frame(r, bg=FUNDO)
        rodape.pack(fill="x", padx=16, pady=(0, 12))
        tk.Checkbutton(rodape, text="Falar as respostas", variable=self.falar_respostas,
                       bg=FUNDO, fg=APAGADO, selectcolor=PAINEL, activebackground=FUNDO,
                       activeforeground=TEXTO, font=("Segoe UI", 10)).pack(side="left")
        self._botao(rodape, "Trocar chave", self.pedir_chave).pack(side="right")
        self._botao(rodape, "Nova conversa", lambda: self.enviar("nova conversa")).pack(side="right", padx=8)

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
        self.status.config(text="Pronto", fg=APAGADO)
        self.mostrar("Jarvis", resposta, falar=True)
        if acao == "sair":
            self.raiz.after(2500, self.raiz.destroy)

    # ---------- microfone ----------

    def ouvir(self) -> None:
        if self.ocupado:
            return
        if not voz.microfone_disponivel():
            messagebox.showinfo("Microfone", "Não encontrei um microfone. Verifique se ele está "
                                "conectado e liberado em Configurações > Privacidade > Microfone.")
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

    # ---------- chave da IA ----------

    def _carregar_cerebro(self) -> None:
        try:
            self.cerebro = criar_cerebro(self.config)
        except Exception as erro:
            self.cerebro = None
            messagebox.showerror("Jarvis", f"Não consegui iniciar a IA: {erro}")

    def pedir_chave(self) -> None:
        janela = tk.Toplevel(self.raiz, bg=FUNDO, padx=20, pady=16)
        janela.title("Chave da IA")
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

        def salvar() -> None:
            chave = campo.get().strip()
            if not chave:
                messagebox.showwarning("Chave", "Cole a chave no campo antes de salvar.", parent=janela)
                return
            salvar_no_env(self.config.nome_chave, chave)
            self._carregar_cerebro()
            janela.destroy()
            if self.cerebro:
                self.mostrar("Jarvis", "Chave salva. Agora posso conversar sobre qualquer assunto.", falar=True)

        campo.bind("<Return>", lambda _e: salvar())
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
