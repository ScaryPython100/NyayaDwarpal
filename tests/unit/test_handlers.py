"""
Unit tests for Lambda handler logic (AWS calls mocked)
"""

import importlib.util
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
# Same modules as shared/python, without the Linux libraries bundled there for Lambda
sys.path.insert(0, str(ROOT / "lambda_functions" / "shared"))
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-south-2")


def load_handler(name):
    """Import lambda_functions/<name>/handler.py under a unique module name"""
    spec = importlib.util.spec_from_file_location(f"{name}_handler", ROOT / "lambda_functions" / name / "handler.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def triage():
    return load_handler("voice_triage")


@pytest.fixture(scope="module")
def cases():
    return load_handler("case_memory")


@pytest.fixture(scope="module")
def transcribe():
    return load_handler("audio_transcribe")


class TestTriageNormalization:
    @pytest.mark.parametrize("value,expected", [
        ("high", "high"), ("High", "high"), ("उच्च", "high"), ("అధిక", "high"),
        ("low", "low"), ("निम्न", "low"), ("medium", "medium"), ("मध्यम", "medium"),
        ("", "medium"), (None, "medium"),
    ])
    def test_levels(self, triage, value, expected):
        assert triage.normalize_level(value) == expected

    @pytest.mark.parametrize("value,expected", [
        ("angry", "angry"), ("Frustrated", "frustrated"), ("calm", "calm"),
        ("निराश", "distressed"), ("", "calm"),
    ])
    def test_emotions(self, triage, value, expected):
        assert triage.normalize_emotion(value) == expected

    def test_one_bedrock_call_and_english_labels(self, triage):
        model_answer = {
            "category": "Employment Law - Unpaid Wages",
            "urgency": "उच्च",
            "severity": "high",
            "emotionalState": "frustrated",
            "legalSections": [{"act": "Code on Wages, 2019", "section": "Section 17"}],
            "nextSteps": "Write to employer, File complaint",
            "facts": {"who": "worker"},
        }
        fake = {"text": "Here you go:\n" + json.dumps(model_answer, ensure_ascii=False), "usage": {}}
        with patch.object(triage.bedrock_client, "invoke_model", return_value=fake) as invoke, \
             patch.object(triage.dynamodb_helper, "put_item") as put_item:
            response = triage.lambda_handler({"body": json.dumps({
                "userId": "user-123456-abcdef", "transcribedText": "Salary not paid", "language": "hi"
            })}, None)
        body = json.loads(response["body"])
        assert response["statusCode"] == 200
        assert invoke.call_count == 1
        assert body["data"]["emotion"]["urgency"] == "high"
        assert body["data"]["emotion"]["primary"] == "frustrated"
        assert body["data"]["nextSteps"] == ["Write to employer", "File complaint"]
        saved = put_item.call_args.args[1]
        assert saved["emotion"]["primary"] == "frustrated"

    def test_bad_ai_answer_is_an_error_not_a_fake_result(self, triage):
        with patch.object(triage.bedrock_client, "invoke_model", return_value={"text": "Sorry, I cannot help"}) as invoke, \
             patch.object(triage.dynamodb_helper, "put_item") as put_item:
            response = triage.lambda_handler({"body": json.dumps({
                "userId": "user-123456-abcdef", "transcribedText": "Salary not paid", "language": "en"
            })}, None)
        assert response["statusCode"] == 502
        assert invoke.call_count == 2  # one retry
        put_item.assert_not_called()

    def test_text_length_limit(self, triage):
        response = triage.lambda_handler({"body": json.dumps({
            "userId": "user-123456-abcdef", "transcribedText": "x" * 6000, "language": "en"
        })}, None)
        assert response["statusCode"] == 400


class TestCaseMemory:
    @pytest.mark.parametrize("user_id", ["all", "", "user-1", "<script>", None])
    def test_rejects_missing_or_bad_user_id(self, cases, user_id):
        params = {} if user_id is None else {"userId": user_id}
        response = cases.lambda_handler({"queryStringParameters": params}, None)
        assert response["statusCode"] == 400

    def test_queries_only_that_user_newest_first(self, cases):
        table = MagicMock()
        table.query.return_value = {"Items": [{
            "sessionId": "abc", "userId": "user-123456-abcdef", "timestamp": "2026-10-28T10:00:00",
            "transcription": "Short issue", "emotion": {"primary": "calm"},
        }]}
        with patch.object(cases.dynamodb, "Table", return_value=table):
            response = cases.lambda_handler({"queryStringParameters": {"userId": "user-123456-abcdef", "limit": "500"}}, None)
        kwargs = table.query.call_args.kwargs
        assert kwargs["IndexName"] == "UserIdIndex"
        assert kwargs["ScanIndexForward"] is False
        assert kwargs["Limit"] == 50
        case = json.loads(response["body"])["data"]["cases"][0]
        assert case["issueSummary"] == "Short issue"
        assert "userId" not in case


class TestTranscribe:
    def test_safari_audio_is_sent_as_m4a(self, transcribe):
        ok = MagicMock(status_code=200)
        ok.json.return_value = {"transcript": "namaste", "language_code": "hi-IN"}
        with patch.dict(os.environ, {"SARVAM_API_KEY": "test-key"}), \
             patch.object(transcribe.requests, "post", return_value=ok) as post:
            response = transcribe.lambda_handler({"body": json.dumps({
                "audio": "AAAA", "mime_type": "audio/mp4;codecs=mp4a.40.2", "language_code": "unknown"
            })}, None)
        sent = post.call_args.kwargs
        assert sent["files"]["file"][0] == "recording.m4a"
        assert sent["data"]["language_code"] == "unknown"
        body = json.loads(response["body"])
        assert body["data"]["language_code"] == "hi-IN"

    def test_rejected_key_gives_friendly_error(self, transcribe):
        denied = MagicMock(status_code=403, text='{"error":"invalid_api_key_error"}')
        with patch.dict(os.environ, {"SARVAM_API_KEY": "old-key"}), \
             patch.object(transcribe.requests, "post", return_value=denied):
            response = transcribe.lambda_handler({"body": json.dumps({"audio": "AAAA"})}, None)
        body = json.loads(response["body"])
        assert response["statusCode"] == 503
        assert body["errorCode"] == "service_unavailable"
        assert "invalid_api_key" not in body["error"]


class TestTranslationChunks:
    @pytest.fixture(scope="class")
    def translator(self):
        return load_handler("document_translator")

    @pytest.mark.parametrize("text", [
        "word " * 2000,                                   # one long line, no punctuation
        "यह एक वाक्य है। " * 300,                           # Hindi sentences on one line
        "Line one.\n" * 400,                               # many short lines
        "x" * 2500,                                        # no spaces at all
    ])
    def test_chunks_stay_under_sarvam_limit_and_keep_all_text(self, translator, text):
        chunks = translator.split_into_chunks(text, 900)
        assert chunks and all(len(c) <= 900 for c in chunks)
        assert "".join(chunks).replace(" ", "").replace("\n", "") == text.replace(" ", "").replace("\n", "")

    def test_bad_json_body_is_a_400(self, translator):
        response = translator.lambda_handler({"body": "{not json"}, None)
        assert response["statusCode"] == 400
