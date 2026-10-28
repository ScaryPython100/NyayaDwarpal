"""
Unit tests for Bedrock client integration
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError

from lambda_functions.shared.bedrock_client import BedrockClient


class TestBedrockClient:
    """Test suite for BedrockClient"""
    
    @pytest.fixture
    def bedrock_client(self):
        """Create BedrockClient instance for testing"""
        return BedrockClient(region="us-east-1")
    
    @pytest.fixture
    def mock_bedrock_response(self):
        """Mock Bedrock API response"""
        return {
            "body": MagicMock(
                read=lambda: json.dumps({
                    "content": [{"text": "Test response"}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 10, "output_tokens": 20}
                }).encode()
            )
        }
    
    def test_invoke_model_success(self, bedrock_client, mock_bedrock_response):
        """Test successful model invocation"""
        with patch.object(bedrock_client.client, "invoke_model", return_value=mock_bedrock_response):
            result = bedrock_client.invoke_model(
                prompt="Test prompt",
                max_tokens=100,
                temperature=0.7
            )
            
            assert result["text"] == "Test response"
            assert result["stop_reason"] == "end_turn"
            assert result["usage"]["input_tokens"] == 10
            assert result["model_id"] == BedrockClient.MODEL_ID
    
    def test_invoke_model_with_system_prompt(self, bedrock_client, mock_bedrock_response):
        """Test model invocation with system prompt"""
        with patch.object(bedrock_client.client, "invoke_model", return_value=mock_bedrock_response) as mock_invoke:
            bedrock_client.invoke_model(
                prompt="Test prompt",
                system_prompt="You are a legal assistant"
            )
            
            # Verify system prompt was included in request
            call_args = mock_invoke.call_args
            body = json.loads(call_args.kwargs["body"])
            assert "system" in body
            assert body["system"] == "You are a legal assistant"
    
    def test_invoke_model_throttling_retry(self, bedrock_client):
        """Test retry logic for throttling errors"""
        # First two calls fail with throttling, third succeeds
        mock_response = {
            "body": MagicMock(
                read=lambda: json.dumps({
                    "content": [{"text": "Success after retry"}],
                    "stop_reason": "end_turn",
                    "usage": {}
                }).encode()
            )
        }
        
        throttle_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "invoke_model"
        )
        
        with patch.object(bedrock_client.client, "invoke_model") as mock_invoke:
            mock_invoke.side_effect = [throttle_error, throttle_error, mock_response]
            
            result = bedrock_client.invoke_model(prompt="Test", retry_attempts=3)
            
            assert result["text"] == "Success after retry"
            assert mock_invoke.call_count == 3
    
    def test_invoke_model_max_retries_exceeded(self, bedrock_client):
        """Test failure after max retries"""
        throttle_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "invoke_model"
        )
        
        with patch.object(bedrock_client.client, "invoke_model", side_effect=throttle_error):
            with pytest.raises(ClientError):
                bedrock_client.invoke_model(prompt="Test", retry_attempts=2)
    
    def test_build_legal_triage_prompt(self, bedrock_client):
        """Test legal triage prompt generation"""
        prompt = bedrock_client.build_legal_triage_prompt(
            transcribed_text="मेरी जमीन पर कब्जा कर लिया गया है",
            language="hi"
        )
        
        assert "मेरी जमीन पर कब्जा कर लिया गया है" in prompt
        assert "hi" in prompt
        assert "Key Facts" in prompt
        assert "Legal Category" in prompt
        assert "JSON" in prompt
    
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
    
    def test_rate_limiting(self, bedrock_client):
        """Test token bucket rate limiting"""
        initial_tokens = bedrock_client.token_bucket
        
        # Consume tokens
        bedrock_client._wait_for_tokens(1000)
        
        assert bedrock_client.token_bucket < initial_tokens
        assert bedrock_client.token_bucket >= 0
    
    def test_token_bucket_refill(self, bedrock_client):
        """Test token bucket refills over time"""
        import time
        
        # Consume tokens
        bedrock_client._wait_for_tokens(5000)
        tokens_after_consumption = bedrock_client.token_bucket
        
        # Wait for refill
        time.sleep(1)
        bedrock_client._refill_token_bucket()
        
        assert bedrock_client.token_bucket > tokens_after_consumption
