from django.test import TestCase
from rest_framework.test import APIClient
from main.core.config import get_dev_settings, resolve_params, set_dev_settings
from main.core.agent import get_llm, _get_llm_with_thinking
from main.models import Setting


class DevSettingsTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_get_dev_settings_endpoint(self):
        response = self.client.get("/api/dev/settings/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("settings", data)
        self.assertEqual(data["settings"]["base_url"], "https://openrouter.ai/api/v1")
        self.assertEqual(data["settings"]["model"], "")
        self.assertEqual(data["settings"]["api_key"], "")

    def test_put_dev_settings_endpoint(self):
        payload = {
            "provider": "openai_compatible",
            "base_url": "https://openrouter.ai/api/v1",
            "model": "anthropic/claude-3.7-sonnet",
            "api_key": "sk-or-v1-testkey123",
            "temperature": 0.5,
            "chat_history_window": 15,
            "thinking_level": "high",
            "extra_params": '{"top_p": 0.95, "max_tokens": 2048}',
            "system_prompt": "Custom system prompt for Mina AI",
            "tts_base_url": "https://openrouter.ai/api/v1",
            "tts_api_key": "sk-or-v1-ttstestkey",
        }
        response = self.client.put("/api/dev/settings/", data=payload, format="json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["settings"]["model"], "anthropic/claude-3.7-sonnet")
        self.assertEqual(data["settings"]["api_key"], "sk-or-v1-testkey123")
        self.assertEqual(data["settings"]["tts_base_url"], "https://openrouter.ai/api/v1")
        self.assertEqual(data["settings"]["tts_api_key"], "sk-or-v1-ttstestkey")
        self.assertEqual(data["settings"]["thinking_level"], "high")
        self.assertEqual(data["settings"]["extra_params"], '{"top_p": 0.95, "max_tokens": 2048}')
        self.assertEqual(data["settings"]["system_prompt"], "Custom system prompt for Mina AI")

        # Verify resolve_params reads newly saved settings
        params = resolve_params()
        self.assertEqual(params["model"], "anthropic/claude-3.7-sonnet")
        self.assertEqual(params["api_key"], "sk-or-v1-testkey123")
        self.assertEqual(params["tts_base_url"], "https://openrouter.ai/api/v1")
        self.assertEqual(params["tts_api_key"], "sk-or-v1-ttstestkey")
        self.assertEqual(params["thinking_level"], "high")
        self.assertEqual(params["thinking_budget"], -1)
        self.assertEqual(params["extra_params"], '{"top_p": 0.95, "max_tokens": 2048}')

        # Verify LLM creation
        llm = get_llm()
        self.assertEqual(llm.model_name, "anthropic/claude-3.7-sonnet")
        self.assertEqual(llm.openai_api_key.get_secret_value(), "sk-or-v1-testkey123")
        self.assertEqual(llm.top_p, 0.95)
        self.assertEqual(llm.max_tokens, 2048)

    def test_tts_model_info_and_voices_endpoints(self):
        resp = self.client.post("/api/dev/tts-model-info/", data={
            "base_url": "https://openrouter.ai/api/v1",
            "model": "deepgram/flux-tts:free",
            "api_key": "test",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("voices", data)
        self.assertTrue(len(data["voices"]) > 0)
        self.assertEqual(data["default_voice"], "flux-alexis-en")

        resp_v = self.client.post("/api/dev/tts-voices/", data={
            "base_url": "https://openrouter.ai/api/v1",
            "model": "deepgram/flux-tts:free",
            "api_key": "test",
        }, format="json")
        self.assertEqual(resp_v.status_code, 200)
        self.assertTrue(resp_v.json()["count"] > 0)
