"""
Document Translation Lambda Handler

This Lambda function extracts text from vernacular documents using AWS Textract,
translates to English using Sarvam AI, and applies legal glossary mappings.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor
import os
import uuid
from datetime import datetime
from typing import Dict, Any, List
import boto3

# Import shared utilities (from Lambda layer)
import sys
sys.path.insert(0, '/opt/python')

from models import APIResponse, LegalGlossaryTerm
from aws_helpers import S3Helper, DynamoDBHelper, TextractHelper


# Environment variables
DOCUMENT_BUCKET = os.environ.get('DOCUMENT_BUCKET', 'nyaya-dwarpal-documents')
ARCHIVE_BUCKET = os.environ.get('ARCHIVE_BUCKET', 'nyaya-dwarpal-archive')
GLOSSARY_TABLE = os.environ.get('GLOSSARY_TABLE', 'NyayaDwarpal-LegalGlossary')
SARVAM_AI_ENDPOINT = os.environ.get('SARVAM_AI_ENDPOINT', 'https://api.sarvam.ai/v1')
SARVAM_AI_API_KEY = os.environ.get('SARVAM_AI_API_KEY', '')

# Initialize clients
s3_helper = S3Helper()
dynamodb_helper = DynamoDBHelper()


MAX_TRANSLATE_CHARS = 6000
MAX_CHUNK_SIZE = 900  # mayura:v1 limit is 1000 characters

SENTENCE_END = re.compile(r'(?<=[.!?।॥])\s+')


def split_into_chunks(text: str, limit: int = MAX_CHUNK_SIZE) -> List[str]:
    """Split text into pieces under `limit`, at line breaks, then sentence ends, then spaces"""
    pieces = []
    for line in text.split('\n'):
        if len(line) <= limit:
            pieces.append(line)
            continue
        for sentence in SENTENCE_END.split(line):
            while len(sentence) > limit:
                cut = sentence.rfind(' ', 0, limit)
                cut = cut if cut > limit // 2 else limit
                pieces.append(sentence[:cut])
                sentence = sentence[cut:].lstrip()
            pieces.append(sentence)

    chunks, current = [], ''
    for piece in pieces:
        candidate = f"{current}\n{piece}" if current else piece
        if len(candidate) <= limit:
            current = candidate
        else:
            if current.strip():
                chunks.append(current.strip())
            current = piece
    if current.strip():
        chunks.append(current.strip())
    return chunks

TRANSLATION_ERRORS = {
    'service_unavailable': (503, 'Translation is not available right now. Please try again later.'),
    'busy': (503, 'Too many people are translating right now. Please try again in a minute.'),
    'translation_failed': (502, 'We could not translate this document. Please try again.'),
    'no_text': (400, 'We could not find any text in this file. Try a clearer PDF or a .txt file.'),
}


class TranslationError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def extract_text_from_document(s3_key: str = None, bucket: str = None, file_content: str = None, filename: str = None) -> str:
    """
    Smart text extraction based on file type
    
    Args:
        s3_key: S3 object key (optional if file_content provided)
        bucket: S3 bucket name (optional if file_content provided)
        file_content: Base64 encoded file content (optional if s3_key provided)
        filename: Original filename (required if file_content provided)
        
    Returns:
        Extracted text content
    """
    if file_content:
        import base64
        print(f"Processing file content directly: {filename}")
        file_bytes = base64.b64decode(file_content)
        ext = os.path.splitext(filename)[1].lower() if filename else '.txt'
    else:
        ext = os.path.splitext(s3_key)[1].lower()
        s3_client = boto3.client('s3', region_name='ap-south-2')
        file_bytes = s3_client.get_object(Bucket=bucket, Key=s3_key)['Body'].read()

    if ext == '.txt':
        try:
            return file_bytes.decode('utf-8')
        except UnicodeDecodeError:
            return file_bytes.decode('utf-16') if file_bytes[:2] in (b'\xff\xfe', b'\xfe\xff') else file_bytes.decode('latin-1')
    if ext == '.pdf':
        return extract_pdf_text(file_bytes)
    raise TranslationError('no_text')


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Text layer first; Textract OCR (sent as bytes: it cannot read S3 in another region) for scanned pages"""
    from io import BytesIO
    import PyPDF2

    try:
        reader = PyPDF2.PdfReader(BytesIO(pdf_bytes))
        text = '\n'.join(page.extract_text() or '' for page in reader.pages)
        pages = len(reader.pages)
    except Exception as e:
        print(f"PDF text extraction failed: {str(e)}")
        text, pages = '', 1
    if len(text.strip()) >= 20:
        return text
    if pages > 1:
        raise TranslationError('no_text')
    textract = boto3.client('textract', region_name='ap-south-1')
    response = textract.detect_document_text(Document={'Bytes': pdf_bytes})
    return '\n'.join(block['Text'] for block in response.get('Blocks', []) if block.get('BlockType') == 'LINE')

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for document translation
    
    Args:
        event: API Gateway event with document upload
        context: Lambda context
        
    Returns:
        API Gateway response with translation results
    """
    try:
        # Parse request
        try:
            body = json.loads(event.get('body') or '{}')
        except json.JSONDecodeError:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'success': False, 'error': 'Invalid request'})
            }
        user_id = body.get('userId')
        session_id = body.get('sessionId')
        document_id = body.get('documentId', str(uuid.uuid4()))
        source_language = body.get('sourceLanguage') or 'auto'
        target_language = body.get('targetLanguage') or 'en'
        document_type = body.get('documentType', 'Other')
        s3_key = body.get('s3Key')
        file_content = body.get('fileContent')  # Base64 encoded file
        filename = body.get('filename')
        
        # Validate required fields (either s3Key OR fileContent+filename)
        if not user_id:
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
                    error="userId is required"
                ).dict())
            }
        
        if not s3_key and not (file_content and filename):
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
                    error="Either s3Key or (fileContent + filename) is required"
                ).dict())
            }
        
        # Step 1: Extract text using smart extraction
        print(f"Extracting text from document")
        if file_content:
            original_text = extract_text_from_document(
                file_content=file_content,
                filename=filename,
                bucket=DOCUMENT_BUCKET
            )
        else:
            original_text = extract_text_from_document(
                s3_key=s3_key,
                bucket=DOCUMENT_BUCKET
            )
        
        if not original_text or not original_text.strip():
            raise TranslationError('no_text')
        original_text = original_text.strip()
        truncated = len(original_text) > MAX_TRANSLATE_CHARS
        if truncated:
            original_text = original_text[:MAX_TRANSLATE_CHARS]
        
        # Step 2: Identify legal terms in the text
        print(f"Identifying legal terms in {source_language}")
        legal_terms = identify_legal_terms(original_text, source_language)
        
        # Step 3: Query legal glossary for mappings
        print(f"Querying glossary for {len(legal_terms)} terms")
        glossary_mappings = query_legal_glossary(legal_terms, source_language)
        
        # Step 4: Translate text using Sarvam AI
        print(f"Translating document from {source_language} to {target_language}")
        translated_text = translate_text(
            text=original_text,
            source_language=source_language,
            target_language=target_language,
            glossary_mappings=glossary_mappings
        )
        
        # Step 5: Identify unmapped terms that need review
        unmapped_terms = [
            term for term in legal_terms
            if term not in [m['originalTerm'] for m in glossary_mappings]
        ]
        
        # Step 6: Generate translated document and store in S3
        translated_s3_key = f"translated/{document_id}.txt"
        s3_helper.upload_file(
            file_content=translated_text.encode('utf-8'),
            bucket=ARCHIVE_BUCKET,
            key=translated_s3_key,
            content_type='text/plain'
        )
        
        # Step 7: Return response
        response_data = {
            'sessionId': session_id,
            'documentId': document_id,
            'originalText': original_text,
            'translatedText': translated_text,
            'truncated': truncated,
            'sourceLanguage': source_language,
            'targetLanguage': target_language,
            'glossaryMappings': glossary_mappings,
            'unmappedTerms': [
                {
                    'term': term,
                    'literalTranslation': '',  # Would need another API call
                    'needsReview': True
                }
                for term in unmapped_terms
            ],
            'translatedDocumentS3Key': translated_s3_key,
            'downloadUrl': s3_helper.generate_presigned_url(
                bucket=ARCHIVE_BUCKET,
                key=translated_s3_key,
                expiration=3600
            ),
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
                message="Document translation completed successfully",
                data=response_data
            ).dict())
        }
        
    except TranslationError as e:
        status, message = TRANSLATION_ERRORS.get(e.code, TRANSLATION_ERRORS['translation_failed'])
        return {
            'statusCode': status,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'success': False,
                'message': 'Translation failed',
                'data': None,
                'errorCode': e.code,
                'error': message,
                'timestamp': datetime.utcnow().isoformat()
            })
        }
    except Exception as e:
        print(f"Error in document translation: {str(e)}")
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
                message="Internal server error",
                error="Something went wrong while translating. Please try again."
            ).dict())
        }


def identify_legal_terms(text: str, language: str) -> List[str]:
    """
    Identify potential legal terms in the text
    
    Args:
        text: Original text
        language: Language code
        
    Returns:
        List of identified legal terms
    """
    # Common legal terms in various Indian languages
    # This is a simplified version - in production, use NLP or Bedrock
    common_legal_terms = {
        'hi': ['खाता', 'पंचनामा', 'वादी', 'प्रतिवादी', 'न्यायालय', 'अधिवक्ता'],
        'ta': ['கட்டா', 'பஞ்சநாமா', 'வாதி', 'பிரதிவாதி'],
        'kn': ['ಖಾತಾ', 'ಪಂಚನಾಮಾ', 'ವಾದಿ', 'ಪ್ರತಿವಾದಿ'],
        'te': ['ఖాతా', 'పంచనామా', 'వాది', 'ప్రతివాది'],
        'ml': ['ഖാത', 'പഞ്ചനാമ', 'വാദി', 'പ്രതിവാദി'],
    }
    
    if language in common_legal_terms:
        terms = common_legal_terms[language]
    else:
        terms = [term for language_terms in common_legal_terms.values() for term in language_terms]
    identified = []
    
    for term in terms:
        if term in text:
            identified.append(term)
    
    return identified


def query_legal_glossary(terms: List[str], language: str) -> List[Dict[str, Any]]:
    """
    Query legal glossary for term mappings
    
    Args:
        terms: List of legal terms
        language: Language code
        
    Returns:
        List of glossary mappings
    """
    mappings = []
    
    for term in terms:
        try:
            # Query DynamoDB for glossary entry
            item = dynamodb_helper.get_item(
                table_name=GLOSSARY_TABLE,
                key={'term': term, 'language': language}
            )
            
            if item:
                mappings.append({
                    'originalTerm': term,
                    'translatedTerm': item.get('english_equivalent', ''),
                    'context': item.get('definition', ''),
                    'confidence': 1.0
                })
        except Exception as e:
            print(f"Error querying glossary for term '{term}': {str(e)}")
    
    return mappings


def translate_text(
    text: str,
    source_language: str,
    target_language: str,
    glossary_mappings: List[Dict[str, Any]]
) -> str:
    """
    Translate text using Sarvam AI with glossary mappings
    
    Args:
        text: Text to translate
        source_language: Source language code (e.g., 'en', 'hi')
        target_language: Target language code (e.g., 'en', 'hi')
        glossary_mappings: Legal glossary mappings
        
    Returns:
        Translated text
    """
    import requests
    
    if not SARVAM_AI_API_KEY:
        raise TranslationError('service_unavailable')

    try:
        # First, replace legal terms with placeholders (glossary holds English equivalents)
        placeholder_map = {}
        modified_text = text
        
        for i, mapping in enumerate(glossary_mappings if target_language == 'en' else []):
            placeholder = f"__LEGAL_TERM_{i}__"
            modified_text = modified_text.replace(
                mapping['originalTerm'],
                placeholder
            )
            placeholder_map[placeholder] = mapping['translatedTerm']
        
        # Map language codes to Sarvam AI format (e.g., 'hi' -> 'hi-IN')
        language_map = {
            'en': 'en-IN',
            'hi': 'hi-IN',
            'ta': 'ta-IN',
            'te': 'te-IN',
            'kn': 'kn-IN',
            'ml': 'ml-IN',
            'mr': 'mr-IN',
            'gu': 'gu-IN',
            'bn': 'bn-IN',
            'pa': 'pa-IN'
        }
        
        source_lang_code = language_map.get(source_language, 'auto')
        target_lang_code = language_map.get(target_language, 'en-IN')
        if source_lang_code == target_lang_code:
            source_lang_code = 'auto'
        
        # Prepare headers for Sarvam AI
        headers = {
            'api-subscription-key': SARVAM_AI_API_KEY,
            'Content-Type': 'application/json'
        }
        
        # mayura:v1 accepts at most 1000 characters per request
        chunks = split_into_chunks(modified_text, MAX_CHUNK_SIZE)
        
        print(f"Translating {len(chunks)} chunk(s) from {source_lang_code} -> {target_lang_code}")
        
        def translate_chunk(chunk: str) -> str:
            payload = {
                'input': chunk,
                'source_language_code': source_lang_code,
                'target_language_code': target_lang_code,
                'model': 'mayura:v1',
                'mode': 'formal'
            }
            response = requests.post(
                f'{SARVAM_AI_ENDPOINT}/translate',
                headers=headers,
                json=payload,
                timeout=20
            )
            if response.status_code == 200:
                return response.json().get('translated_text', '')
            print(f"Sarvam AI translation error: {response.status_code} - {response.text[:300]}")
            if response.status_code in (401, 403):
                raise TranslationError('service_unavailable')
            if response.status_code == 429:
                raise TranslationError('busy')
            raise TranslationError('translation_failed')

        # Translate chunks in parallel so long documents finish within the API time limit
        with ThreadPoolExecutor(max_workers=3) as pool:
            translated_chunks = list(pool.map(translate_chunk, chunks))
        
        # Combine translated chunks
        translated = '\n'.join(translated_chunks)
        
        # Replace placeholders with glossary terms
        for placeholder, legal_term in placeholder_map.items():
            translated = translated.replace(placeholder, legal_term)
        
        return translated
            
    except TranslationError:
        raise
    except Exception as e:
        print(f"Error in translation: {str(e)}")
        raise TranslationError('translation_failed')
