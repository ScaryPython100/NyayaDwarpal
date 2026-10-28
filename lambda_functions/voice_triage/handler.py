"""
Voice Triage Lambda Handler

This Lambda function processes transcribed text from voice input,
detects emotion and urgency, and classifies the legal problem using AWS Bedrock.

Note: Audio recording and transcription (via Sarvam AI) is handled by the frontend.
This Lambda only receives the final transcribed text.
"""

import json
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
        
        # Step 1: Detect emotion and urgency using Bedrock
        emotion_result = detect_emotion_and_urgency(transcribed_text, language)
        
        # Step 2: Classify legal problem using Bedrock
        classification_result = classify_legal_problem(transcribed_text, language, use_native_script)
        
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
        session_dict['timestamp'] = datetime.utcnow().isoformat()
        
        dynamodb_helper.put_item(SESSION_TABLE, convert_floats_to_decimal(session_dict))
        
        # Step 5: Return response
        response_data = {
            'sessionId': session_id,
            'transcription': transcribed_text,
            'emotion': {
                'primary': classification_result.get('emotionalState', emotion_result['primary']),
                'confidence': emotion_result['confidence'],
                'urgency': classification_result.get('urgency', emotion_result['urgency']),
                'urgencyReason': classification_result.get('urgencyReason', '')
            },
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
                error=str(e)
            ).dict(), ensure_ascii=False)
        }


def detect_emotion_and_urgency(transcription: str, language: str) -> Dict[str, Any]:
    """
    Detect emotion and urgency from transcribed text using Bedrock
    
    Args:
        transcription: Transcribed text
        language: Language code
        
    Returns:
        Dict with emotion, confidence, and urgency
    """
    prompt = f"""Analyze the following text in {language} language and detect the emotional state and urgency level.

Text: {transcription}

Provide your analysis in JSON format with these keys:
- emotion: one of "distressed", "angry", "confused", "calm"
- confidence: a number between 0.0 and 1.0
- urgency: one of "high", "medium", "low"

Respond with only the JSON object, no additional text."""
    
    try:
        result = bedrock_client.invoke_model(
            prompt=prompt,
            max_tokens=200,
            temperature=0.3
        )
        
        # Parse JSON response
        response_text = result['text'].strip()
        # Remove markdown code blocks if present
        if response_text.startswith('```'):
            response_text = response_text.split('```')[1]
            if response_text.startswith('json'):
                response_text = response_text[4:]
        
        emotion_data = json.loads(response_text)
        
        # Normalize emotion to match enum values
        emotion = emotion_data.get('emotion', 'neutral')
        if emotion == 'neutral':
            emotion = 'calm'  # Map neutral to calm for enum compatibility
        
        return {
            'primary': emotion,
            'confidence': emotion_data.get('confidence', 0.5),
            'urgency': emotion_data.get('urgency', 'medium')
        }
        
    except Exception as e:
        print(f"Error in emotion detection: {str(e)}")
        return {
            'primary': 'calm',
            'confidence': 0.5,
            'urgency': 'medium'
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
    print(f"Calling Bedrock with transcription: {transcription[:100]}...")
    print(f"Language: {language}, Use Native Script: {use_native_script}")
    
    prompt = bedrock_client.build_legal_triage_prompt(transcription, language, use_native_script)
    
    print(f"Prompt length: {len(prompt)} characters")
    print(f"Prompt preview: {prompt[:500]}...")
    
    try:
        print("Invoking Bedrock model...")
        result = bedrock_client.invoke_model(
            prompt=prompt,
            max_tokens=3000,  # Increased for longer responses
            temperature=0.7,  # Increased from 0.3 for more detailed responses
            system_prompt="You are an expert Indian lawyer with 20+ years of experience. You MUST provide detailed, actionable legal advice. NEVER say consult a lawyer as generic advice. Always give specific steps, costs, timelines, and resources. NEVER return Other as category. If landlord issue use Tenant Rights. If employment use Labour Law. If overcharging use Consumer Rights. CRITICAL: Respond in the same language as the user input. Hindi input means Hindi Devanagari response."
        )
        
        print(f"Bedrock response received. Length: {len(result['text'])} characters")
        print(f"Token usage: {result.get('usage', {})}")
        
        # Parse JSON response with improved error handling
        response_text = result['text'].strip()
        import re
        # Strip markdown backticks
        if '```' in response_text:
            parts = response_text.split('```')
            for part in parts:
                p = part.strip().lstrip('json').strip()
                if p.startswith('{'):
                    response_text = p
                    break
        # Remove control characters
        response_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', response_text).strip()
        print(f"[BEDROCK RAW RESPONSE] First 500 chars: {response_text[:500]}...")
        
        # Try to parse JSON with multiple fallback strategies
        classification = None
        parse_attempts = []
        
        # Attempt 1: Direct parse
        try:
            classification = json.loads(response_text)
            print("[JSON PARSE] Success on direct parse")
        except json.JSONDecodeError as e:
            parse_attempts.append(f"Direct parse failed: {str(e)}")
            
            # Attempt 2: Remove markdown code blocks
            try:
                cleaned = response_text
                if cleaned.startswith('```'):
                    # Remove opening ```json or ```
                    cleaned = cleaned.split('```', 1)[1]
                    if cleaned.startswith('json'):
                        cleaned = cleaned[4:].strip()
                    # Remove closing ```
                    if '```' in cleaned:
                        cleaned = cleaned.rsplit('```', 1)[0].strip()
                
                classification = json.loads(cleaned)
                print("[JSON PARSE] Success after removing markdown")
            except json.JSONDecodeError as e:
                parse_attempts.append(f"Markdown removal failed: {str(e)}")
                
                # Attempt 3: Find JSON object boundaries
                try:
                    start_idx = response_text.find('{')
                    end_idx = response_text.rfind('}')
                    if start_idx != -1 and end_idx != -1:
                        json_str = response_text[start_idx:end_idx+1]
                        classification = json.loads(json_str)
                        print("[JSON PARSE] Success after extracting JSON boundaries")
                    else:
                        raise ValueError("No JSON object found in response")
                except (json.JSONDecodeError, ValueError) as e:
                    parse_attempts.append(f"Boundary extraction failed: {str(e)}")
                    print(f"[JSON PARSE ERROR] All attempts failed: {parse_attempts}")
                    raise json.JSONDecodeError(
                        f"Failed to parse JSON after {len(parse_attempts)} attempts",
                        response_text,
                        0
                    )
        print(f"Parsed classification - Category: {classification.get('category', 'MISSING')}")
        print(f"Recommendation length: {len(classification.get('recommendation', ''))} characters")
        
        # Normalize severity to match enum values (capitalize first letter)
        severity = classification.get('severity', 'medium')
        if isinstance(severity, str):
            severity = severity.capitalize() if severity else 'Medium'
        
        # Normalize urgency
        urgency = classification.get('urgency', 'medium')
        if isinstance(urgency, str):
            urgency = urgency.lower()
        
        # Extract legal sections with proper structure
        legal_sections = classification.get('legalSections', [])
        sections_list = []
        for section in legal_sections:
            if isinstance(section, dict):
                sections_list.append(section)
            elif isinstance(section, str):
                sections_list.append({
                    'act': 'Indian Law',
                    'section': section,
                    'description': ''
                })
        
        # Parse nextSteps - Groq might return string instead of array
        next_steps = classification.get('nextSteps', [])
        if isinstance(next_steps, str):
            # Split by comma and clean up
            next_steps = [step.strip() for step in next_steps.split(',') if step.strip()]
        elif not isinstance(next_steps, list):
            next_steps = []
        
        # Parse requiredDocuments - Groq might return string instead of array
        required_docs = classification.get('requiredDocuments', [])
        if isinstance(required_docs, str):
            # Split by comma and clean up
            required_docs = [doc.strip() for doc in required_docs.split(',') if doc.strip()]
        elif not isinstance(required_docs, list):
            required_docs = []
        
        # Parse resources - Groq might return string instead of array
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
            'emotionalState': classification.get('emotionalState', 'calm'),
            'recommendation': classification.get('recommendation', ''),
            'nextSteps': next_steps,
            'requiredDocuments': required_docs,
            'estimatedCost': classification.get('estimatedCost', ''),
            'timeline': classification.get('timeline', ''),
            'resources': resources,
            'legalDisclaimer': classification.get('legalDisclaimer', 'This advice is AI-generated for informational purposes only. Please consult a qualified legal professional before taking any action. Laws may vary by state.'),
            'confidence': 0.85  # Default confidence
        }
        
    except json.JSONDecodeError as e:
        print(f"JSON decode error in legal classification: {str(e)}")
        print(f"Response text: {response_text}")
        return {
            'facts': {},
            'category': 'Other',
            'subCategory': '',
            'sections': [],
            'severity': 'Medium',
            'urgency': 'medium',
            'urgencyReason': '',
            'emotionalState': 'calm',
            'recommendation': 'Please consult with a legal professional for detailed advice.',
            'nextSteps': [],
            'requiredDocuments': [],
            'estimatedCost': '',
            'timeline': '',
            'resources': [],
            'legalDisclaimer': 'This advice is AI-generated for informational purposes only. Please consult a qualified legal professional before taking any action. Laws may vary by state.',
            'confidence': 0.5
        }
    except Exception as e:
        print(f"Error in legal classification: {str(e)}")
        return {
            'facts': {},
            'category': 'Other',
            'subCategory': '',
            'sections': [],
            'severity': 'Medium',
            'urgency': 'medium',
            'urgencyReason': '',
            'emotionalState': 'calm',
            'recommendation': 'Please consult with a legal professional for detailed advice.',
            'nextSteps': [],
            'requiredDocuments': [],
            'estimatedCost': '',
            'timeline': '',
            'resources': [],
            'legalDisclaimer': 'This advice is AI-generated for informational purposes only. Please consult a qualified legal professional before taking any action. Laws may vary by state.',
            'confidence': 0.5
        }


# Override model ID
import bedrock_client as bc
bc.BedrockClient.MODEL_ID = "amazon.nova-lite-v1:0"
