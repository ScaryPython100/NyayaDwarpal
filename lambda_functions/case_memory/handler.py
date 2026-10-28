"""
Case Memory Lambda Handler

This Lambda function retrieves user case history from DynamoDB session table.
"""

import json
import os
from datetime import datetime
from typing import Dict, Any, List
from decimal import Decimal
import boto3

# Import shared utilities (from Lambda layer)
import sys
sys.path.insert(0, '/opt/python')

from models import APIResponse


# Environment variables
SESSION_TABLE = os.environ.get('SESSION_TABLE', 'NyayaDwarpal-Sessions')

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
        user_id = query_params.get('userId', 'all')
        limit = int(query_params.get('limit', '50'))
        
        print(f"Fetching cases for userId: {user_id}, limit: {limit}")
        
        # Get session table
        table = dynamodb.Table(SESSION_TABLE)
        
        # Scan table (since userId is not a key, we need to scan)
        # In production, you should add a GSI on userId for better performance
        if user_id and user_id != 'all':
            # Scan with filter expression
            response = table.scan(
                FilterExpression='userId = :uid',
                ExpressionAttributeValues={':uid': user_id},
                Limit=limit
            )
        else:
            # Scan all
            response = table.scan(Limit=limit)
        
        items = response.get('Items', [])
        
        # Convert Decimal types to float
        items = decimal_to_float(items)
        
        # Transform items to case format
        cases = []
        for item in items:
            case = {
                'caseId': item.get('sessionId', 'unknown'),
                'userId': item.get('userId', 'unknown'),
                'date': item.get('timestamp', datetime.utcnow().isoformat()),
                'emotion': {
                    'primary': item.get('emotion', {}).get('primary', 'calm'),
                    'urgency': item.get('emotion', {}).get('urgency', 'medium'),
                    'confidence': item.get('emotion', {}).get('confidence', 0.5)
                },
                'category': item.get('category', item.get('classification', {}).get('category', 'Other')),
                'issueSummary': item.get('transcription', 'No description available')[:100] + '...',
                'fullTranscription': item.get('fullTranscription', item.get('transcription', '')),
                'relevantSections': item.get('classification', {}).get('relevantSections', []),
                'extractedFacts': item.get('extractedFacts', {}),
                'recommendation': item.get('recommendation', ''),
                'nextSteps': item.get('nextSteps', []),
                'requiredDocuments': item.get('requiredDocuments', [])
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
            ).dict())
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
                error=str(e)
            ).dict())
        }
