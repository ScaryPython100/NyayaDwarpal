"""
Document Translation Lambda Handler

This Lambda function extracts text from vernacular documents using AWS Textract,
translates to English using Sarvam AI, and applies legal glossary mappings.
"""

import json
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
    # If file content is provided directly (base64), decode and process
    if file_content:
        import base64
        print(f"Processing file content directly: {filename}")
        
        # Decode base64 content
        file_bytes = base64.b64decode(file_content)
        
        # Determine file type from filename
        ext = os.path.splitext(filename)[1].lower() if filename else '.txt'
        
        if ext == '.txt':
            # Decode text directly
            return file_bytes.decode('utf-8')
        else:
            # For PDFs, we need to upload to S3 temporarily for Textract
            # (Textract requires S3 location)
            temp_key = f"temp/{uuid.uuid4()}{ext}"
            s3_helper.upload_file(
                file_content=file_bytes,
                bucket=bucket or DOCUMENT_BUCKET,
                key=temp_key,
                content_type='application/pdf' if ext == '.pdf' else 'image/jpeg'
            )
            
            # Use Textract
            textract_helper = TextractHelper(region='ap-south-1')
            textract_response = textract_helper.analyze_document(
                bucket=bucket or DOCUMENT_BUCKET,
                key=temp_key,
                feature_types=['FORMS', 'TABLES']
            )
            
            # Clean up temp file
            try:
                s3_client = boto3.client('s3', region_name='ap-south-2')
                s3_client.delete_object(Bucket=bucket or DOCUMENT_BUCKET, Key=temp_key)
            except:
                pass
            
            return textract_helper.extract_text(textract_response)
    
    # Otherwise, read from S3
    ext = os.path.splitext(s3_key)[1].lower()
    
    if ext == '.txt':
        # Read text files directly from S3 (no Textract needed)
        print(f"Reading .txt file directly from S3 in ap-south-2")
        s3_client = boto3.client('s3', region_name='ap-south-2')
        response = s3_client.get_object(Bucket=bucket, Key=s3_key)
        return response['Body'].read().decode('utf-8')
    else:
        # Use Textract for PDFs and images (cross-region to ap-south-1)
        print(f"Using Textract in ap-south-1 for {ext} file")
        textract_helper = TextractHelper(region='ap-south-1')
        textract_response = textract_helper.analyze_document(
            bucket=bucket,
            key=s3_key,
            feature_types=['FORMS', 'TABLES']
        )
        return textract_helper.extract_text(textract_response)


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
        body = json.loads(event.get('body', '{}'))
        user_id = body.get('userId')
        session_id = body.get('sessionId')
        document_id = body.get('documentId', str(uuid.uuid4()))
        source_language = body.get('sourceLanguage', 'hi')
        target_language = body.get('targetLanguage', 'en')
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
        
        if not original_text:
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key',
                    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
                },
                'body': json.dumps(APIResponse.error_response(
                    message="Text extraction failed",
                    error="Unable to extract text from document"
                ).dict())
            }
        
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
        
        if not translated_text:
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key',
                    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
                },
                'body': json.dumps(APIResponse.error_response(
                    message="Translation failed",
                    error="Unable to translate document"
                ).dict())
            }
        
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
            'originalText': original_text[:500] + '...' if len(original_text) > 500 else original_text,
            'translatedText': translated_text[:500] + '...' if len(translated_text) > 500 else translated_text,
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
                error=str(e)
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
    
    terms = common_legal_terms.get(language, [])
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
    
    try:
        # First, replace legal terms with placeholders
        placeholder_map = {}
        modified_text = text
        
        for i, mapping in enumerate(glossary_mappings):
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
        target_lang_code = language_map.get(target_language, 'hi-IN')
        
        # Prepare headers for Sarvam AI
        headers = {
            'api-subscription-key': SARVAM_AI_API_KEY,
            'Content-Type': 'application/json'
        }
        
        # Chunk text if it exceeds 1000 characters (mayura:v1 limit)
        MAX_CHUNK_SIZE = 900  # Leave some buffer
        chunks = []
        
        if len(modified_text) <= MAX_CHUNK_SIZE:
            chunks = [modified_text]
        else:
            # Split by sentences to avoid breaking mid-sentence
            sentences = modified_text.replace('\n\n', '\n').split('\n')
            current_chunk = ""
            
            for sentence in sentences:
                if len(current_chunk) + len(sentence) + 1 <= MAX_CHUNK_SIZE:
                    current_chunk += sentence + "\n"
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = sentence + "\n"
            
            if current_chunk:
                chunks.append(current_chunk.strip())
        
        print(f"Translating {len(chunks)} chunk(s) from {source_lang_code} -> {target_lang_code}")
        
        # Translate each chunk
        translated_chunks = []
        for i, chunk in enumerate(chunks):
            print(f"Translating chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")
            
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
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                translated_chunks.append(result.get('translated_text', ''))
            else:
                print(f"Sarvam AI translation error for chunk {i+1}: {response.status_code} - {response.text}")
                return None
        
        # Combine translated chunks
        translated = '\n'.join(translated_chunks)
        
        # Replace placeholders with glossary terms
        for placeholder, legal_term in placeholder_map.items():
            translated = translated.replace(placeholder, legal_term)
        
        return translated
            
    except Exception as e:
        print(f"Error in translation: {str(e)}")
        return None
