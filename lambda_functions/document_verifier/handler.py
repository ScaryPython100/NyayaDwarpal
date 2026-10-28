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
import os
import sys
from typing import Dict, Any, List
from io import BytesIO

# Import shared utilities (from Lambda layer)
sys.path.insert(0, '/opt/python')

from bedrock_client import BedrockClient

# Initialize Groq client
bedrock_client = BedrockClient()


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
            return error_response(f'Invalid base64 encoding: {str(e)}')
        
        # Extract text based on file type
        extracted_text = extract_text(document_bytes, file_type, file_name)
        
        if not extracted_text or len(extracted_text.strip()) < 10:
            return error_response('Could not extract sufficient text from document')
        
        # Verify document using Groq
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
        return error_response(str(e))


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
        elif file_type in ['docx', 'doc'] or file_name.endswith(('.docx', '.doc')):
            return extract_text_from_docx(document_bytes)
        elif file_type in ['jpg', 'jpeg', 'png', 'tiff', 'bmp'] or file_name.endswith(('.jpg', '.jpeg', '.png', '.tiff', '.bmp')):
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
        
        text = []
        for page in pdf_reader.pages:
            text.append(page.extract_text())
        
        return '\n'.join(text)
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


def extract_text_from_image(image_bytes: bytes) -> str:
    """Extract text from image using pytesseract (OCR)"""
    try:
        from PIL import Image
        import pytesseract
        
        image = Image.open(BytesIO(image_bytes))
        text = pytesseract.image_to_string(image)
        
        return text
    except Exception as e:
        print(f"Error extracting image text: {str(e)}")
        raise ValueError(f'Failed to extract text from image: {str(e)}')


def verify_document(text: str, file_name: str) -> Dict[str, Any]:
    """
    Verify document for common legal document errors using Groq
    
    Args:
        text: Extracted document text
        file_name: Original file name
        
    Returns:
        Verification results with issues, severity, and summary
    """
    prompt = build_verification_prompt(text, file_name)
    
    try:
        result = bedrock_client.invoke_model(
            prompt=prompt,
            max_tokens=2000,
            temperature=0.3
        )
        
        # Parse JSON response
        response_text = result['text'].strip()
        print(f"Groq response: {response_text[:500]}...")
        
        # Remove markdown code blocks if present
        if response_text.startswith('```'):
            response_text = response_text.split('```')[1]
            if response_text.startswith('json'):
                response_text = response_text[4:]
            response_text = response_text.rsplit('```', 1)[0]
        
        verification = json.loads(response_text)
        
        return {
            'fileName': file_name,
            'issues': verification.get('issues', []),
            'summary': verification.get('summary', 'Document verification complete'),
            'overallSeverity': verification.get('overallSeverity', 'LOW'),
            'timestamp': verification.get('timestamp', '')
        }
        
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {str(e)}")
        print(f"Response text: {response_text}")
        return {
            'fileName': file_name,
            'issues': [],
            'summary': 'Could not parse verification results',
            'overallSeverity': 'MEDIUM',
            'timestamp': ''
        }
    except Exception as e:
        print(f"Error in document verification: {str(e)}")
        raise


def build_verification_prompt(text: str, file_name: str) -> str:
    """
    Build prompt for document verification
    
    Args:
        text: Document text
        file_name: File name
        
    Returns:
        Formatted prompt for Groq
    """
    return f"""You are an expert legal document reviewer. Analyze the following document for common errors and issues.

DOCUMENT NAME: {file_name}

DOCUMENT TEXT:
{text[:4000]}  

ANALYZE FOR THE FOLLOWING ISSUES:

1. **Missing Signatures**: Check if signature fields are empty or missing
2. **Name Mismatches**: Look for inconsistent names across the document
3. **Date Issues**: Check for:
   - Invalid dates (e.g., 32nd January)
   - Future dates where past dates expected
   - Inconsistent date formats
   - Missing dates in critical sections
4. **Spelling Mistakes**: Identify spelling errors in legal terms and general text
5. **Legal Document Errors**:
   - Missing mandatory clauses
   - Incomplete sentences
   - Missing party information
   - Unclear terms or ambiguous language
   - Missing witness information
   - Incorrect legal terminology

For each issue found, provide:
- **type**: Category (signature, name, date, spelling, legal, formatting)
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
- If no issues found, return empty issues array with summary "No issues found. Document appears to be properly formatted."
- Be thorough but practical - focus on issues that could cause legal problems
- Provide actionable suggestions for each issue

Respond with ONLY the JSON object, no markdown formatting."""


def error_response(error_message: str) -> Dict[str, Any]:
    """Generate error response"""
    return {
        'statusCode': 500,
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
