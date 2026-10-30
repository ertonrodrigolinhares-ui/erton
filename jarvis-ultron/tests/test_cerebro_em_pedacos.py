"""Etapa 15: a JarvisLive (main.py) é montada com pedaços que moram em cerebro/*.py.

Cada pedaço tem os mesmos nomes de função de antes; este arquivo diz em qual arquivo cada assunto mora
(quando algo falhar, dá para dizer "olha o cerebro/reserva.py"). E garante o combinado do plano: nenhum
pedaço lê o os.environ nem cria cliente do Gemini ao ser importado, e nenhum importa o main.py (senão
vira um laço: o main importa os pedaços)."""

import ast
import subprocess
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

# arquivo -> (classe, os métodos e atributos de classe que moram lá)
PEDACOS = {
    "cerebro/avisos.py": ("Avisos", {
        "anunciar", "_trava_avisos", "_falar_aviso", "_falar_no_pc", "_falar_avisos_guardados",
        "_notificar_na_tela", "_chamada_fechada", "_pode_falar_agora",
        "AVISO_ESPERA_AO_CHAMAR", "VOZ_DO_PC_ESPERA", "RESPOSTA_DIGITADA_FALA",
    }),
    "cerebro/escuta.py": ("Escuta", {
        "_definir_modo_escuta", "_aviso_de_escuta", "_mostrar_selo", "_mostrar_volume",
    }),
    "cerebro/pontes.py": ("Pontes", {
        "_hermes_sem_travar", "_entregar_resultado_hermes", "HERMES_ESPERA",
        "_geekie_pendencias", "_verificar_lembretes_geekie", "_iniciar_lembretes_geekie",
        "_autodiagnostico", "_preparar_automacoes",
    }),
    "cerebro/voz_saida.py": ("VozSaida", {
        "set_speaking", "speak", "_speak_vision_result", "speak_error", "update_voice", "_get_current_voice",
        "_idioma_voz", "_falar_com_voz_externa",
    }),
    "cerebro/ultron.py": ("Ultron", {
        "_pedido_de_ultron", "rodar_automacao_ultron", "_falar_resultado_ultron",
    }),
    "cerebro/desligar.py": ("Desligar", {
        "_is_explicit_self_quit_transcript", "_queue_self_quit_after_farewell", "_force_complete_self_quit",
        "_mark_self_quit_farewell_received", "_complete_self_quit_after_audio", "request_shutdown",
        "_suspender", "_voltar_da_suspensao",
    }),
    "cerebro/entrada.py": ("Entrada", {
        "_on_text_command", "_avisar_se_nao_enviou", "_nova_fala", "_trava_da_fala", "_trava_textos",
        "_guardar_ate_conectar", "_mandar_textos_esperando", "send_text", "send_audio_chunk",
        "_microfone_mandou_audio",
    }),
    "cerebro/reserva.py": ("Reserva", {
        "_ativar_modo_reserva", "_ligar_cerebro_gemma", "_desativar_modo_reserva", "_responder_pela_reserva",
        "_avisar_sem_ouvido", "_ferramentas_da_reserva", "_garantir_loop_reserva", "_executar_ferramenta_reserva",
        "_falar_reserva", "_escutar_reserva", "RESERVA_FERRAMENTAS_ESSENCIAIS",
    }),
}


def _nomes_da_classe(classe) -> set[str]:
    return {nome for nome in vars(classe) if not nome.startswith("__")}


class PedacosTests(unittest.TestCase):
    def test_cada_assunto_mora_no_arquivo_combinado(self):
        import importlib

        import main

        for arquivo, (nome_da_classe, nomes) in PEDACOS.items():
            with self.subTest(arquivo=arquivo):
                modulo = importlib.import_module(arquivo[:-3].replace("/", "."))
                classe = getattr(modulo, nome_da_classe)
                self.assertEqual(_nomes_da_classe(classe), nomes)
                self.assertIn(classe, main.JarvisLive.__mro__, f"a JarvisLive não é montada com {nome_da_classe}")

    def test_nenhum_metodo_fica_em_dois_lugares(self):
        import main

        vistos = {}
        for classe in main.JarvisLive.__mro__[:-1]:  # sem o object
            for nome in _nomes_da_classe(classe):
                self.assertNotIn(nome, vistos, f"{nome} está em {classe.__name__} e em {vistos.get(nome)}")
                vistos[nome] = classe.__name__

    def test_nenhum_pedaco_le_o_ambiente_nem_cria_cliente_ao_ser_importado(self):
        for arquivo in PEDACOS:
            with self.subTest(arquivo=arquivo):
                arvore = ast.parse((RAIZ / arquivo).read_text(encoding="utf-8"))
                fora_de_funcao = [no for no in arvore.body
                                  if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                                  and not (isinstance(no, ast.Expr) and isinstance(no.value, ast.Constant))]
                texto = ast.unparse(ast.Module(body=fora_de_funcao, type_ignores=[]))
                self.assertNotIn("environ", texto, f"{arquivo} lê o os.environ ao ser importado")
                self.assertNotIn("genai", texto, f"{arquivo} mexe no Gemini ao ser importado")
                self.assertNotIn("from main", texto, f"{arquivo} importa o main.py")
                self.assertNotIn("import main", texto, f"{arquivo} importa o main.py")

    def test_importar_um_pedaco_nao_puxa_o_main(self):
        modulos = [arquivo[:-3].replace("/", ".") for arquivo in PEDACOS]
        codigo = ("import sys\n"
                  + "".join(f"import {m}\n" for m in modulos)
                  + "assert 'main' not in sys.modules, 'importar um pedaço puxou o main.py'\n")
        rodou = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True)
        self.assertEqual(rodou.returncode, 0, rodou.stderr[-2000:])


if __name__ == "__main__":
    unittest.main()
