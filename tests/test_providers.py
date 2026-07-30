import json
import tempfile
import unittest
from pathlib import Path

import httpx

from src.ai.providers import (
    ANTHROPIC_COMPATIBLE,
    OPENAI_COMPATIBLE,
    CompletionResult,
    ProviderClient,
    ProviderConfig,
    ProviderRequestError,
    ProviderStore,
    create_provider_from_template,
)


class ProviderStoreTests(unittest.TestCase):
    def test_store_round_trip_and_switch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProviderStore(Path(temp_dir) / "providers.json")
            first = create_provider_from_template(
                "zhipu",
                provider_id="zhipu-id",
                api_key="secret-one",
            )
            second = create_provider_from_template(
                "deepseek",
                provider_id="deepseek-id",
                api_key="secret-two",
            )

            state = store.upsert(first)
            self.assertEqual(state.current, first.id)
            store.upsert(second)
            state = store.set_current(second.id)

            loaded = store.load()
            self.assertEqual(loaded.current, second.id)
            self.assertEqual(loaded.active.name, "DeepSeek")
            self.assertEqual(loaded.providers[first.id].api_key, "secret-one")

            state = store.delete(second.id)
            self.assertEqual(state.current, first.id)

    def test_duplicate_names_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProviderStore(Path(temp_dir) / "providers.json")
            store.upsert(
                create_provider_from_template(
                    "zhipu", provider_id="one", name="Primary"
                )
            )
            duplicate = create_provider_from_template(
                "deepseek", provider_id="two", name="primary"
            )
            with self.assertRaisesRegex(ValueError, "名称已存在"):
                store.upsert(duplicate)


class ProviderClientTests(unittest.TestCase):
    def test_openai_length_finish_reason_is_truncated(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {"content": "partial report"},
                            "finish_reason": "length",
                        }
                    ]
                },
            )

        config = create_provider_from_template(
            "custom_openai",
            name="OpenAI Metadata",
            base_url="https://api.example.com/v1",
            model="test-model",
        )
        with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
            result = ProviderClient(
                config,
                http_client=http_client,
            ).complete_with_metadata([{"role": "user", "content": "analyze"}])

        self.assertEqual(
            result,
            CompletionResult(text="partial report", stop_reason="length"),
        )
        self.assertTrue(result.truncated)

    def test_anthropic_max_tokens_stop_reason_is_truncated(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "partial report"}],
                    "stop_reason": "max_tokens",
                },
            )

        config = create_provider_from_template(
            "custom_anthropic",
            name="Anthropic Metadata",
            base_url="https://api.anthropic.test",
            model="claude-test",
        )
        with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
            result = ProviderClient(
                config,
                http_client=http_client,
            ).complete_with_metadata([{"role": "user", "content": "analyze"}])

        self.assertEqual(result.stop_reason, "max_tokens")
        self.assertTrue(result.truncated)

    def test_openai_compatible_request_and_response(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                str(request.url), "https://api.example.com/v1/chat/completions"
            )
            self.assertEqual(request.headers["authorization"], "Bearer test-key")
            self.assertEqual(request.headers["x-trace"], "enabled")
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "test-model")
            self.assertEqual(payload["response_format"], {"type": "json_object"})
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": '{"ATT":["Roll"]}'}}]},
            )

        config = ProviderConfig(
            id="openai-test",
            name="OpenAI Test",
            template_id="custom_openai",
            protocol=OPENAI_COMPATIBLE,
            base_url="https://api.example.com/v1",
            endpoint="chat/completions",
            api_key="test-key",
            model="test-model",
            supports_json_mode=True,
            custom_headers={"X-Trace": "enabled"},
        )
        with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
            result = ProviderClient(config, http_client=http_client).complete(
                [{"role": "user", "content": "select fields"}],
                json_mode=True,
            )
        self.assertEqual(result, '{"ATT":["Roll"]}')

    def test_openai_compatible_can_disable_json_mode(self):
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            self.assertNotIn("response_format", payload)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": '{"ATT":["Roll"]}'}}]},
            )

        config = create_provider_from_template(
            "custom_openai",
            name="No JSON Mode",
            base_url="https://api.example.com/v1",
            model="test-model",
            supports_json_mode=False,
        )
        with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
            result = ProviderClient(config, http_client=http_client).complete(
                [{"role": "user", "content": "select fields"}],
                json_mode=True,
            )
        self.assertEqual(result, '{"ATT":["Roll"]}')

    def test_openai_compatible_model_list(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "GET")
            self.assertEqual(str(request.url), "https://api.example.com/v1/models")
            self.assertEqual(request.headers["authorization"], "Bearer test-key")
            self.assertEqual(request.headers["x-trace"], "enabled")
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "model-z"},
                        {"id": "model-a"},
                        {"id": "model-a"},
                    ]
                },
            )

        config = create_provider_from_template(
            "custom_openai",
            name="Model Discovery",
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="",
            custom_headers={"X-Trace": "enabled"},
            require_model=False,
        )
        with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
            models = ProviderClient(config, http_client=http_client).list_models()
        self.assertEqual(models, ["model-a", "model-z"])

    def test_anthropic_compatible_model_list(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "GET")
            self.assertEqual(str(request.url), "https://api.anthropic.test/v1/models")
            self.assertEqual(request.headers["x-api-key"], "anthropic-key")
            self.assertEqual(request.headers["anthropic-version"], "2023-06-01")
            self.assertNotIn("authorization", request.headers)
            return httpx.Response(
                200,
                json={"data": [{"id": "claude-test"}]},
            )

        config = create_provider_from_template(
            "custom_anthropic",
            name="Anthropic Models",
            base_url="https://api.anthropic.test",
            api_key="anthropic-key",
            model="claude-test",
        )
        with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
            models = ProviderClient(config, http_client=http_client).list_models()
        self.assertEqual(models, ["claude-test"])

    def test_model_list_rejects_empty_response(self):
        config = create_provider_from_template(
            "custom_openai",
            name="Empty Models",
            base_url="https://api.example.com/v1",
            model="test-model",
        )

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": []})

        with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
            with self.assertRaisesRegex(ProviderRequestError, "未返回可用模型"):
                ProviderClient(config, http_client=http_client).list_models()

    def test_anthropic_compatible_request_and_response(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(str(request.url), "https://api.anthropic.test/v1/messages")
            self.assertEqual(request.headers["x-api-key"], "anthropic-key")
            payload = json.loads(request.content)
            self.assertEqual(payload["system"], "system prompt")
            self.assertEqual(payload["messages"], [{"role": "user", "content": "question"}])
            return httpx.Response(
                200,
                json={"content": [{"type": "text", "text": "analysis result"}]},
            )

        config = ProviderConfig(
            id="anthropic-test",
            name="Anthropic Test",
            template_id="custom_anthropic",
            protocol=ANTHROPIC_COMPATIBLE,
            base_url="https://api.anthropic.test",
            endpoint="v1/messages",
            api_key="anthropic-key",
            model="claude-test",
        )
        with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
            result = ProviderClient(config, http_client=http_client).complete(
                [
                    {"role": "system", "content": "system prompt"},
                    {"role": "user", "content": "question"},
                ]
            )
        self.assertEqual(result, "analysis result")

    def test_http_error_does_not_expose_api_key(self):
        config = create_provider_from_template(
            "custom_openai",
            name="Error Test",
            base_url="https://api.example.com/v1",
            model="test-model",
            api_key="do-not-leak-this-key",
        )

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"message": "invalid key"}})

        with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
            with self.assertRaises(ProviderRequestError) as raised:
                ProviderClient(config, http_client=http_client).complete(
                    [{"role": "user", "content": "hello"}]
                )
        self.assertNotIn(config.api_key, str(raised.exception))
        self.assertIn("401", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
