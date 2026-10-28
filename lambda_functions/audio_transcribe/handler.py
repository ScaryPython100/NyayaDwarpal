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

SUPPORTED_LANGUAGES = {
    'unknown', 'en-IN', 'hi-IN', 'bn-IN', 'gu-IN', 'kn-IN', 'ml-IN', 'mr-IN', 'od-IN', 'pa-IN', 'ta-IN', 'te-IN'
}

# Browser recording format -> file name and type sent to Sarvam (Safari records mp4, Chrome/Firefox webm/ogg)
AUDIO_TYPES = {
    'audio/webm': ('recording.webm', 'audio/webm'),
    'audio/ogg': ('recording.ogg', 'audio/ogg'),
    'audio/mp4': ('recording.m4a', 'audio/mp4'),
    'audio/x-m4a': ('recording.m4a', 'audio/mp4'),
    'audio/aac': ('recording.aac', 'audio/aac'),
    'audio/mpeg': ('recording.mp3', 'audio/mpeg'),
    'audio/wav': ('recording.wav', 'audio/wav'),
}


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
        language_code = body.get('language_code') or 'unknown'
        if language_code not in SUPPORTED_LANGUAGES:
            language_code = 'unknown'  # let Sarvam detect the language
        filename, content_type = AUDIO_TYPES.get(
            (body.get('mime_type') or '').split(';')[0].strip().lower(),
            ('recording.webm', 'audio/webm')
        )
        
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
                'statusCode': 503,
                'headers': headers,
                'body': json.dumps({
                    'success': False,
                    'errorCode': 'service_unavailable',
                    'error': 'Voice input is not available right now. Please type your issue instead.'
                })
            }
        
        
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
            'file': (filename, audio_bytes, content_type)
        }
        
        data = {
            'model': 'saaras:v3',
            'mode': 'transcribe',
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
            logger.error(f"Sarvam AI error {response.status_code}: {response.text[:300]}")
            if response.status_code in (401, 403):
                error_code, message, status = 'service_unavailable', 'Voice input is not available right now. Please type your issue instead.', 503
            elif response.status_code == 429:
                error_code, message, status = 'busy', 'Too many people are using voice input. Please try again in a minute.', 503
            else:
                error_code, message, status = 'audio_invalid', 'We could not understand this recording. Please try again, speaking for less than 30 seconds.', 400
            return {
                'statusCode': status,
                'headers': headers,
                'body': json.dumps({
                    'success': False,
                    'errorCode': error_code,
                    'error': message
                })
            }
        
        # Parse Sarvam AI response
        sarvam_data = response.json()
        transcript = sarvam_data.get('transcript') or sarvam_data.get('text', '')
        
        logger.info(f"Transcript received: {len(transcript or '')} characters")
        
        if not transcript or transcript.strip() == '':
            logger.warning("No speech detected in audio")
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({
                    'success': False,
                    'errorCode': 'no_speech',
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
                    'language_code': sarvam_data.get('language_code') or language_code
                }
            }, ensure_ascii=False)
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
