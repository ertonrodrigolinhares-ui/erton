import asyncio
import os
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

# Jarvis Ultron: o banco destes testes fica numa pasta temporária, nunca no tmp/jarvis_web.db de verdade.
# Tem de vir antes de importar o api: ele lê o DATABASE_URL uma vez só, ao ser importado.
_PASTA_BANCO = tempfile.TemporaryDirectory(prefix="jarvis-web-testes-", ignore_cleanup_errors=True)
_BANCO = Path(_PASTA_BANCO.name) / "jarvis_web.db"
_URL_ANTES = os.environ.get("DATABASE_URL")
os.environ["DATABASE_URL"] = "sqlite:///" + _BANCO.as_posix()

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from api import database
from api.database import SessionLocal, init_db
from api.models import (
    AnswerCacheEntry,
    ChatMessage,
    MemoryEntry,
    TaskRecord,
    User,
    UserConfig,
    UserSecret,
)
from api.security import create_access_token, decode_access_token, hash_password, verify_password
from api.server import app
from api.websocket_client import WebSocketClient
from core.tenant import tenant_scope
from memory.memory_manager import load_memory, update_memory


def tearDownModule():
    database.engine.dispose()  # solta o arquivo do banco (no Windows, senão a pasta não apaga)
    _PASTA_BANCO.cleanup()
    if _URL_ANTES is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = _URL_ANTES


class HostedApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # se outro teste importou o api antes, o banco seria o de verdade: para aqui, sem gravar nada
        if database.DATABASE_URL != "sqlite:///" + _BANCO.as_posix():
            raise RuntimeError(f"Os testes do servidor não estão no banco temporário: {database.DATABASE_URL}")
        init_db()
        cls.client = TestClient(app)
        cls.context = cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        self.email = f"operator-{uuid.uuid4().hex}@example.com"
        response = self.client.post("/auth/signup", json={
            "email": self.email,
            "password": "correct-horse-battery-staple",
            "display_name": "Morgan",
        })
        self.assertEqual(response.status_code, 201, response.text)
        session = response.json()
        self.user_id = session["user"]["id"]
        self.access_token = session["access_token"]
        self.headers = {"Authorization": f"Bearer {session['access_token']}"}

    def tearDown(self):
        with SessionLocal.begin() as db:
            for model in (
                AnswerCacheEntry, TaskRecord, ChatMessage, UserConfig,
                MemoryEntry, UserSecret,
            ):
                db.execute(delete(model).where(model.user_id == self.user_id))
            db.execute(delete(User).where(User.id == self.user_id))

    def test_password_hash_and_jwt_round_trip(self):
        encoded = hash_password("correct-horse-battery-staple")
        self.assertNotIn("correct-horse", encoded)
        self.assertTrue(verify_password("correct-horse-battery-staple", encoded))
        self.assertFalse(verify_password("incorrect-password", encoded))
        token = create_access_token(self.user_id)
        self.assertEqual(decode_access_token(token)["sub"], self.user_id)

    def test_gemini_key_is_encrypted_and_user_status_updates(self):
        raw_key = "AIza" + "A" * 35
        response = self.client.post(
            "/me/gemini-key",
            headers=self.headers,
            json={"api_key": raw_key, "validate": False},
        )
        self.assertEqual(response.status_code, 200, response.text)
        with SessionLocal() as db:
            row = db.scalar(select(UserSecret).where(UserSecret.user_id == self.user_id))
            self.assertIsNotNone(row)
            self.assertNotIn(raw_key, row.encrypted_value)
        me = self.client.get("/auth/me", headers=self.headers)
        self.assertTrue(me.json()["gemini_configured"])

        from actions.presentation_maker import _api_key

        with tenant_scope(self.user_id):
            self.assertEqual(_api_key(), raw_key)

    def test_vertex_only_key_does_not_switch_every_tenant_to_vertex(self):
        import os

        from core.api_key_validator import ApiKeyValidationResult

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
            os.environ.pop("JARVIS_GEMINI_VIA", None)
            with patch(
                "api.server.validate_gemini_api_key",
                return_value=ApiKeyValidationResult(True, "Gemini API key verified (Vertex AI).", via="vertex"),
            ):
                response = self.client.post(
                    "/me/gemini-key",
                    headers=self.headers,
                    json={"api_key": "AQ." + "C" * 40, "validate": True},
                )
            self.assertEqual(response.status_code, 422, response.text)
            self.assertIn("Vertex", response.json()["detail"])
            self.assertNotIn("GOOGLE_GENAI_USE_VERTEXAI", os.environ)
        me = self.client.get("/auth/me", headers=self.headers)
        self.assertFalse(me.json()["gemini_configured"])

    def test_memory_is_scoped_by_tenant(self):
        with tenant_scope(self.user_id):
            update_memory({"identity": {"name": {"value": "Morgan"}}})
            self.assertEqual(load_memory()["identity"]["name"]["value"], "Morgan")

        other_id = str(uuid.uuid4())
        with SessionLocal.begin() as db:
            db.add(User(
                id=other_id,
                email=f"other-{uuid.uuid4().hex}@example.com",
                display_name="Other",
                password_hash=hash_password("another-secure-password"),
            ))
        try:
            with tenant_scope(other_id):
                self.assertNotIn("name", load_memory()["identity"])
        finally:
            with SessionLocal.begin() as db:
                db.execute(delete(User).where(User.id == other_id))

    def test_status_and_cloud_actions_are_authenticated(self):
        self.assertEqual(self.client.get("/status").status_code, 401)
        status_response = self.client.get("/status", headers=self.headers)
        self.assertEqual(status_response.json()["state"], "OFFLINE")
        actions = self.client.get("/actions", headers=self.headers).json()["actions"]
        names = {action["name"] for action in actions}
        self.assertIn("web_search", names)
        self.assertNotIn("open_app", names)

    def test_cloud_action_worker_keeps_tenant_context(self):
        import main
        from core.tenant import get_current_user_id

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis.cloud_safe = True
        jarvis.ui = SimpleNamespace(
            set_state=lambda _state: None,
            muted=False,
        )
        call = SimpleNamespace(id="tenant-call", name="web_search", args={"query": "test"})

        with patch.object(main, "web_search_action", side_effect=lambda **_kwargs: get_current_user_id()):
            with tenant_scope(self.user_id):
                response = asyncio.run(jarvis._execute_tool(call))

        self.assertEqual(response.response["result"], self.user_id)

    def test_authenticated_websocket_streams_engine_events(self):
        raw_key = "AIza" + "B" * 35
        response = self.client.post(
            "/me/gemini-key",
            headers=self.headers,
            json={"api_key": raw_key, "validate": False},
        )
        self.assertEqual(response.status_code, 200, response.text)

        class FakeLiveEngine:
            def __init__(self, client, **_kwargs):
                self.client = client
                self.stopped = threading.Event()

            async def run(self):
                self.client.set_state("LISTENING")
                while not self.stopped.is_set():
                    await asyncio.sleep(0.01)

            async def send_text(self, text):
                self.client.write_log(f"Jarvis: Echo: {text}")
                return True

            async def send_audio_chunk(self, _data, _mime_type="audio/pcm;rate=16000"):
                return True

            def request_shutdown(self):
                self.stopped.set()

            def _get_current_voice(self):
                return "puck"

        import main

        with patch.object(main, "JarvisLive", FakeLiveEngine):
            with self.client.websocket_connect(f"/ws?token={self.access_token}") as socket:
                received = [socket.receive_json(), socket.receive_json()]
                self.assertEqual({event["type"] for event in received}, {"ready", "status"})
                socket.send_json({"type": "text", "content": "status report"})
                message = socket.receive_json()
                self.assertEqual(message["type"], "message")
                self.assertEqual(message["content"], "Echo: status report")
                socket.send_json({"type": "close"})
                self.assertEqual(socket.receive()["type"], "websocket.close")


class FakeWebSocket:
    def __init__(self):
        self.events = []

    async def send_json(self, event):
        self.events.append(event)


class WebSocketAdapterTests(unittest.TestCase):
    def test_adapter_serializes_status_text_and_audio(self):
        async def run():
            socket = FakeWebSocket()
            client = WebSocketClient(socket)
            sender = asyncio.create_task(client.send_events())
            client.set_state("LISTENING")
            client.write_log("Jarvis: Online.")
            client.send_audio(b"\x01\x02")
            await asyncio.sleep(0)
            await client.close()
            await sender
            return socket.events

        events = asyncio.run(run())
        self.assertEqual([event["type"] for event in events], ["status", "message", "audio"])
        self.assertEqual(events[-1]["data"], "AQI=")


if __name__ == "__main__":
    unittest.main()
