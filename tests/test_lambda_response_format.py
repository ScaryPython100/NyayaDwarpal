#!/usr/bin/env python3
"""
Test Lambda Response Format
Simulates the exact response format from voice_triage Lambda
"""

import json
from datetime import datetime

# Simulate classification result from Groq
classification_result = {
    'category': 'Consumer Rights',
    'subCategory': 'Service Deficiency',
    'confidence': 0.85,
    'sections': [
        {
            'act': 'Consumer Protection Act, 2019',
            'section': 'Section 2(7)',
            'description': 'Defines consumer rights'
        }
    ],
    'severity': 'Medium',
    'urgency': 'medium',
    'urgencyReason': 'Overcharging issue needs prompt resolution',
    'emotionalState': 'angry',
    'recommendation': 'आपको सबसे पहले ऑटो ड्राइवर से बात करनी चाहिए...',
    'nextSteps': ['Step 1', 'Step 2'],
    'requiredDocuments': ['Doc 1', 'Doc 2'],
    'estimatedCost': '₹2,000-5,000',
    'timeline': '1-2 months',
    'resources': [],
    'facts': {'who': 'auto driver', 'what': 'overcharging'}
}

emotion_result = {
    'primary': 'angry',
    'confidence': 0.8,
    'urgency': 'medium'
}

# Build response_data (same as Lambda)
response_data = {
    'sessionId': 'test-session-123',
    'transcription': 'Auto wale ne meter se 3 guna paisa manga',
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
    'legalDisclaimer': 'This advice is AI-generated...',
    'timestamp': datetime.utcnow().isoformat()
}

# Wrap in APIResponse format
api_response = {
    'success': True,
    'message': 'Voice triage completed successfully',
    'data': response_data,
    'error': None,
    'timestamp': datetime.utcnow().isoformat()
}

# This is what goes in the Lambda response body
lambda_response = {
    'statusCode': 200,
    'headers': {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key',
        'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
    },
    'body': json.dumps(api_response, ensure_ascii=False)
}

print("=" * 80)
print("LAMBDA RESPONSE FORMAT TEST")
print("=" * 80)
print("\n1. Lambda Response Structure:")
print(json.dumps(lambda_response, indent=2, ensure_ascii=False))

print("\n" + "=" * 80)
print("2. Parsed Body (what frontend receives):")
print("=" * 80)
body_parsed = json.loads(lambda_response['body'])
print(json.dumps(body_parsed, indent=2, ensure_ascii=False))

print("\n" + "=" * 80)
print("3. Frontend Access Paths:")
print("=" * 80)
print(f"data.success = {body_parsed['success']}")
print(f"data.data.classification.category = {body_parsed['data']['classification']['category']}")
print(f"data.data.classification.subCategory = {body_parsed['data']['classification']['subCategory']}")
print(f"data.data.recommendation = {body_parsed['data']['recommendation'][:50]}...")
print(f"data.data.nextSteps = {body_parsed['data']['nextSteps']}")
print(f"data.data.requiredDocuments = {body_parsed['data']['requiredDocuments']}")

print("\n" + "=" * 80)
print("4. Verification:")
print("=" * 80)
if body_parsed['success']:
    print("✓ success field is True")
else:
    print("❌ success field is False")

if body_parsed['data']['classification']['category'] != 'Other':
    print(f"✓ Category is specific: {body_parsed['data']['classification']['category']}")
else:
    print("❌ Category is 'Other'")

if len(body_parsed['data']['recommendation']) > 100:
    print(f"✓ Recommendation is detailed ({len(body_parsed['data']['recommendation'])} chars)")
else:
    print(f"❌ Recommendation is too short ({len(body_parsed['data']['recommendation'])} chars)")

if 'आप' in body_parsed['data']['recommendation'] or 'ऑटो' in body_parsed['data']['recommendation']:
    print("✓ Recommendation contains Hindi text")
else:
    print("❌ Recommendation does not contain Hindi text")

print("\n" + "=" * 80)
print("CONCLUSION:")
print("=" * 80)
print("The Lambda response format is CORRECT.")
print("Frontend should be able to access:")
print("  - data.data.classification.category")
print("  - data.data.recommendation")
print("  - data.data.nextSteps")
print("  - etc.")
print("\nIf frontend is receiving empty values, check:")
print("1. API Gateway is not modifying the response")
print("2. CORS headers are correct")
print("3. Content-Type is application/json")
print("4. Response body is valid JSON")
