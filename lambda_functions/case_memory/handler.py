"""
Case Memory Lambda Handler

This Lambda function retrieves user case history from DynamoDB session table.
"""

import json
import re
import os
from datetime import datetime
from typing import Dict, Any, List
from decimal import Decimal
import boto3
from boto3.dynamodb.conditions import Key

# Import shared utilities (from Lambda layer)
import sys
sys.path.insert(0, '/opt/python')

from models import APIResponse


# Environment variables
SESSION_TABLE = os.environ.get('SESSION_TABLE', 'NyayaDwarpal-Sessions')
USER_INDEX = 'UserIdIndex'
MAX_LIMIT = 50
USER_ID_PATTERN = re.compile(r'^user-[A-Za-z0-9-]{6,64}$')

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb', region_name='ap-south-2')


def decimal_to_float(obj):
    """Convert Decimal objects to float for JSON serialization"""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float(item) for item in obj]
    return obj


def summarize(text: str, length: int = 100) -> str:
    text = (text or '').strip()
    if not text:
        return 'No description available'
    return text if len(text) <= length else text[:length].rstrip() + '...'


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for fetching case memory
    
    Args:
        event: API Gateway event
        context: Lambda context
        
    Returns:
        API Gateway response with case history
    """
    try:
        # Parse query parameters
        query_params = event.get('queryStringParameters', {}) or {}
        user_id = (query_params.get('userId') or '').strip()
        try:
            limit = max(1, min(int(query_params.get('limit', MAX_LIMIT)), MAX_LIMIT))
        except ValueError:
            limit = MAX_LIMIT
        
        # Only ever return one user's own cases
        if not USER_ID_PATTERN.match(user_id):
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key',
                    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
                },
                'body': json.dumps(APIResponse.error_response(
                    message="Invalid userId",
                    error="A valid userId is required"
                ).dict())
            }
        
        table = dynamodb.Table(SESSION_TABLE)
        
        # Newest first, from the userId index
        response = table.query(
            IndexName=USER_INDEX,
            KeyConditionExpression=Key('userId').eq(user_id),
            ScanIndexForward=False,
            Limit=limit
        )
        
        items = response.get('Items', [])
        
        # Convert Decimal types to float
        items = decimal_to_float(items)
        
        # Transform items to case format
        cases = []
        for item in items:
            case = {
                'caseId': item.get('sessionId', 'unknown'),
                'date': item.get('timestamp', datetime.utcnow().isoformat()),
                'emotion': {
                    'primary': item.get('emotion', {}).get('primary', 'calm'),
                    'urgency': item.get('emotion', {}).get('urgency', 'medium'),
                    'confidence': item.get('emotion', {}).get('confidence', 0.5)
                },
                'category': item.get('category', item.get('classification', {}).get('category', 'Other')),
                'issueSummary': summarize(item.get('transcription', '')),
                'fullTranscription': item.get('fullTranscription', item.get('transcription', '')),
                'relevantSections': item.get('classification', {}).get('relevantSections', []),
                'extractedFacts': item.get('extractedFacts', {}),
                'recommendation': item.get('recommendation', ''),
                'nextSteps': item.get('nextSteps', []),
                'requiredDocuments': item.get('requiredDocuments', []),
                'subCategory': item.get('subCategory', ''),
                'severity': item.get('classification', {}).get('severity', ''),
                'language': item.get('language', '')
            }
            cases.append(case)
        
        # Sort by date (most recent first)
        cases.sort(key=lambda x: x['date'], reverse=True)
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key',
                'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
            },
            'body': json.dumps(APIResponse.success_response(
                message=f"Retrieved {len(cases)} cases successfully",
                data={
                    'cases': cases,
                    'count': len(cases),
                    'userId': user_id
                }
            ).dict(), ensure_ascii=False)
        }
        
    except Exception as e:
        print(f"Error fetching cases: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key',
                'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
            },
            'body': json.dumps(APIResponse.error_response(
                message="Failed to fetch cases",
                error="Could not load your cases. Please try again."
            ).dict())
        }
