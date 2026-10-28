"""
Voice Triage Lambda Handler

This Lambda function processes transcribed text from voice input,
detects emotion and urgency, and classifies the legal problem using AWS Bedrock.

Note: Audio recording and transcription (via Sarvam AI) is handled by the frontend.
This Lambda only receives the final transcribed text.
"""

import json
import re
import os
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any
from decimal import Decimal
import boto3

# Import shared utilities (from Lambda layer)
import sys
sys.path.insert(0, '/opt/python')

from bedrock_client import BedrockClient
from models import (
    SeverityLevel, EmotionalState,
    UserSession, APIResponse
)
from aws_helpers import S3Helper, DynamoDBHelper
from law_map import fix_sections


# Environment variables
DOCUMENT_BUCKET = os.environ.get('DOCUMENT_BUCKET', 'nyaya-dwarpal-documents')
SESSION_TABLE = os.environ.get('SESSION_TABLE', 'NyayaDwarpal-Sessions')
BEDROCK_REGION = os.environ.get('BEDROCK_REGION', 'us-east-1')
AWS_REGION = os.environ.get('AWS_REGION', 'ap-south-2')

# Initialize clients
s3_helper = S3Helper()
dynamodb_helper = DynamoDBHelper(region=AWS_REGION)
bedrock_client = BedrockClient(region=BEDROCK_REGION)
bedrock_client.MODEL_ID = "amazon.nova-lite-v1:0"


MAX_TEXT_LENGTH = 5000

LEVEL_WORDS = {
    'high': ['high', 'urgent', 'उच्च', 'अधिक', 'ज्यादा', 'జాస్తి', 'అధిక', 'ఎక్కువ', 'உயர்', 'அதிக', 'উচ্চ', 'বেশি', 'ઉચ્ચ', 'ಹೆಚ್ಚು', 'ಉನ್ನತ', 'ഉയർന്ന', 'ਉੱਚ'],
    'low': ['low', 'निम्न', 'कम', 'తక్కువ', 'குறைந்த', 'நிம்ன', 'নিম্ন', 'কম', 'ઓછ', 'નિમ્ન', 'ಕಡಿಮೆ', 'കുറഞ്ഞ', 'ਘੱਟ'],
}
EMOTIONS = ['distressed', 'angry', 'confused', 'frustrated', 'calm']


def normalize_level(value: Any) -> str:
    """Map an urgency/severity value (possibly translated) to high/medium/low"""
    text = str(value or '').strip().lower()
    for level, words in LEVEL_WORDS.items():
        if any(word in text for word in words):
            return level
    return 'medium'


def normalize_emotion(value: Any) -> str:
    text = str(value or '').strip().lower()
    for emotion in EMOTIONS:
        if emotion in text:
            return emotion
    return 'distressed' if text else 'calm'


def error_response(status_code: int, message: str, error: str) -> Dict[str, Any]:
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
        },
        'body': json.dumps(APIResponse.error_response(message=message, error=error).dict(), ensure_ascii=False)
    }


def invoke_and_parse(prompt: str) -> Dict[str, Any]:
    """Call Bedrock and parse the JSON object in its answer"""
    result = bedrock_client.invoke_model(
        prompt=prompt,
        max_tokens=3000,
        temperature=0.5,
        system_prompt=SYSTEM_PROMPT
    )
    print(f"Bedrock response received. Length: {len(result['text'])} characters, usage: {result.get('usage', {})}")
    response_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', result['text']).strip()
    start_idx = response_text.find('{')
    end_idx = response_text.rfind('}')
    if start_idx == -1 or end_idx == -1:
        raise ValueError("No JSON object found in response")
    parsed = json.loads(response_text[start_idx:end_idx + 1])
    if not isinstance(parsed, dict) or not parsed.get('category'):
        raise ValueError("Response is missing a category")
    return parsed


SYSTEM_PROMPT = (
    "You are an expert Indian lawyer with 20+ years of experience. Give detailed, actionable legal advice: "
    "specific steps, where to file, costs, timelines and free resources, not just 'consult a lawyer'. "
    "Never return Other as category. If landlord issue use Tenant Rights. If employment use Labour Law. "
    "If overcharging use Consumer Rights. Cite the BNS, BNSS and BSA (2023) for criminal law, never the IPC or CrPC as current law. "
    "Respond in the language and script the prompt asks for."
)


def convert_floats_to_decimal(obj):
    """
    Recursively convert float values to Decimal for DynamoDB compatibility
    """
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: convert_floats_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimal(item) for item in obj]
    return obj


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for voice triage
    
    Args:
        event: API Gateway event with transcribed text
        context: Lambda context
        
    Returns:
        API Gateway response with triage results
    """
    try:
        # Parse request
        body = json.loads(event.get('body', '{}'))
        user_id = body.get('userId')
        session_id = body.get('sessionId', str(uuid.uuid4()))
        transcribed_text = body.get('transcribedText')
        language = body.get('language', 'hi')  # Default to Hindi
        use_native_script = body.get('useNativeScript', True)  # Default to native script
        
        # Validate required fields
        if not user_id or not transcribed_text:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key',
                    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
                },
                'body': json.dumps(APIResponse.error_response(
                    message="Missing required fields",
                    error="userId and transcribedText are required"
                ).dict(), ensure_ascii=False)
            }
        
        if len(transcribed_text) > MAX_TEXT_LENGTH:
            return error_response(400, "Text too long", f"Please keep the description under {MAX_TEXT_LENGTH} characters")
        
        # Classify the problem, urgency and emotional state in one Bedrock call
        try:
            classification_result = classify_legal_problem(transcribed_text, language, use_native_script)
        except Exception as e:
            print(f"Legal classification failed: {str(e)}")
            return error_response(502, "Analysis failed", "The AI could not analyse this issue. Please try again.")
        
        emotion_result = {
            'primary': classification_result['emotionalState'],
            'confidence': classification_result['confidence'],
            'urgency': classification_result['urgency'],
            'urgencyReason': classification_result.get('urgencyReason', '')
        }
        
        # Step 3: Skip TriageResult model creation to avoid enum validation issues
        # Claude returns specific categories like "Employment Law - Unpaid Wages"
        # which don't match the strict LegalCategory enum
        
        # Step 4: Store session data
        session = UserSession(
            session_id=session_id,
            user_id=user_id,
            document_id=None,
            conversation_history=[
                {
                    'role': 'user',
                    'content': transcribed_text,
                    'timestamp': datetime.utcnow().isoformat()
                }
            ],
            current_step='triage_complete',
            context={
                'classification_result': classification_result,
                'emotion': emotion_result,
                'language': language
            },
            preferred_language=language,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
            ttl=int((datetime.utcnow() + timedelta(days=90)).timestamp())
        )
        
        # Convert to dict and rename session_id to sessionId for DynamoDB
        session_dict = session.dict()
        session_dict['sessionId'] = session_dict.pop('session_id')
        session_dict['userId'] = session_dict.pop('user_id')
        session_dict['documentId'] = session_dict.pop('document_id')
        session_dict['conversationHistory'] = session_dict.pop('conversation_history')
        session_dict['currentStep'] = session_dict.pop('current_step')
        session_dict['preferredLanguage'] = session_dict.pop('preferred_language')
        session_dict['createdAt'] = session_dict.pop('created_at')
        session_dict['updatedAt'] = session_dict.pop('updated_at')
        
        # Add top-level fields for Case Memory to access
        session_dict['transcription'] = transcribed_text
        session_dict['fullTranscription'] = transcribed_text  # Add fullTranscription field
        session_dict['emotion'] = emotion_result
        session_dict['category'] = classification_result['category']  # Add category at top level
        session_dict['classification'] = {
            'category': classification_result['category'],
            'confidence': classification_result['confidence'],
            'relevantSections': classification_result['sections'],
            'severity': classification_result['severity']
        }
        session_dict['extractedFacts'] = classification_result['facts']
        session_dict['recommendation'] = classification_result.get('recommendation', '')
        session_dict['nextSteps'] = classification_result.get('nextSteps', [])
        session_dict['requiredDocuments'] = classification_result.get('requiredDocuments', [])
        session_dict['subCategory'] = classification_result.get('subCategory', '')
        session_dict['estimatedCost'] = classification_result.get('estimatedCost', '')
        session_dict['timeline'] = classification_result.get('timeline', '')
        session_dict['language'] = language
        session_dict['timestamp'] = datetime.utcnow().isoformat()
        
        dynamodb_helper.put_item(SESSION_TABLE, convert_floats_to_decimal(session_dict))
        
        # Step 5: Return response
        response_data = {
            'sessionId': session_id,
            'transcription': transcribed_text,
            'emotion': emotion_result,
            'classification': {
                'category': classification_result['category'],
                'subCategory': classification_result.get('subCategory', ''),
                'confidence': classification_result['confidence'],
                'relevantSections': classification_result['sections'],
                'severity': classification_result['severity']
            },
            'extractedFacts': classification_result['facts'],
            'recommendation': classification_result.get('recommendation', ''),
            'nextSteps': classification_result.get('nextSteps', []),
            'requiredDocuments': classification_result.get('requiredDocuments', []),
            'estimatedCost': classification_result.get('estimatedCost', ''),
            'timeline': classification_result.get('timeline', ''),
            'resources': classification_result.get('resources', []),
            'legalDisclaimer': classification_result.get('legalDisclaimer', 'This advice is AI-generated for informational purposes only. Please consult a qualified legal professional before taking any action. Laws may vary by state.'),
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key',
                'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
            },
            'body': json.dumps(APIResponse.success_response(
                message="Voice triage completed successfully",
                data=response_data
            ).dict(), ensure_ascii=False)
        }
        
    except Exception as e:
        print(f"Error in voice triage: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key',
                'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
            },
            'body': json.dumps(APIResponse.error_response(
                message="Internal server error",
                error="Something went wrong. Please try again."
            ).dict(), ensure_ascii=False)
        }


def classify_legal_problem(transcription: str, language: str, use_native_script: bool = True) -> Dict[str, Any]:
    """
    Classify legal problem using Bedrock
    
    Args:
        transcription: Transcribed text
        language: Language code
        use_native_script: If True, use native script; if False, use romanized text
        
    Returns:
        Dict with classification results including recommendations and next steps
    """
    print(f"=== CLASSIFY LEGAL PROBLEM ===")
    print(f"Language: {language}, Use Native Script: {use_native_script}")
    
    prompt = bedrock_client.build_legal_triage_prompt(transcription, language, use_native_script)
    
    print(f"Prompt length: {len(prompt)} characters")
    
    classification = None
    last_error = None
    for attempt in range(2):
        try:
            classification = invoke_and_parse(prompt)
            break
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            print(f"[JSON PARSE] Attempt {attempt + 1} failed: {str(e)}")
    if classification is None:
        raise ValueError(f"Could not parse model response: {last_error}")

    print(f"Parsed classification - Category: {classification.get('category', 'MISSING')}")
    print(f"Recommendation length: {len(classification.get('recommendation', ''))} characters")
    
    # Normalize fixed values (the model sometimes translates them)
    severity = normalize_level(classification.get('severity')).capitalize()
    urgency = normalize_level(classification.get('urgency'))
    emotional_state = normalize_emotion(classification.get('emotionalState'))
    
    # Extract legal sections with proper structure, correcting repealed IPC/CrPC citations
    legal_sections = classification.get('legalSections', [])
    sections_list = []
    for section in legal_sections if isinstance(legal_sections, list) else []:
        if isinstance(section, dict):
            sections_list.append(section)
        elif isinstance(section, str):
            sections_list.append({
                'act': '',
                'section': section,
                'description': ''
            })
    sections_list = fix_sections(sections_list)
    
    # Parse nextSteps - The model might return string instead of array
    next_steps = classification.get('nextSteps', [])
    if isinstance(next_steps, str):
        # Split by comma and clean up
        next_steps = [step.strip() for step in next_steps.split(',') if step.strip()]
    elif not isinstance(next_steps, list):
        next_steps = []
    
    # Parse requiredDocuments - The model might return string instead of array
    required_docs = classification.get('requiredDocuments', [])
    if isinstance(required_docs, str):
        # Split by comma and clean up
        required_docs = [doc.strip() for doc in required_docs.split(',') if doc.strip()]
    elif not isinstance(required_docs, list):
        required_docs = []
    
    # Parse resources - The model might return string instead of array
    resources = classification.get('resources', [])
    if isinstance(resources, str):
        # If it's a string, wrap it in a list
        resources = [{'name': 'Resource', 'action': resources, 'cost': '', 'timeline': ''}]
    elif not isinstance(resources, list):
        resources = []
    
    return {
        'facts': classification.get('facts', {}),
        'category': classification.get('category', 'Other'),
        'subCategory': classification.get('subCategory', ''),
        'sections': sections_list,
        'severity': severity,
        'urgency': urgency,
        'urgencyReason': classification.get('urgencyReason', ''),
        'emotionalState': emotional_state,
        'recommendation': classification.get('recommendation', ''),
        'nextSteps': next_steps,
        'requiredDocuments': required_docs,
        'estimatedCost': classification.get('estimatedCost', ''),
        'timeline': classification.get('timeline', ''),
        'resources': resources,
        'legalDisclaimer': classification.get('legalDisclaimer', 'This advice is AI-generated for informational purposes only. Please consult a qualified legal professional before taking any action. Laws may vary by state.'),
        'confidence': 0.85  # Default confidence
    }
    


# Override model ID
import bedrock_client as bc
bc.BedrockClient.MODEL_ID = "amazon.nova-lite-v1:0"
