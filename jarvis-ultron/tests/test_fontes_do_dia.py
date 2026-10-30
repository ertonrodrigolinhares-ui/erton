"""Etapa 9 da reorganização: clima falado, notícias, mapa e saudação. Nenhum teste usa a internet."""

import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from core import fontes_do_dia  # noqa: E402

CLIMA = {
    "current_condition": [{"temp_C": "27", "FeelsLikeC": "29", "humidity": "70",
                           "lang_pt": [{"value": "Parcialmente nublado"}], "weatherDesc": [{"value": "Partly cloudy"}]}],
    "weather": [
        {"date": "2026-10-30", "mintempC": "22", "maxtempC": "31",
         "hourly": [{"chanceofrain": "10"}, {"chanceofrain": "40"}, {"chanceofrain": "0"}]},
        {"date": "2026-10-31", "mintempC": "21", "maxtempC": "30", "hourly": []},
        {"date": "2026-11-01", "mintempC": "23", "maxtempC": "32", "hourly": []},
    ],
}
RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Selic fica em 10% - Valor</title><link>https://x/1</link></item>
<item><title>Chuva na Paraiba - G1</title><link>https://x/2</link></item>
<item><title></title><link>https://x/3</link></item>
<item><title>Terceira manchete - Folha</title><link>https://x/4</link></item>
</channel></rss>"""


def _automacao(nome: str):
    spec = importlib.util.spec_from_file_location(f"teste_{nome}", RAIZ / "automacoes" / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class ImportarSemTelaTests(unittest.TestCase):
    def test_core_fontes_do_dia_nao_carrega_o_pyqt(self):
        codigo = ("import sys; sys.path.insert(0, %r); import core.fontes_do_dia; "
                  "print(any(m.startswith('PyQt6') for m in sys.modules))" % str(RAIZ))
        saida = subprocess.run([sys.executable, "-I", "-c", codigo], capture_output=True, text=True, timeout=60)
        self.assertEqual(saida.returncode, 0, saida.stderr)
        self.assertEqual(saida.stdout.strip(), "False")

    def test_ui_stark_e_ui_orbe_reexportam_e_usam_o_core(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import ui_orbe
        import ui_stark

        self.assertIs(ui_stark.buscar_clima, fontes_do_dia.buscar_clima)
        self.assertIs(ui_stark.buscar_noticias, fontes_do_dia.buscar_noticias)
        fonte = Path(ui_orbe.__file__).read_text(encoding="utf-8")
        self.assertIn("from core.fontes_do_dia import buscar_clima", fonte)
        self.assertNotIn("from ui_stark import buscar", fonte)


class ClimaTests(unittest.TestCase):
    def test_linhas_do_painel_iguais_as_de_antes(self):
        with patch.object(fontes_do_dia, "_dados_do_clima", return_value=CLIMA):
            linhas = fontes_do_dia.buscar_clima("Campina Grande").splitlines()
        self.assertEqual(linhas[0], "27°C  Parcialmente nublado")
        self.assertEqual(linhas[1], "Sensação 29°C · Umidade 70%")
        self.assertEqual(linhas[2], "Sex  22° / 31°")

    def test_frase_falada_em_portugues_com_a_cidade_do_env(self):
        with patch.dict(os.environ, {"JARVIS_CIDADE": "João Pessoa"}), \
                patch.object(fontes_do_dia, "_dados_do_clima", return_value=CLIMA) as dados:
            frase = fontes_do_dia.clima_falado()
        dados.assert_called_once_with("João Pessoa")
        self.assertEqual(frase, "Em João Pessoa agora faz 27 graus, parcialmente nublado, sensação de 29 e "
                                "umidade de 70%. Hoje, mínima de 22 e máxima de 31, com 40% de chance de chuva.")

    def test_pede_ao_wttr_in_em_portugues_sem_localizar_pelo_ip(self):
        chamadas = []

        class Resposta:
            def raise_for_status(self):
                pass

            def json(self):
                return CLIMA

        def get(url, **kw):
            chamadas.append((url, kw))
            return Resposta()

        with patch("requests.get", side_effect=get):
            fontes_do_dia.clima_falado("São Paulo")
        url, kw = chamadas[0]
        self.assertTrue(url.startswith("https://wttr.in/S%C3%A3o%20Paulo?"), url)
        self.assertIn("lang=pt", url)
        self.assertEqual(kw.get("timeout"), fontes_do_dia.TEMPO_LIMITE)
        fonte = (RAIZ / "core" / "fontes_do_dia.py").read_text(encoding="utf-8")
        for proibido in ("geocoder", "ipinfo", "ip-api", "latitude", "longitude"):
            self.assertNotIn(proibido, fonte.lower().replace("nunca localiza pelo ip e nunca\n  diz latitude e longitude", ""))

    def test_acao_weather_report_fala_o_clima_e_so_abre_o_navegador_se_pedirem(self):
        from actions import weather_report

        registro = SimpleNamespace(write_log=lambda t: registro.linhas.append(t), linhas=[])
        with patch.dict(os.environ, {"JARVIS_CIDADE": "Campina Grande"}), \
                patch.object(fontes_do_dia, "_dados_do_clima", return_value=CLIMA), \
                patch.object(weather_report.webbrowser, "open", return_value=True) as abrir:
            texto = weather_report.weather_action({}, player=registro)
            self.assertTrue(texto.startswith("Em Campina Grande agora faz 27 graus"))
            abrir.assert_not_called()  # só abre o navegador se o usuário pedir
            weather_report.weather_action({"city": "Recife", "open_browser": True}, player=registro)
            abrir.assert_called_once()
            self.assertIn("wttr.in/Recife", abrir.call_args.args[0])
        self.assertTrue(registro.linhas[0].startswith("JARVIS: Em Campina Grande"))

    def test_declaracao_do_clima_nao_exige_cidade(self):
        import main

        declaracao = next(d for d in main.get_tool_declarations() if d["name"] == "weather_report")
        self.assertNotIn("required", declaracao["parameters"])
        self.assertIn("open_browser", declaracao["parameters"]["properties"])
        self.assertIn("weather_report", main.JarvisLive.RESERVA_FERRAMENTAS_ESSENCIAIS)
        self.assertNotIn("weather_report", main.FERRAMENTAS_NUVEM_IA)


class NoticiasTests(unittest.TestCase):
    def setUp(self):
        self.noticias = _automacao("noticias")
        self.jarvis = SimpleNamespace(_fala_n=3, _fala_texto="quais as notícias?")

    def _rss(self):
        class Resposta:
            content = RSS

            def raise_for_status(self):
                pass

        return patch("requests.get", return_value=Resposta())

    def test_busca_do_rss_tira_o_nome_do_jornal_e_pula_titulo_vazio(self):
        with self._rss():
            itens = fontes_do_dia.buscar_noticias(5)
        self.assertEqual(itens, [("Selic fica em 10%", "https://x/1"), ("Chuva na Paraiba", "https://x/2"),
                                 ("Terceira manchete", "https://x/4")])

    def test_lista_as_manchetes_em_portugues_e_nao_abre_nada(self):
        with self._rss(), patch.object(self.noticias.webbrowser, "open") as abrir:
            texto = self.noticias.executar({"action": "list"}, self.jarvis)
        self.assertIn("1. Selic fica em 10%", texto)
        self.assertIn("2. Chuva na Paraiba", texto)
        abrir.assert_not_called()

    def test_so_abre_depois_de_um_sim_numa_fala_nova(self):
        with self._rss():
            self.noticias.executar({"action": "list"}, self.jarvis)
        with patch.object(self.noticias.webbrowser, "open", return_value=True) as abrir:
            # a mesma fala do pedido (ou "não") não abre
            resposta = self.noticias.executar({"action": "open", "number": 2}, self.jarvis)
            self.assertIn("Não abri", resposta)
            self.jarvis._fala_n, self.jarvis._fala_texto = 4, "não"
            self.assertIn("Não abri", self.noticias.executar({"action": "open", "number": 2}, self.jarvis))
            abrir.assert_not_called()
            # "sim, abre a segunda" NÃO vale ("segunda" parece dia da semana: a trava do ok recusa, de propósito)
            self.jarvis._fala_n, self.jarvis._fala_texto = 5, "sim, abre a segunda"
            self.assertIn("Não abri", self.noticias.executar({"action": "open", "number": 2}, self.jarvis))
            # um "sim" claro numa fala nova abre a escolhida
            self.jarvis._fala_n, self.jarvis._fala_texto = 6, "sim, pode"
            resposta = self.noticias.executar({"action": "open", "number": 2}, self.jarvis)
        abrir.assert_called_once_with("https://x/2")
        self.assertIn("Chuva na Paraiba", resposta)

    def test_abrir_sem_ter_listado_ou_numero_errado(self):
        self.noticias._ultimas.clear()
        self.assertIn("Primeiro peça as notícias", self.noticias.executar({"action": "open", "number": 1}, self.jarvis))
        with self._rss():
            self.noticias.executar({"action": "list"}, self.jarvis)
        self.jarvis._fala_n, self.jarvis._fala_texto = 9, "sim"
        with patch.object(self.noticias.webbrowser, "open") as abrir:
            self.assertIn("Escolha um número de 1 a 3", self.noticias.executar({"action": "open", "number": 7}, self.jarvis))
        abrir.assert_not_called()

    def test_sem_internet_responde_em_vez_de_quebrar(self):
        with patch("requests.get", side_effect=OSError("sem rede")):
            self.assertIn("Não consegui buscar as notícias", self.noticias.executar({"action": "list"}, self.jarvis))


class MapaTests(unittest.TestCase):
    def test_endereco_do_google_maps_codificado_direito(self):
        mapa = _automacao("mapa")
        self.assertEqual(mapa.endereco_do_mapa("praia de Tambaú,  João Pessoa"),
                         "https://www.google.com/maps/search/?api=1&query=praia%20de%20Tamba%C3%BA%2C%20Jo%C3%A3o%20Pessoa")
        with patch.object(mapa.webbrowser, "open", return_value=True) as abrir:
            self.assertIn("Abri o mapa de praia de Tambaú", mapa.executar({"place": "praia de Tambaú"}, None))
        self.assertIn("google.com/maps/search/?api=1&query=", abrir.call_args.args[0])
        self.assertNotIn("&amp;", abrir.call_args.args[0])
        self.assertIn("Faltou dizer o lugar", mapa.executar({}, None))


class ModoPrivadoTests(unittest.TestCase):
    def test_as_tres_novidades_nao_usam_ia_e_ficam_no_modo_privado(self):
        import main
        from core.automacoes import carregar_ferramentas

        carga = carregar_ferramentas()
        self.assertEqual(carga.erros, [])
        for nome in ("news_headlines", "show_map"):
            self.assertIn(nome, carga.ferramentas)
            self.assertFalse(carga.ferramentas[nome].usa_ia_nuvem, nome)
            self.assertNotIn(nome, main.FERRAMENTAS_NUVEM_IA)
        with patch.dict(os.environ, {"JARVIS_CEREBRO": "gemma"}):
            for nome in ("weather_report", "news_headlines", "show_map"):
                self.assertIsNone(main.bloqueio_do_modo_privado(nome, {}), nome)


class SaudacaoTests(unittest.TestCase):
    def test_bom_dia_boa_tarde_boa_noite(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import ui_orbe

        self.assertEqual(ui_orbe.saudacao(7), "Bom dia")
        self.assertEqual(ui_orbe.saudacao(11), "Bom dia")
        self.assertEqual(ui_orbe.saudacao(12), "Boa tarde")
        self.assertEqual(ui_orbe.saudacao(17), "Boa tarde")
        self.assertEqual(ui_orbe.saudacao(18), "Boa noite")
        self.assertEqual(ui_orbe.saudacao(3), "Boa noite")


if __name__ == "__main__":
    unittest.main()
