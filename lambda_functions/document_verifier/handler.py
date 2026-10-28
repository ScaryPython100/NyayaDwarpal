"""
Document Verifier Lambda Handler

This Lambda function verifies legal documents for common errors:
- Missing signatures
- Name mismatches
- Incorrect dates
- Spelling mistakes
- Other legal document issues
"""

import json
import base64
import boto3
import os
import sys
from typing import Dict, Any, List
from io import BytesIO

# Import shared utilities (from Lambda layer)
sys.path.insert(0, '/opt/python')

from bedrock_client import BedrockClient

# Initialize Bedrock client
bedrock_client = BedrockClient()


MAX_VERIFY_CHARS = 8000
TEXTRACT_REGION = 'ap-south-1'


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for document verification
    
    Args:
        event: API Gateway event with base64-encoded document
        context: Lambda context
        
    Returns:
        API Gateway response with verification results
    """
    try:
        # Parse request
        body = json.loads(event.get('body', '{}'))
        document_base64 = body.get('document')
        file_type = body.get('fileType', '').lower()
        file_name = body.get('fileName', 'document')
        
        # Validate required fields
        if not document_base64 or not file_type:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type',
                    'Access-Control-Allow-Methods': 'POST,OPTIONS'
                },
                'body': json.dumps({
                    'success': False,
                    'error': 'Missing required fields: document and fileType'
                }, ensure_ascii=False)
            }
        
        # Decode document
        try:
            document_bytes = base64.b64decode(document_base64)
        except Exception as e:
            return error_response('The file could not be read. Please upload it again.', status_code=400)
        
        # Extract text based on file type
        extracted_text = extract_text(document_bytes, file_type, file_name)
        
        if not extracted_text or len(extracted_text.strip()) < 10:
            return error_response('We could not find enough text in this file. Try a clearer photo, a PDF with selectable text, or a .txt file.', status_code=400)
        
        # Verify document using Bedrock
        verification_result = verify_document(extracted_text, file_name)
        
        # Return response
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'POST,OPTIONS'
            },
            'body': json.dumps({
                'success': True,
                'data': verification_result
            }, ensure_ascii=False)
        }
        
    except Exception as e:
        print(f"Error in document verification: {str(e)}")
        if isinstance(e, ValueError):
            return error_response(str(e), status_code=400)
        return error_response('We could not check this document. Please try again.')


def extract_text(document_bytes: bytes, file_type: str, file_name: str) -> str:
    """
    Extract text from document based on file type
    
    Args:
        document_bytes: Document content as bytes
        file_type: File type (pdf, docx, jpg, png, txt, etc.)
        file_name: Original file name
        
    Returns:
        Extracted text
    """
    try:
        if file_type == 'txt' or file_name.endswith('.txt'):
            return extract_text_from_txt(document_bytes)
        elif file_type == 'pdf' or file_name.endswith('.pdf'):
            return extract_text_from_pdf(document_bytes)
        elif file_type == 'doc' or file_name.lower().endswith('.doc'):
            raise ValueError('Old .doc files are not supported. Please save the file as .docx or PDF and upload again.')
        elif file_type == 'docx' or file_name.lower().endswith('.docx'):
            return extract_text_from_docx(document_bytes)
        elif file_type in ['jpg', 'jpeg', 'png'] or file_name.lower().endswith(('.jpg', '.jpeg', '.png')):
            return extract_text_from_image(document_bytes)
        else:
            raise ValueError(f'Unsupported file type: {file_type}')
    except Exception as e:
        print(f"Error extracting text: {str(e)}")
        raise


def extract_text_from_txt(txt_bytes: bytes) -> str:
    """Extract text from TXT file by decoding UTF-8"""
    try:
        # Try UTF-8 first
        text = txt_bytes.decode('utf-8')
        return text
    except UnicodeDecodeError:
        # Fallback to latin-1 if UTF-8 fails
        try:
            text = txt_bytes.decode('latin-1')
            return text
        except Exception as e:
            print(f"Error decoding TXT file: {str(e)}")
            raise ValueError(f'Failed to decode text file: {str(e)}')


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF using PyPDF2"""
    try:
        import PyPDF2
        pdf_file = BytesIO(pdf_bytes)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        
        text = '\n'.join(page.extract_text() or '' for page in pdf_reader.pages)
        if len(text.strip()) >= 20:
            return text
        # Scanned PDF with no text layer: read it with Textract (single-page PDFs)
        if len(pdf_reader.pages) > 1:
            raise ValueError('This looks like a scanned PDF with several pages. Please upload a photo of each page, or a PDF with selectable text.')
        return extract_text_with_textract(pdf_bytes)
    except Exception as e:
        print(f"Error extracting PDF text: {str(e)}")
        raise ValueError(f'Failed to extract text from PDF: {str(e)}')


def extract_text_from_docx(docx_bytes: bytes) -> str:
    """Extract text from DOCX using python-docx"""
    try:
        import docx
        docx_file = BytesIO(docx_bytes)
        doc = docx.Document(docx_file)
        
        text = []
        for paragraph in doc.paragraphs:
            text.append(paragraph.text)
        
        return '\n'.join(text)
    except Exception as e:
        print(f"Error extracting DOCX text: {str(e)}")
        raise ValueError(f'Failed to extract text from DOCX: {str(e)}')


def extract_text_with_textract(document_bytes: bytes) -> str:
    """OCR with AWS Textract (JPEG, PNG or single-page PDF, up to 5 MB)"""
    textract = boto3.client('textract', region_name=TEXTRACT_REGION)
    response = textract.detect_document_text(Document={'Bytes': document_bytes})
    lines = [block['Text'] for block in response.get('Blocks', []) if block.get('BlockType') == 'LINE']
    return '\n'.join(lines)


def extract_text_from_image(image_bytes: bytes) -> str:
    """Extract text from a photo or scan (JPEG/PNG) with AWS Textract"""
    try:
        return extract_text_with_textract(image_bytes)
    except Exception as e:
        print(f"Error extracting image text: {str(e)}")
        raise ValueError(f'Failed to extract text from image: {str(e)}')


def verify_document(text: str, file_name: str) -> Dict[str, Any]:
    """
    Verify document for common legal document errors using Bedrock
    
    Args:
        text: Extracted document text
        file_name: Original file name
        
    Returns:
        Verification results with issues, severity, and summary
    """
    prompt = build_verification_prompt(text, file_name)
    
    last_error = None
    for attempt in range(2):
        try:
            result = bedrock_client.invoke_model(
                prompt=prompt,
                max_tokens=2000,
                temperature=0.3
            )
            response_text = result['text']
            start, end = response_text.find('{'), response_text.rfind('}')
            if start == -1 or end == -1:
                raise ValueError('No JSON object in response')
            verification = json.loads(response_text[start:end + 1])
            issues = verification.get('issues', [])
            if not isinstance(issues, list):
                raise ValueError('issues is not a list')
            for issue in issues:
                issue['severity'] = str(issue.get('severity', 'LOW')).upper()
                # Uploaded copies are often unsigned drafts: never rank that above minor
                if str(issue.get('type', '')).lower() in ('signature', 'witness', 'stamp'):
                    issue['severity'] = 'LOW'
                if issue['severity'] not in ('HIGH', 'MEDIUM', 'LOW'):
                    issue['severity'] = 'MEDIUM'
            return {
                'fileName': file_name,
                'issues': issues,
                'summary': verification.get('summary', 'Document verification complete'),
                'overallSeverity': str(verification.get('overallSeverity', 'LOW')).upper(),
                'truncated': len(text) > MAX_VERIFY_CHARS,
            }
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            print(f"Verification parse attempt {attempt + 1} failed: {str(e)}")
    raise RuntimeError(f'Could not read the AI response: {last_error}')


def build_verification_prompt(text: str, file_name: str) -> str:
    """
    Build prompt for document verification
    
    Args:
        text: Document text
        file_name: File name
        
    Returns:
        Formatted prompt for Bedrock
    """
    return f"""You are an expert legal document reviewer. Analyze the following document for common errors and issues.

DOCUMENT NAME: {file_name}

DOCUMENT TEXT:
{text[:MAX_VERIFY_CHARS]}

ANALYZE FOR THE FOLLOWING ISSUES:

1. **Missing Signatures**: Check if signature fields are empty or missing
2. **Name Mismatches**: Look for inconsistent names across the document
3. **Date Issues**: Check for:
   - Invalid dates (e.g., 32nd January)
   - Future dates where past dates expected
   - Inconsistent date formats
   - Missing dates in critical sections
4. **Spelling Mistakes**: Identify spelling errors in legal terms and general text
5. **Unfair or Illegal Clauses** (most important): clauses that are one-sided or against Indian law, e.g. non-refundable security deposits, entry without notice, unfair termination or notice periods, waiving statutory rights, penalties far above actual loss, disputes decided only by one party. Name the Indian law it conflicts with when you are sure (e.g. Indian Contract Act 1872 s.23 / s.74, Model Tenancy Act 2021, Consumer Protection Act 2019, labour codes).
6. **Legal Document Errors**:
   - Missing mandatory clauses
   - Incomplete sentences
   - Missing party information
   - Unclear terms or ambiguous language
   - Missing witness information
   - Incorrect legal terminology

For each issue found, provide:
- **type**: Category (unfair_clause, signature, name, date, spelling, legal, formatting)
- **severity**: HIGH (critical legal issue), MEDIUM (important but not critical), LOW (minor issue)
- **description**: Clear description of the issue
- **location**: Where in the document (e.g., "Page 1, Paragraph 3" or "Signature section")
- **suggestion**: How to fix it

Respond in JSON format with these EXACT keys:
{{
  "issues": [
    {{
      "type": "signature",
      "severity": "HIGH",
      "description": "Signature field is empty in the agreement section",
      "location": "Bottom of page 1",
      "suggestion": "Obtain signature from all parties before finalizing"
    }},
    {{
      "type": "date",
      "severity": "MEDIUM",
      "description": "Date format inconsistent (DD/MM/YYYY vs MM/DD/YYYY)",
      "location": "Header and footer",
      "suggestion": "Use consistent date format throughout (DD/MM/YYYY recommended for Indian documents)"
    }}
  ],
  "summary": "Found 2 issues: 1 HIGH severity (missing signature), 1 MEDIUM severity (date format inconsistency). Recommend addressing high-severity issues before finalizing.",
  "overallSeverity": "HIGH",
  "timestamp": "2026-03-04T16:30:00Z"
}}

IMPORTANT:
- The text may be a draft or an unsigned copy: report missing signatures, witnesses or stamp duty at most once, as LOW severity.
- If no issues found, return empty issues array with summary "No issues found. Document appears to be properly formatted."
- Be thorough but practical - focus on issues that could cause legal problems
- Provide actionable suggestions for each issue

Respond with ONLY the JSON object, no markdown formatting."""


def error_response(error_message: str, status_code: int = 500) -> Dict[str, Any]:
    """Generate error response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'POST,OPTIONS'
        },
        'body': json.dumps({
            'success': False,
            'error': error_message
        }, ensure_ascii=False)
    }
