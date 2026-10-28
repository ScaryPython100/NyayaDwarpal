"""
AWS Bedrock Integration Utility - Using Amazon Nova Lite
"""

import json
import time
import boto3
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError


class BedrockClient:
    MODEL_ID = "amazon.nova-lite-v1:0"

    def __init__(self, region: str = "us-east-1"):
        self.region = region
        self.client = None

    def _ensure_client(self):
        if self.client is None:
            print(f"[Bedrock] Initializing client in region: {self.region}")
            self.client = boto3.client(
                service_name='bedrock-runtime',
                region_name=self.region
            )

    def invoke_model(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        retry_attempts: int = 3,
    ) -> Dict[str, Any]:
        self._ensure_client()
        print(f"[Bedrock] Invoking model with temperature={temperature}, max_tokens={max_tokens}")

        request_body = {
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": prompt}]
                }
            ],
            "inferenceConfig": {
                "maxTokens": max_tokens,
                "temperature": temperature,
            }
        }

        if system_prompt:
            request_body["system"] = [{"text": system_prompt}]
            print(f"[Bedrock] System prompt: {system_prompt[:200]}...")

        print(f"[Bedrock] Sending request to {self.MODEL_ID}...")

        for attempt in range(retry_attempts):
            try:
                response = self.client.invoke_model(
                    modelId=self.MODEL_ID,
                    body=json.dumps(request_body)
                )

                response_body = json.loads(response['body'].read())
                stop_reason = response_body.get('stopReason', '')
                print(f"[Bedrock] Response received. Stop reason: {stop_reason}")

                text_content = ""
                output = response_body.get('output', {})
                message = output.get('message', {})
                for content_block in message.get('content', []):
                    if isinstance(content_block, dict) and 'text' in content_block:
                        text_content += content_block['text']

                usage = response_body.get('usage', {})
                input_tokens = usage.get('inputTokens', 0)
                output_tokens = usage.get('outputTokens', 0)

                return {
                    "text": text_content,
                    "stop_reason": stop_reason,
                    "usage": {
                        "prompt_tokens": input_tokens,
                        "completion_tokens": output_tokens,
                        "total_tokens": input_tokens + output_tokens
                    },
                    "model_id": self.MODEL_ID,
                }

            except ClientError as e:
                error_code = e.response['Error']['Code']
                error_message = e.response['Error']['Message']
                print(f"[Bedrock] Error on attempt {attempt + 1}: {error_code} - {error_message}")

                if error_code == 'ThrottlingException' and attempt < retry_attempts - 1:
                    wait_time = (2 ** attempt) * 1.0
                    print(f"[Bedrock] Throttled. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue

                if attempt < retry_attempts - 1:
                    print(f"[Bedrock] Retrying in 2s...")
                    time.sleep(2.0)
                    continue
                raise

            except Exception as e:
                print(f"[Bedrock] Error on attempt {attempt + 1}: {str(e)}")
                if attempt < retry_attempts - 1:
                    print(f"[Bedrock] Retrying in 2s...")
                    time.sleep(2.0)
                    continue
                raise

        raise Exception("All retry attempts failed")

    def build_legal_triage_prompt(self, transcribed_text: str, language: str, use_native_script: bool = True) -> str:
        language_map = {
            'en': {'name': 'English', 'script': 'Latin script'},
            'hi': {'name': 'Hindi', 'script': 'Devanagari script (देवनागरी अक्षर)'},
            'te': {'name': 'Telugu', 'script': 'Telugu script (తెలుగు అక్షరాలు)'},
            'ta': {'name': 'Tamil', 'script': 'Tamil script (தமிழ் எழுத்துக்கள்)'},
            'bn': {'name': 'Bengali', 'script': 'Bengali script (বাংলা লিপি)'},
            'mr': {'name': 'Marathi', 'script': 'Devanagari script (देवनागरी अक्षर)'},
            'gu': {'name': 'Gujarati', 'script': 'Gujarati script (ગુજરાતી લિપિ)'},
            'kn': {'name': 'Kannada', 'script': 'Kannada script (ಕನ್ನಡ ಲಿಪಿ)'},
            'ml': {'name': 'Malayalam', 'script': 'Malayalam script (മലയാളം ലിപി)'},
            'pa': {'name': 'Punjabi', 'script': 'Gurmukhi script (ਗੁਰਮੁਖੀ ਲਿਪੀ)'},
        }

        lang_info = language_map.get(language, {'name': language, 'script': 'native script'})
        language_name = lang_info['name']
        script_name = lang_info['script']

        if language == 'en':
            language_instruction = "Respond in clear, professional English.\nJSON keys must be in English. All content values must be in English."
            language_reminder = ""
        elif use_native_script:
            language_instruction = f"YOU MUST RESPOND ONLY IN {language_name.upper()} USING {script_name.upper()}.\nFor {language_name}: Use ONLY {script_name}.\nABSOLUTELY NO English or Roman letters in your response content. JSON keys must stay in English but ALL values must be in {script_name}."
            language_reminder = f"\nREMINDER: YOU MUST RESPOND ONLY IN {language_name.upper()} USING {script_name.upper()}. ABSOLUTELY NO English or Roman letters in response values."
        else:
            language_instruction = f"Respond in {language_name} using English/Roman letters (romanized/transliterated text).\nJSON keys must be in English. All content values must be in romanized {language_name}."
            language_reminder = ""

        return f"""{language_instruction}

You are an expert Indian lawyer with 20+ years of experience. A client has come to you with this legal issue:

CLIENT'S ISSUE (in {language_name}):
"{transcribed_text}"

Your job is to provide EXTREMELY DETAILED, ACTIONABLE legal advice that the client can act on IMMEDIATELY. Do NOT give generic advice like "consult a lawyer" - that's useless. Give SPECIFIC steps they can take TODAY.

ANALYZE AND CATEGORIZE:

1. LEGAL CATEGORY (choose most specific - DO NOT use "Other" unless absolutely necessary):
   - Employment Law - Unpaid Wages
   - Employment Law - Wrongful Termination
   - Employment Law - Workplace Harassment
   - Property Law - Tenant Rights
   - Property Law - Property Disputes
   - Consumer Rights - Defective Products
   - Consumer Rights - Service Deficiency
   - Family Law - Divorce
   - Family Law - Child Custody
   - Family Law - Domestic Violence
   - Criminal Law - Theft/Fraud
   - Criminal Law - Assault
   - Contract Law - Breach
   - Civil Disputes - Damages
   - Other: ONLY if truly doesn't fit any category above

2. URGENCY LEVEL: HIGH / MEDIUM / LOW

3. PROVIDE EXTREMELY DETAILED ADVICE with immediate actions, step-by-step legal process, where to file, costs, timeline, legal rights and laws, compensation, free resources, and warnings.

CRITICAL: Return ONLY valid JSON - NO markdown backticks, NO preamble, NO extra text.

Respond in JSON format with these EXACT keys:
{{
  "category": "Consumer Rights - Service Deficiency",
  "subCategory": "Auto driver overcharged fare",
  "urgency": "medium",
  "urgencyReason": "Financial exploitation by public transport operator",
  "emotionalState": "frustrated",
  "facts": {{
    "who": "auto driver and passenger",
    "what": "overcharging fare",
    "when": "recent",
    "where": "public road",
    "amount": "extra amount charged"
  }},
  "legalSections": [
    {{
      "act": "Consumer Protection Act, 2019",
      "section": "Section 2(11)",
      "description": "Deficiency in service by transport provider",
      "penalty": "Compensation + punitive damages",
      "remedy": "Refund of excess amount + compensation"
    }}
  ],
  "recommendation": "DETAILED multi-paragraph advice with specific steps, timelines, costs, and resources - minimum 500 words",
  "nextSteps": [
    "TODAY: Note auto number, time, route, amount paid vs meter reading",
    "DAY 1: File complaint on consumerhelpline.gov.in (FREE)",
    "DAY 2: File complaint at nearest Regional Transport Office (RTO)",
    "WEEK 1: If unresolved, file at District Consumer Forum (filing fee: ₹500)"
  ],
  "requiredDocuments": [
    "Receipt or note of amount paid",
    "Auto registration number",
    "Photo of meter reading if possible",
    "Bank transaction record if paid digitally"
  ],
  "estimatedCost": "Consumer helpline: FREE, RTO complaint: FREE, Consumer Forum: ₹500 filing fee",
  "timeline": "RTO action: 7-15 days, Consumer Forum: 3-6 months",
  "severity": "medium",
  "resources": [
    {{
      "name": "National Consumer Helpline",
      "action": "Call 1800-11-4000 (toll free) or file at consumerhelpline.gov.in",
      "cost": "FREE",
      "timeline": "Response within 7 days"
    }},
    {{
      "name": "Regional Transport Office (RTO)",
      "action": "File complaint against auto driver license/permit",
      "cost": "FREE",
      "timeline": "Action within 15 days"
    }}
  ],
  "legalDisclaimer": "This advice is AI-generated for informational purposes only. Please consult a qualified legal professional before taking any action. Laws may vary by state."
}}
{language_reminder}"""

    def build_petition_generation_prompt(self, facts: Dict[str, Any], legal_category: str, relevant_sections: list) -> str:
        return f"""You are a legal document drafting assistant for Indian courts. Generate a structured legal petition.

Facts: {json.dumps(facts, indent=2, ensure_ascii=False)}
Legal Category: {legal_category}
Relevant Sections: {', '.join(relevant_sections)}

Generate a petition with three sections:
1. FACTS: Organize the story chronologically with dates and parties clearly identified
2. GROUNDS: Cite relevant legal provisions (BNS/BNSS/CPC sections) that support the case
3. PRAYER: Specify the relief sought (monetary compensation, injunction, possession, etc.)

Format your response as JSON with keys: facts_section, grounds_section, prayer_section."""

    def build_citation_verification_prompt(self, petition_text: str, citations: list) -> str:
        return f"""You are a legal citation verification assistant for Indian law. Review the following citations.

Petition excerpt:
{petition_text[:1000]}...

Citations to verify:
{json.dumps(citations, indent=2, ensure_ascii=False)}

For each citation:
1. Check if it's outdated (e.g., IPC instead of BNS, CrPC instead of BNSS)
2. Assess relevance to the legal argument
3. Suggest updated equivalents if outdated

Format your response as JSON array with objects containing: citation, is_outdated, suggested_replacement, relevance_score (0-1), relevance_explanation."""

    def build_clarification_prompt(self, petition_draft: str, missing_info: list) -> str:
        return f"""You are a helpful legal assistant. The petition draft is missing some information.

Current draft:
{petition_draft[:500]}...

Missing information:
{json.dumps(missing_info, indent=2, ensure_ascii=False)}

Generate up to 5 targeted clarifying questions in simple, non-legal language. Focus on critical information like dates, amounts, and names.

Format your response as JSON array of strings (questions)."""
