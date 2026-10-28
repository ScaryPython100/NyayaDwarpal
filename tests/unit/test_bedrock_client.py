"""
Unit tests for Bedrock client integration (Amazon Nova Lite)
"""

import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

from lambda_functions.shared.bedrock_client import BedrockClient


SHARED_DIR = Path(__file__).resolve().parents[2] / "lambda_functions" / "shared"


def nova_response(text="Test response", stop_reason="end_turn", input_tokens=10, output_tokens=20):
    """Build a fake invoke_model response in the Nova Lite format"""
    body = {
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        "stopReason": stop_reason,
        "usage": {"inputTokens": input_tokens, "outputTokens": output_tokens},
    }
    return {"body": MagicMock(read=lambda: json.dumps(body).encode())}


def throttle_error():
    return ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
        "invoke_model"
    )


class TestBedrockClient:
    """Test suite for BedrockClient"""

    @pytest.fixture
    def bedrock_client(self):
        """BedrockClient with a mocked boto3 client"""
        client = BedrockClient(region="us-east-1")
        client.client = MagicMock()
        return client

    @pytest.fixture(autouse=True)
    def no_sleep(self):
        """Skip retry back-off waits"""
        with patch("lambda_functions.shared.bedrock_client.time.sleep") as mock_sleep:
            yield mock_sleep

    def test_layer_copy_matches(self):
        """The layer ships python/bedrock_client.py; the tested copy must be identical"""
        tested = (SHARED_DIR / "bedrock_client.py").read_text()
        shipped = (SHARED_DIR / "python" / "bedrock_client.py").read_text()
        assert tested == shipped

    def test_uses_nova_lite(self):
        assert BedrockClient.MODEL_ID == "amazon.nova-lite-v1:0"

    def test_client_created_lazily(self):
        """No boto3 client is made until the first call"""
        client = BedrockClient(region="us-east-1")
        assert client.client is None
        with patch("lambda_functions.shared.bedrock_client.boto3.client") as mock_boto:
            client._ensure_client()
            mock_boto.assert_called_once_with(service_name="bedrock-runtime", region_name="us-east-1")

    def test_invoke_model_success(self, bedrock_client):
        """Test successful model invocation"""
        bedrock_client.client.invoke_model.return_value = nova_response()

        result = bedrock_client.invoke_model(prompt="Test prompt", max_tokens=100, temperature=0.7)

        assert result["text"] == "Test response"
        assert result["stop_reason"] == "end_turn"
        assert result["usage"] == {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        assert result["model_id"] == BedrockClient.MODEL_ID

    def test_request_body_format(self, bedrock_client):
        """Prompt and settings are sent in the Nova messages format"""
        bedrock_client.client.invoke_model.return_value = nova_response()

        bedrock_client.invoke_model(prompt="Test prompt", max_tokens=100, temperature=0.3)

        kwargs = bedrock_client.client.invoke_model.call_args.kwargs
        assert kwargs["modelId"] == BedrockClient.MODEL_ID
        body = json.loads(kwargs["body"])
        assert body["messages"] == [{"role": "user", "content": [{"text": "Test prompt"}]}]
        assert body["inferenceConfig"] == {"maxTokens": 100, "temperature": 0.3}
        assert "system" not in body

    def test_invoke_model_with_system_prompt(self, bedrock_client):
        """Test model invocation with system prompt"""
        bedrock_client.client.invoke_model.return_value = nova_response()

        bedrock_client.invoke_model(prompt="Test prompt", system_prompt="You are a legal assistant")

        body = json.loads(bedrock_client.client.invoke_model.call_args.kwargs["body"])
        assert body["system"] == [{"text": "You are a legal assistant"}]

    def test_joins_multiple_text_blocks(self, bedrock_client):
        body = {
            "output": {"message": {"content": [{"text": "Part 1. "}, {"text": "Part 2."}]}},
            "stopReason": "end_turn",
            "usage": {},
        }
        bedrock_client.client.invoke_model.return_value = {"body": MagicMock(read=lambda: json.dumps(body).encode())}

        result = bedrock_client.invoke_model(prompt="Test")

        assert result["text"] == "Part 1. Part 2."
        assert result["usage"]["total_tokens"] == 0

    def test_invoke_model_throttling_retry(self, bedrock_client, no_sleep):
        """Test retry logic for throttling errors"""
        bedrock_client.client.invoke_model.side_effect = [
            throttle_error(), throttle_error(), nova_response("Success after retry")
        ]

        result = bedrock_client.invoke_model(prompt="Test", retry_attempts=3)

        assert result["text"] == "Success after retry"
        assert bedrock_client.client.invoke_model.call_count == 3
        # Exponential back-off: 1s, then 2s
        assert [c.args[0] for c in no_sleep.call_args_list] == [1.0, 2.0]

    def test_invoke_model_max_retries_exceeded(self, bedrock_client):
        """Test failure after max retries"""
        bedrock_client.client.invoke_model.side_effect = throttle_error()

        with pytest.raises(ClientError):
            bedrock_client.invoke_model(prompt="Test", retry_attempts=2)
        assert bedrock_client.client.invoke_model.call_count == 2

    def test_other_errors_are_retried_then_raised(self, bedrock_client):
        bedrock_client.client.invoke_model.side_effect = ValueError("bad response")

        with pytest.raises(ValueError):
            bedrock_client.invoke_model(prompt="Test", retry_attempts=3)
        assert bedrock_client.client.invoke_model.call_count == 3

    def test_build_legal_triage_prompt(self, bedrock_client):
        """Test legal triage prompt generation"""
        prompt = bedrock_client.build_legal_triage_prompt(
            transcribed_text="मेरी जमीन पर कब्जा कर लिया गया है",
            language="hi"
        )

        assert "मेरी जमीन पर कब्जा कर लिया गया है" in prompt
        assert "HINDI" in prompt
        assert "DEVANAGARI SCRIPT" in prompt
        assert "LEGAL CATEGORY" in prompt
        assert "JSON" in prompt
        assert '"legalSections"' in prompt

    def test_build_legal_triage_prompt_english(self, bedrock_client):
        prompt = bedrock_client.build_legal_triage_prompt(
            transcribed_text="My landlord is not returning my deposit",
            language="en"
        )

        assert prompt.startswith("Respond in clear, professional English.")
        assert "REMINDER" not in prompt

    def test_build_legal_triage_prompt_romanized(self, bedrock_client):
        prompt = bedrock_client.build_legal_triage_prompt(
            transcribed_text="Auto wale ne meter se 3 guna paisa manga",
            language="hi",
            use_native_script=False
        )

        assert "romanized Hindi" in prompt
        assert "REMINDER" not in prompt

    def test_build_petition_generation_prompt(self, bedrock_client):
        """Test petition generation prompt"""
        facts = {
            "who": "Plaintiff vs Defendant",
            "what": "Property dispute",
            "when": "2024-01-15",
            "where": "Mumbai"
        }

        prompt = bedrock_client.build_petition_generation_prompt(
            facts=facts,
            legal_category="Civil",
            relevant_sections=["Section 9 CPC", "Section 38 Specific Relief Act"]
        )

        assert "Property dispute" in prompt
        assert "Civil" in prompt
        assert "Section 9 CPC" in prompt
        assert "FACTS" in prompt
        assert "GROUNDS" in prompt
        assert "PRAYER" in prompt

    def test_build_citation_verification_prompt(self, bedrock_client):
        """Test citation verification prompt"""
        citations = [
            "Section 302 IPC",
            "2023 SCC 123",
            "AIR 2022 SC 456"
        ]

        prompt = bedrock_client.build_citation_verification_prompt(
            petition_text="Sample petition text with citations...",
            citations=citations
        )

        assert "Section 302 IPC" in prompt
        assert "2023 SCC 123" in prompt
        assert "outdated" in prompt.lower()
        assert "relevance" in prompt.lower()

    def test_build_clarification_prompt(self, bedrock_client):
        """Test clarification question prompt"""
        missing_info = ["Date of incident", "Amount claimed", "Defendant's address"]

        prompt = bedrock_client.build_clarification_prompt(
            petition_draft="Draft petition...",
            missing_info=missing_info
        )

        assert "Date of incident" in prompt
        assert "Amount claimed" in prompt
        assert "5" in prompt  # Maximum 5 questions
        assert "simple" in prompt.lower()
