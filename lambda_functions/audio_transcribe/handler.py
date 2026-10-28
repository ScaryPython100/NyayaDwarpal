import json
import os
import base64
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Try to import requests, provide helpful error if missing
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logger.error("requests library not available - Lambda layer may be missing")

def lambda_handler(event, context):
    """
    Lambda function to transcribe audio using Sarvam AI
    Receives base64 encoded audio and returns transcript
    """
    
    # CORS headers
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key',
        'Access-Control-Allow-Methods': 'POST,OPTIONS',
        'Content-Type': 'application/json'
    }
    
    # Handle OPTIONS request for CORS
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({'message': 'CORS preflight'})
        }
    
    # Log the incoming event for debugging
    logger.info(f"Received event: {json.dumps(event)}")
    
    # Check if requests library is available
    if not REQUESTS_AVAILABLE:
        logger.error("requests library not available")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({
                'success': False,
                'error': 'Server configuration error: requests library not available'
            })
        }
    
    try:
        # Parse request body
        body_str = event.get('body', '{}')
        logger.info(f"Request body: {body_str[:200]}...")  # Log first 200 chars
        
        body = json.loads(body_str)
        audio_base64 = body.get('audio')
        language_code = body.get('language_code', 'en-IN')
        
        logger.info(f"Language code: {language_code}")
        logger.info(f"Audio data length: {len(audio_base64) if audio_base64 else 0}")
        
        if not audio_base64:
            logger.warning("No audio data provided in request")
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({
                    'success': False,
                    'error': 'Missing audio data'
                })
            }
        
        # Get Sarvam API key from environment variable
        sarvam_api_key = os.environ.get('SARVAM_API_KEY')
        if not sarvam_api_key:
            logger.error("SARVAM_API_KEY environment variable not set")
            return {
                'statusCode': 500,
                'headers': headers,
                'body': json.dumps({
                    'success': False,
                    'error': 'Sarvam API key not configured'
                })
            }
        
        logger.info(f"Sarvam API key found: {sarvam_api_key[:10]}...")
        
        # Decode base64 audio
        try:
            audio_bytes = base64.b64decode(audio_base64)
            logger.info(f"Decoded audio size: {len(audio_bytes)} bytes")
        except Exception as e:
            logger.error(f"Base64 decode error: {str(e)}")
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({
                    'success': False,
                    'error': f'Invalid base64 audio data: {str(e)}'
                })
            }
        
        # Call Sarvam AI speech-to-text API
        sarvam_url = 'https://api.sarvam.ai/speech-to-text'
        
        # Prepare multipart form data
        files = {
            'file': ('recording.webm', audio_bytes, 'audio/webm')
        }
        
        data = {
            'model': 'saaras:v3',
            'language_code': language_code
        }
        
        sarvam_headers = {
            'api-subscription-key': sarvam_api_key
        }
        
        logger.info(f"Calling Sarvam AI with audio size: {len(audio_bytes)} bytes")
        
        # Make request to Sarvam AI
        try:
            response = requests.post(
                sarvam_url,
                headers=sarvam_headers,
                files=files,
                data=data,
                timeout=30
            )
            logger.info(f"Sarvam AI response status: {response.status_code}")
            logger.info(f"Sarvam AI response: {response.text[:500]}")
        except requests.exceptions.Timeout:
            logger.error("Sarvam AI request timeout")
            return {
                'statusCode': 504,
                'headers': headers,
                'body': json.dumps({
                    'success': False,
                    'error': 'Transcription request timeout'
                })
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Sarvam AI request error: {str(e)}")
            return {
                'statusCode': 502,
                'headers': headers,
                'body': json.dumps({
                    'success': False,
                    'error': f'Transcription service error: {str(e)}'
                })
            }
        
        if response.status_code != 200:
            error_text = response.text
            logger.error(f"Sarvam AI error: {error_text}")
            return {
                'statusCode': response.status_code,
                'headers': headers,
                'body': json.dumps({
                    'success': False,
                    'error': f'Sarvam AI transcription failed: {error_text}'
                })
            }
        
        # Parse Sarvam AI response
        sarvam_data = response.json()
        transcript = sarvam_data.get('transcript') or sarvam_data.get('text', '')
        
        logger.info(f"Transcript received: {transcript[:100] if transcript else 'EMPTY'}...")
        
        if not transcript or transcript.strip() == '':
            logger.warning("No speech detected in audio")
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({
                    'success': False,
                    'error': 'No speech detected in audio'
                })
            }
        
        # Return successful response
        logger.info("Transcription successful")
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({
                'success': True,
                'data': {
                    'transcript': transcript,
                    'language_code': language_code
                }
            })
        }
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}")
        return {
            'statusCode': 400,
            'headers': headers,
            'body': json.dumps({
                'success': False,
                'error': f'Invalid JSON in request body: {str(e)}'
            })
        }
        
    except requests.exceptions.Timeout:
        logger.error("Sarvam AI request timeout")
        return {
            'statusCode': 504,
            'headers': headers,
            'body': json.dumps({
                'success': False,
                'error': 'Transcription request timeout'
            })
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Sarvam AI request error: {str(e)}")
        return {
            'statusCode': 502,
            'headers': headers,
            'body': json.dumps({
                'success': False,
                'error': f'Transcription service error: {str(e)}'
            })
        }
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({
                'success': False,
                'error': f'Internal server error: {str(e)}'
            })
        }
