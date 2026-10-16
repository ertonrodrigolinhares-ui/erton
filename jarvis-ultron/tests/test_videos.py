import importlib.util
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from core import aprovacao
from core.aprovacao import fechar_fala, mais_um_pedaco, nova_fala


def _modulo():
    spec = importlib.util.spec_from_file_location("auto_videos", RAIZ / "automacoes" / "videos.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class JarvisFalso:
    """Imita o JarvisLive: conta as falas do Erton (o "ok" só vale numa fala nova)."""

    def __init__(self, fala=""):
        self._fala_n, self._fala_texto = 0, ""
        self.avisos, self.logs = [], []
        self.ui = NS(write_log=self.logs.append)
        if fala:
            self.falar(fala)

    def falar(self, texto):
        nova_fala(self, texto)

    def _falar_aviso(self, texto):
        self.avisos.append(texto)


def _esperar_video():
    for t in threading.enumerate():
        if t.name == "VideoVeo":
            t.join(5)


class OkAntesDoVideoTests(unittest.TestCase):
    def setUp(self):
        self.m = _modulo()
        self.pedido = {"description": "a triathlete crossing the finish line in Hawaii at sunset", "seconds": 8}

    def test_primeiro_mostra_o_preco_e_nao_faz_nada(self):
        with patch.object(self.m, "gerar") as gerar:
            r = self.m.executar(dict(self.pedido), JarvisFalso())
        self.assertIn("US$ 0.96", r)  # 8 s x US$ 0,12 (rápido)
        self.assertIn("R$", r)
        gerar.assert_not_called()

    def test_confirmar_sem_ok_do_usuario_nao_faz(self):
        jarvis = JarvisFalso("faz um vídeo de um triatleta no Havaí")
        with patch.object(self.m, "gerar") as gerar:
            self.m.executar(dict(self.pedido), jarvis)
            jarvis.falar("hmm, quanto fica mesmo?")
            r = self.m.executar(dict(self.pedido, confirm=True), jarvis)
            _esperar_video()
        self.assertIn("Not confirmed", r)
        gerar.assert_not_called()

    def test_recusa_que_comeca_com_ok_nao_vale(self):
        jarvis = JarvisFalso("faz um vídeo de um triatleta no Havaí")
        with patch.object(self.m, "gerar") as gerar:
            self.m.executar(dict(self.pedido), jarvis)
            for recusa in ("Ok, pode cancelar, tá caro", "ok, deixa pra depois", "sim, mas muito caro",
                           "ok, quanto fica em euro?", "ok, entendi", "ok, pode fazer amanhã",
                           "ok, pode fazer daqui a pouco", "ok pode fazer peraí", "sim, pode fazer na semana que vem"):
                jarvis.falar(recusa)
                r = self.m.executar(dict(self.pedido, confirm=True), jarvis)
                self.assertIn("Not confirmed", r, recusa)
            _esperar_video()
        gerar.assert_not_called()

    def test_resto_da_fala_que_vira_recusa_nao_faz_e_o_preco_continua_valendo(self):
        # Gemini ao vivo: a ferramenta chegou com só o "Ok," transcrito; o resto chega depois
        jarvis = JarvisFalso("faz um vídeo de um triatleta no Havaí")
        with patch.object(aprovacao, "SILENCIO", 0.2), \
                patch.object(self.m, "gerar", return_value=Path("/tmp/video.mp4")) as gerar, \
                patch.object(self.m, "_abrir"):
            self.m.executar(dict(self.pedido), jarvis)
            numero = nova_fala(jarvis, "Ok,", em_pedacos=True)
            r = self.m.executar(dict(self.pedido, confirm=True), jarvis)
            self.assertIn("background", r)
            mais_um_pedaco(jarvis, numero, "Ok, pode cancelar, tá caro")
            fechar_fala(jarvis, numero)
            _esperar_video()
            gerar.assert_not_called()
            self.assertIn("Não fiz o vídeo", jarvis.avisos[-1])
            # um "ok" claro numa fala nova ainda vale para o mesmo preço
            jarvis.falar("ok, pode fazer")
            self.assertIn("background", self.m.executar(dict(self.pedido, confirm=True), jarvis))
            _esperar_video()
        gerar.assert_called_once()

    def test_ok_dito_antes_do_preco_nao_vale(self):
        jarvis = JarvisFalso("ok, pode fazer")
        with patch.object(self.m, "gerar") as gerar:
            self.m.executar(dict(self.pedido), jarvis)  # o preço vem depois do "ok"
            r = self.m.executar(dict(self.pedido, confirm=True), jarvis)
            _esperar_video()
        self.assertIn("Not confirmed", r)
        gerar.assert_not_called()

    def test_confirmar_sem_ter_mostrado_o_preco_nao_faz(self):
        with patch.object(self.m, "gerar") as gerar:
            r = self.m.executar(dict(self.pedido, confirm=True), JarvisFalso("ok, pode fazer"))
            _esperar_video()
        self.assertIn("Not confirmed", r)
        gerar.assert_not_called()

    def test_ok_para_outro_video_nao_vale(self):
        jarvis = JarvisFalso("faz um vídeo de um triatleta no Havaí")
        with patch.object(self.m, "gerar") as gerar:
            self.m.executar(dict(self.pedido), jarvis)
            jarvis.falar("ok, pode fazer")
            r = self.m.executar(dict(self.pedido, seconds=4, confirm=True), jarvis)
            _esperar_video()
        self.assertIn("Not confirmed", r)
        gerar.assert_not_called()

    def test_com_ok_faz_em_segundo_plano_abre_e_avisa(self):
        jarvis = JarvisFalso("faz um vídeo de um triatleta no Havaí")
        with patch.object(self.m, "gerar", return_value=Path("/tmp/video.mp4")) as gerar, \
                patch.object(self.m, "_abrir") as abrir:
            self.m.executar(dict(self.pedido), jarvis)
            jarvis.falar("ok, pode fazer")
            r = self.m.executar(dict(self.pedido, confirm=True), jarvis)
            _esperar_video()
        self.assertIn("background", r)
        gerar.assert_called_once()
        abrir.assert_called_once_with(Path("/tmp/video.mp4"))
        self.assertIn("pronto", jarvis.avisos[0])
        # o mesmo ok não serve para um segundo vídeo
        with patch.object(self.m, "gerar") as gerar2:
            r2 = self.m.executar(dict(self.pedido, confirm=True), jarvis)
        self.assertIn("Not confirmed", r2)
        gerar2.assert_not_called()

    def test_pode_fazer_dito_junto_com_o_pedido_nao_vale(self):
        """O ok tem que vir numa fala nova, depois de o Erton ouvir o preço."""
        jarvis = JarvisFalso("faz um vídeo de um triatleta no Havaí, pode fazer")
        with patch.object(self.m, "gerar") as gerar:
            self.m.executar(dict(self.pedido), jarvis)
            r = self.m.executar(dict(self.pedido, confirm=True), jarvis)
            _esperar_video()
        self.assertIn("Not confirmed", r)
        gerar.assert_not_called()

    def test_dolar_com_virgula_no_env_funciona(self):
        with patch.dict("os.environ", {"JARVIS_DOLAR": "5,40"}):
            dolares, reais = self.m.estimar(8, "rapido")
            r = self.m.executar(dict(self.pedido), JarvisFalso())
        self.assertAlmostEqual(reais, dolares * 5.40)
        self.assertIn("US$ 0.96", r)
        for ruim in ("abc", "0", "-3", "nan"):
            with patch.dict("os.environ", {"JARVIS_DOLAR": ruim}):
                dolares, reais = self.m.estimar(8, "rapido")
            self.assertAlmostEqual(reais, dolares * 5.4, msg=ruim)

    def test_modo_privado_nunca_manda_a_descricao_para_o_google(self):
        import os

        pedido = dict(self.pedido, description="client Fulano from company X receiving a certificate")
        with patch.dict(os.environ, {"JARVIS_CEREBRO": "gemma"}), patch.object(self.m, "gerar") as gerar:
            r1 = self.m.executar(dict(pedido), JarvisFalso())
            r2 = self.m.executar(dict(pedido, confirm=True), JarvisFalso("ok, pode fazer"))
            _esperar_video()
        self.assertIn("modo privado", r1)
        self.assertNotIn("US$", r1)
        self.assertIn("modo privado", r2)
        gerar.assert_not_called()

    def test_modo_privado_ligado_entre_o_preco_e_o_ok(self):
        jarvis = JarvisFalso("ok, pode fazer")
        with patch.object(self.m, "gerar") as gerar:
            self.m.executar(dict(self.pedido), JarvisFalso())
            with patch.object(self.m, "_modo_privado", side_effect=[False, True]):
                self.m.executar(dict(self.pedido, confirm=True), jarvis)
                _esperar_video()
        gerar.assert_not_called()
        self.assertIn("modo privado", jarvis.avisos[0])

    def test_marcada_como_ia_na_nuvem(self):
        from core.automacoes import carregar_ferramentas

        self.assertTrue(carregar_ferramentas(RAIZ / "automacoes").ferramentas["generate_video"].usa_ia_nuvem)

    def test_erro_do_google_vira_aviso_em_portugues(self):
        jarvis = JarvisFalso("faz um vídeo de um triatleta no Havaí")
        with patch.object(self.m, "gerar", side_effect=RuntimeError("403 billing account not enabled")):
            self.m.executar(dict(self.pedido), jarvis)
            jarvis.falar("ok, pode fazer")
            self.m.executar(dict(self.pedido, confirm=True), jarvis)
            _esperar_video()
        self.assertIn("faturamento", jarvis.avisos[0])


def _pedaco(texto):
    """Um pedaço da transcrição da fala do Erton (Gemini ao vivo)."""
    return NS(server_content=NS(input_transcription=NS(text=texto), output_transcription=None, turn_complete=False),
              tool_call=None)


def _video(confirm):
    fc = NS(name="generate_video", id="v", args={"description": "my workout", "seconds": 8, "confirm": confirm})
    return NS(server_content=None, tool_call=NS(function_calls=[fc]))


def _fim_do_turno():
    return NS(server_content=NS(input_transcription=None, output_transcription=None, turn_complete=True),
              tool_call=None)


def _microfone(jarvis):
    """O microfone mandou áudio ao Gemini com o Jarvis calado (o Erton falando depois do preço)."""
    jarvis._microfone_mandou_audio()


def _jarvis_falando(valor):
    """O Jarvis começou (True) ou terminou (False) de falar; enquanto fala, o microfone fica fechado."""
    return lambda jarvis: jarvis.set_speaking(valor)


class OkNoGeminiAoVivoTests(unittest.TestCase):
    """No Gemini ao vivo a transcrição chega em pedaços e atrasada: o "pode fazer" dito junto com o
    pedido não pode aprovar o vídeo na segunda chamada do mesmo turno."""

    def setUp(self):
        from core import aprovacao

        self.m = _modulo()
        self.respostas, self.avisos = [], []
        silencio = patch.object(aprovacao, "SILENCIO", 0.4)  # o padrão (2 s) só deixaria o teste lento
        silencio.start()
        self.addCleanup(silencio.stop)

    def _rodar(self, mensagens):
        """mensagens: o que o Gemini manda, na ordem; um número é uma pausa (segundos) na conexão e
        uma função é algo que acontece no PC nessa hora (_microfone, _jarvis_falando)."""
        import asyncio

        import main

        jarvis = object.__new__(main.JarvisLive)
        jarvis.ui = NS(muted=False, write_log=lambda t: None, clear_subtitle=lambda: None,
                       show_subtitle=lambda t: None, set_state=lambda estado: None)
        self.jarvis = jarvis
        jarvis._portao = NS(estender=lambda: None, estado="ouvindo")
        jarvis._turn_done_event = None
        jarvis._shutdown_requested = threading.Event()
        jarvis._fala_n, jarvis._fala_texto = 0, ""
        for nome in ("_checar_pedido_de_modo", "_pedido_de_cerebro", "_falar_com_voz_externa"):
            setattr(jarvis, nome, lambda t: None)
        jarvis._is_explicit_self_quit_transcript = lambda t: False
        jarvis.anunciar = lambda texto, *a, **k: self.avisos.append(texto) or "falado"
        m, respostas = self.m, self.respostas

        async def ferramentas(chamadas):
            respostas.extend(m.executar(dict(fc.args), jarvis) for fc in chamadas)
            return []

        jarvis._execute_tool_batch = ferramentas

        class Sessao:
            async def receive(self):
                for mensagem in mensagens:
                    if isinstance(mensagem, (int, float)):
                        await asyncio.sleep(mensagem)
                        continue
                    if callable(mensagem):
                        mensagem(jarvis)
                        continue
                    yield mensagem
                jarvis._shutdown_requested.set()

            async def send_tool_response(self, function_responses):
                pass

        jarvis.session = Sessao()
        with patch.object(self.m, "gerar", return_value=Path("/tmp/video.mp4")) as gerar, \
                patch.object(self.m, "_abrir"):
            asyncio.run(jarvis._receive_audio())
            _esperar_video()
        return gerar

    def test_pode_fazer_que_chega_depois_do_preco_no_mesmo_turno_nao_vale(self):
        gerar = self._rodar([_pedaco("Jarvis, faz um vídeo de 8 segundos do meu treino"), _video(False),
                             _pedaco(", pode fazer"), _video(True), _fim_do_turno()])
        gerar.assert_not_called()
        self.assertIn("Not confirmed", self.respostas[1])

    def test_pedido_inteiro_transcrito_atrasado_nao_vale(self):
        # o preço saiu antes de chegar qualquer pedaço da fala; o pedido (que soa como um "ok")
        # chega depois, no mesmo turno do modelo: não é uma fala nova depois do preço
        gerar = self._rodar([_video(False), _pedaco("Ok Jarvis, pode fazer um vídeo do meu treino"),
                             _video(True), _fim_do_turno()])
        gerar.assert_not_called()
        self.assertIn("Not confirmed", self.respostas[1])

    def test_ok_que_vira_recusa_quando_o_resto_da_fala_chega_nao_faz(self):
        # "Ok, pode cancelar, tá caro": a ferramenta chega quando só o "Ok," foi transcrito; o resto
        # chega depois. O vídeo pago não pode começar com o pedaço "Ok,".
        gerar = self._rodar([_pedaco("Jarvis, faz um vídeo de 8 segundos do meu treino"), _video(False),
                             _fim_do_turno(), _microfone, _pedaco("Ok,"), _video(True), 0.2,
                             _pedaco("pode cancelar, tá caro"), _fim_do_turno()])
        gerar.assert_not_called()
        self.assertTrue(any("Não fiz o vídeo" in a for a in self.avisos), self.avisos)

    def test_resto_da_fala_que_chega_depois_do_fim_do_turno_tambem_conta(self):
        # o resto da fala chega só depois do fim do turno do modelo (vira uma fala nova): não faz
        gerar = self._rodar([_pedaco("Jarvis, faz um vídeo de 8 segundos do meu treino"), _video(False),
                             _fim_do_turno(), _microfone, _pedaco("Ok,"), _video(True), _fim_do_turno(), 0.2,
                             _pedaco("pode cancelar, tá caro"), _fim_do_turno()])
        gerar.assert_not_called()
        # o resto chegou sem áudio novo do microfone: é a mesma fala, que cresceu (e deixou de ser um "ok")
        self.assertEqual(self.jarvis._fala_n, 2)
        self.assertIn("pode cancelar", self.jarvis._fala_texto)

    def test_ok_numa_fala_nova_depois_do_preco_vale(self):
        gerar = self._rodar([_pedaco("Jarvis, faz um vídeo de 8 segundos do meu treino"), _video(False),
                             _jarvis_falando(True), _fim_do_turno(), _jarvis_falando(False), _microfone,
                             _pedaco("ok, pode fazer"), _video(True), _fim_do_turno()])
        gerar.assert_called_once()
        self.assertIn("background", self.respostas[1])

    def test_resto_do_pedido_que_chega_depois_do_turno_do_preco_nao_vale(self):
        # o ", pode fazer" do pedido chega atrasado, já depois do fim do turno do preço (o Jarvis ainda
        # falando o preço, o microfone fechado); o turno seguinte é aberto por um aviso, sem fala dele
        gerar = self._rodar([_pedaco("Jarvis, faz um vídeo de 8 segundos do meu treino"), _video(False),
                             _jarvis_falando(True), _fim_do_turno(), _pedaco(", pode fazer"),
                             _jarvis_falando(False), _fim_do_turno(), _video(True), _fim_do_turno()])
        gerar.assert_not_called()
        self.assertIn("Not confirmed", self.respostas[1])
        self.assertEqual(self.jarvis._fala_n, 1)  # o resto fez a fala do pedido crescer
        self.assertTrue(self.jarvis._fala_texto.endswith(", pode fazer"), self.jarvis._fala_texto)

    def test_resto_do_pedido_mais_uma_pergunta_nao_vale(self):
        gerar = self._rodar([_pedaco("Jarvis, faz um vídeo de 8 segundos do meu treino"), _video(False),
                             _fim_do_turno(), _pedaco(", pode fazer"), _microfone,
                             _pedaco("e em dólar quanto dá?"), _video(True), _fim_do_turno()])
        gerar.assert_not_called()
        self.assertIn("Not confirmed", self.respostas[1])

    def test_ok_de_verdade_depois_do_resto_atrasado_vale(self):
        # depois do resto atrasado, o microfone volta a mandar áudio: o "ok" dele é uma fala nova
        gerar = self._rodar([_pedaco("Jarvis, faz um vídeo de 8 segundos do meu treino"), _video(False),
                             _fim_do_turno(), _pedaco(", pode fazer"), _microfone,
                             _pedaco("ok, pode fazer"), _video(True), _fim_do_turno()])
        gerar.assert_called_once()
        self.assertEqual(self.jarvis._fala_texto, "ok, pode fazer")


class Operacao:
    def __init__(self, voltas, video):
        self.voltas, self.video = voltas, video

    @property
    def done(self):
        return self.voltas <= 0

    @property
    def result(self):
        return NS(generated_videos=[NS(video=self.video)])

    error = None
    name = "models/veo/operations/teste-123"


class VideoFalso:
    uri = None
    video_bytes = b"mp4"

    def save(self, caminho):
        Path(caminho).write_bytes(self.video_bytes)


class ClienteVeo:
    def __init__(self, nomes, inexistentes=()):
        self.nomes, self.inexistentes, self.pedidos = nomes, set(inexistentes), []
        self.models = NS(list=lambda config=None: [NS(name=f"models/{n}") for n in self.nomes],
                         generate_videos=self._gerar)
        self.operations = NS(get=self._andar)

    def _gerar(self, model, source, config):
        self.pedidos.append((model, config))
        if model in self.inexistentes:
            raise Exception(f"404 NOT_FOUND {model}")
        return Operacao(2, VideoFalso())

    def _andar(self, operacao):
        operacao.voltas -= 1
        return operacao


class GerarTests(unittest.TestCase):
    def setUp(self):
        self.m = _modulo()
        self.casa = tempfile.mkdtemp()

    def test_escolhe_o_veo_rapido_mais_novo_e_salva(self):
        cliente = ClienteVeo(["veo-3.0-fast-generate-001", "veo-3.1-fast-generate-preview", "veo-3.1-generate-preview"])
        with patch.object(self.m, "pasta_videos", lambda: Path(self.casa)):
            arquivo = self.m.gerar("a runner", 8, "rapido", True, cliente=cliente, dormir=lambda s: None)
        self.assertTrue(arquivo.exists())
        modelo, config = cliente.pedidos[0]
        self.assertEqual(modelo, "veo-3.1-fast-generate-preview")
        self.assertEqual(config.aspect_ratio, "9:16")
        self.assertEqual(config.duration_seconds, 8)

    def test_modelo_que_nao_existe_tenta_o_proximo(self):
        cliente = ClienteVeo(["veo-3.1-generate-preview", "veo-3.1-generate-001"], inexistentes={"veo-3.1-generate-preview"})
        with patch.object(self.m, "pasta_videos", lambda: Path(self.casa)):
            arquivo = self.m.gerar("a runner", 4, "maximo", False, cliente=cliente, dormir=lambda s: None)
        self.assertTrue(arquivo.exists())
        self.assertEqual([p[0] for p in cliente.pedidos], ["veo-3.1-generate-preview", "veo-3.1-generate-001"])

    # --- o econômico nunca vira um modelo mais caro que o preço aprovado

    def test_economico_sem_veo_lite_nao_usa_o_modelo_rapido(self):
        cliente = ClienteVeo(["veo-3.1-fast-generate-preview", "veo-3.1-generate-preview"],
                             inexistentes={"veo-3.1-lite-generate-preview"})
        with patch.object(self.m, "pasta_videos", lambda: Path(self.casa)):
            with self.assertRaises(RuntimeError) as erro:
                self.m.gerar("a runner", 8, "economico", False, cliente=cliente, dormir=lambda s: None)
        modelos = [p[0] for p in cliente.pedidos]
        self.assertTrue(modelos)
        self.assertTrue(all("lite" in m for m in modelos), modelos)
        self.assertIn("rápida", self.m._explicar(erro.exception))  # sugere pedir de novo (novo preço, novo ok)

    def test_lista_de_modelos_fica_na_faixa_de_preco(self):
        sem_lista = NS(models=NS(list=lambda config=None: (_ for _ in ()).throw(RuntimeError("sem rede"))))
        conta = NS(models=NS(list=lambda config=None: [NS(name=f"models/{n}") for n in (
            "veo-3.1-fast-generate-preview", "veo-3.1-generate-preview", "veo-3.1-lite-generate-preview")]))
        for cliente in (sem_lista, conta):
            self.assertTrue(all("lite" in n for n in self.m.escolher_modelo(cliente, "economico")))
            self.assertTrue(all("fast" in n for n in self.m.escolher_modelo(cliente, "rapido")))
            self.assertFalse(any("fast" in n or "lite" in n for n in self.m.escolher_modelo(cliente, "maximo")))

    # --- 1080p só com 8 segundos

    def test_video_curto_pede_720p_e_o_de_8_segundos_1080p(self):
        for segundos, esperado in ((4, "720p"), (6, "720p"), (8, "1080p")):
            for qualidade in ("rapido", "maximo"):
                cliente = ClienteVeo(["veo-3.1-fast-generate-preview", "veo-3.1-generate-preview"])
                with patch.object(self.m, "pasta_videos", lambda: Path(self.casa)):
                    self.m.gerar("a runner", segundos, qualidade, False, cliente=cliente, dormir=lambda s: None)
                modelo, config = cliente.pedidos[0]
                self.assertEqual((config.duration_seconds, config.resolution), (segundos, esperado), modelo)

    def test_veo_3_0_vertical_pede_720p(self):
        self.assertEqual(self.m._resolucao("veo-3.0-fast-generate-001", 8, "rapido", True), "720p")
        self.assertEqual(self.m._resolucao("veo-3.0-fast-generate-001", 8, "rapido", False), "1080p")
        self.assertEqual(self.m._resolucao("veo-3.1-fast-generate-preview", 8, "rapido", True), "1080p")

    # --- uma falha de rede depois de o Google começar não perde o vídeo já pago

    def test_queda_de_rede_ao_acompanhar_nao_perde_o_video(self):
        cliente = ClienteVeo(["veo-3.1-fast-generate-preview"])
        andar, falhas = cliente._andar, [ConnectionError("wifi caiu")]

        def andar_com_queda(operacao):
            if falhas:
                raise falhas.pop()
            return andar(operacao)

        cliente.operations = NS(get=andar_com_queda)
        with patch.object(self.m, "pasta_videos", lambda: Path(self.casa)):
            arquivo = self.m.gerar("a runner", 8, "rapido", False, cliente=cliente, dormir=lambda s: None)
        self.assertTrue(arquivo.exists())
        self.assertEqual(len(cliente.pedidos), 1)  # não pediu (nem pagou) um segundo vídeo

    def test_falha_passageira_ao_baixar_tenta_de_novo(self):
        class VideoNaNuvem(VideoFalso):
            uri, video_bytes = "https://exemplo/video", None

        baixar = []

        def download(file):
            baixar.append(file)
            if len(baixar) == 1:
                raise OSError("conexão reiniciada")
            file.video_bytes = b"mp4"

        cliente = ClienteVeo(["veo-3.1-fast-generate-preview"])
        cliente._gerar = lambda model, source, config: Operacao(1, VideoNaNuvem())
        cliente.models.generate_videos = cliente._gerar
        cliente.files = NS(download=download)
        with patch.object(self.m, "pasta_videos", lambda: Path(self.casa)):
            arquivo = self.m.gerar("a runner", 8, "rapido", False, cliente=cliente, dormir=lambda s: None)
        self.assertTrue(arquivo.exists())
        self.assertEqual(len(baixar), 2)

    def test_pc_dormiu_na_espera_olha_mais_uma_vez_antes_de_desistir(self):
        relogio = iter([0, 10 ** 6, 10 ** 6])
        cliente = ClienteVeo(["veo-3.1-fast-generate-preview"])
        cliente.models.generate_videos = lambda model, source, config: Operacao(1, VideoFalso())
        with patch.object(self.m, "pasta_videos", lambda: Path(self.casa)):
            arquivo = self.m.gerar("a runner", 8, "rapido", False, cliente=cliente,
                                   dormir=lambda s: None, agora=lambda: next(relogio))
        self.assertTrue(arquivo.exists())

    def _pc_dorme_e_a_rede_demora(self, volta_em):
        """Relógio falso: o PC dorme 30 min na 1ª pausa; a rede só volta `volta_em` s depois de acordar."""
        relogio, consultas = [0.0], []
        cliente = ClienteVeo(["veo-3.1-fast-generate-preview"])
        andar = cliente._andar

        def gerar(model, source, config):
            cliente.pedidos.append((model, config))
            return Operacao(1, VideoFalso())  # fica pronto na próxima consulta que der certo

        def dormir(segundos):
            relogio[0] += segundos + (30 * 60 if relogio[0] == 0 else 0)

        def consultar(operacao):
            consultas.append(relogio[0])
            if relogio[0] < 30 * 60 + 10 + volta_em:
                raise ConnectionError("Wi-Fi ainda voltando")
            return andar(operacao)

        cliente.models.generate_videos, cliente.operations = gerar, NS(get=consultar)
        with patch.object(self.m, "pasta_videos", lambda: Path(self.casa)):
            try:
                return self.m.gerar("a runner", 8, "rapido", False, cliente=cliente,
                                    dormir=dormir, agora=lambda: relogio[0]), consultas, cliente
            except self.m.VideoJaPedido as erro:
                return erro, consultas, cliente

    def test_pc_acordou_e_o_wifi_demora_uns_segundos_ainda_salva_o_video(self):
        arquivo, consultas, cliente = self._pc_dorme_e_a_rede_demora(volta_em=8)
        self.assertIsInstance(arquivo, Path, consultas)
        self.assertTrue(arquivo.exists())
        self.assertEqual(len(cliente.pedidos), 1)  # não pediu (nem pagou) um segundo vídeo
        self.assertGreater(consultas[-1], consultas[0])  # esperou a rede voltar antes de olhar de novo

    def test_pc_acordou_sem_rede_desiste_depois_de_poucas_tentativas_e_avisa(self):
        erro, consultas, cliente = self._pc_dorme_e_a_rede_demora(volta_em=10 ** 6)
        self.assertIsInstance(erro, self.m.VideoJaPedido)
        self.assertIn("pode cobrar", self.m._explicar(erro))
        self.assertLessEqual(len(consultas), 6)  # não fica preso tentando para sempre
        self.assertEqual(len(cliente.pedidos), 1)

    def test_sem_resposta_avisa_que_pode_ter_cobrado_e_anota_o_pedido(self):
        relogio = iter([0, 10 ** 6, 10 ** 6])
        cliente = ClienteVeo(["veo-3.1-fast-generate-preview"])
        cliente.models.generate_videos = lambda model, source, config: Operacao(5, VideoFalso())
        with patch.object(self.m, "pasta_videos", lambda: Path(self.casa)):
            with self.assertRaises(self.m.VideoJaPedido) as erro:
                self.m.gerar("a runner", 8, "rapido", False, cliente=cliente,
                             dormir=lambda s: None, agora=lambda: next(relogio))
        aviso = self.m._explicar(erro.exception)
        self.assertIn("15 minutos", aviso)
        self.assertIn("pode cobrar", aviso)
        self.assertIn("pendentes.txt", aviso)
        anotado = (Path(self.casa) / "pendentes.txt").read_text(encoding="utf-8")
        self.assertIn("operations/teste-123", anotado)

    def test_falha_de_rede_que_nao_passa_tambem_avisa_da_cobranca(self):
        cliente = ClienteVeo(["veo-3.1-fast-generate-preview"])
        cliente.files = NS(download=lambda file: (_ for _ in ()).throw(ConnectionError("sem internet")))
        cliente.models.generate_videos = lambda model, source, config: Operacao(
            1, type("VideoNaNuvem", (VideoFalso,), {"uri": "https://exemplo/video", "video_bytes": None})())
        with patch.object(self.m, "pasta_videos", lambda: Path(self.casa)):
            with self.assertRaises(self.m.VideoJaPedido) as erro:
                self.m.gerar("a runner", 8, "rapido", False, cliente=cliente, dormir=lambda s: None)
        aviso = self.m._explicar(erro.exception)
        self.assertIn("conexão com o Google falhou", aviso)
        self.assertIn("antes de pedir outro", aviso)

    def test_carrega_como_ferramenta_do_jarvis(self):
        from core.automacoes import carregar_ferramentas

        carga = carregar_ferramentas(RAIZ / "automacoes")
        self.assertIn("generate_video", carga.ferramentas)
        self.assertNotIn("videos.py", carga.na_tela)


if __name__ == "__main__":
    unittest.main()
