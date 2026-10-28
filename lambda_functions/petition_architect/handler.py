"""
Legal Petition Verifier Lambda Function

This Lambda function verifies existing legal petitions for defects, outdated citations,
and compliance with BNS/BNSS 2023 legal framework. It integrates with AWS Bedrock
for intelligent verification and Textract for PDF processing.
"""

import json
import os
import uuid
import re
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

import boto3
from botocore.exceptions import ClientError

# Import shared modules (from Lambda layer)
import sys
sys.path.insert(0, '/opt/python')

from bedrock_client import BedrockClient
from models import APIResponse
from aws_helpers import DynamoDBHelper, S3Helper


# Environment variables
DOCUMENT_BUCKET = os.environ.get("DOCUMENT_BUCKET", "")
DOCUMENT_TABLE = os.environ.get("DOCUMENT_TABLE", "")
SESSION_TABLE = os.environ.get("SESSION_TABLE", "")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "us-east-1")
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-2")

# Initialize clients
bedrock_client = BedrockClient(region=BEDROCK_REGION)
dynamodb_helper = DynamoDBHelper(region=AWS_REGION)
s3_helper = S3Helper(region=AWS_REGION)
textract_client = boto3.client('textract', region_name=AWS_REGION)

# BNS/BNSS mapping for outdated IPC/CrPC sections
IPC_TO_BNS_MAPPING = {
    "302": "103",  # Murder
    "304": "105",  # Culpable homicide not amounting to murder
    "307": "109",  # Attempt to murder
    "376": "63",   # Rape
    "379": "303",  # Theft
    "420": "318",  # Cheating
    "498A": "84",  # Cruelty by husband or relatives
    "354": "74",   # Assault or criminal force to woman with intent to outrage her modesty
    "406": "316",  # Criminal breach of trust
    "323": "115",  # Voluntarily causing hurt
    "504": "356",  # Intentional insult with intent to provoke breach of peace
}

CRPC_TO_BNSS_MAPPING = {
    "154": "173",  # FIR
    "161": "180",  # Examination of witnesses
    "173": "193",  # Report of investigation
    "207": "230",  # Supply of copies
    "313": "347",  # Examination of accused
    "437": "483",  # Bail in non-bailable offences
}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for Legal Petition Verifier
    
    Handles two event sources:
    1. S3 Events: Automatically process uploaded documents
    2. API Gateway Events: Handle direct API requests
       - POST /petition/generate: Verify petition from text input
       - POST /petition/clarify: Verify petition from PDF document (using Textract)
    
    Args:
        event: S3 or API Gateway event
        context: Lambda context
        
    Returns:
        API Gateway response with verification results or S3 processing result
    """
    print("=" * 80)
    print("LAMBDA_HANDLER START")
    print("=" * 80)
    
    try:
        print("CHECKPOINT 1: Starting lambda_handler")
        
        # Log incoming event for debugging
        print("CHECKPOINT 2: Logging incoming event")
        print(f"Received event: {json.dumps(event)}")
        
        # Detect event source
        print("CHECKPOINT 3: Detecting event source")
        
        # Check if this is an S3 event
        if "Records" in event and len(event["Records"]) > 0:
            first_record = event["Records"][0]
            if "s3" in first_record and first_record.get("eventSource") == "aws:s3":
                print("CHECKPOINT 4: S3 event detected - routing to S3 handler")
                return handle_s3_event(event)
        
        # Otherwise, treat as API Gateway event
        print("CHECKPOINT 5: API Gateway event detected")
        
        # Parse request
        print("CHECKPOINT 6: Parsing request path and body")
        path = event.get("path", "")
        print(f"Path: {path}")
        
        body_str = event.get("body", "{}")
        print(f"Body string length: {len(body_str) if body_str else 0}")
        
        # Handle empty body
        if not body_str:
            print("CHECKPOINT 7: Empty body detected - returning 400")
            return create_response(
                400,
                APIResponse.error_response(
                    "Empty request body",
                    "Request body is required"
                )
            )
        
        print("CHECKPOINT 8: Parsing JSON body")
        try:
            body = json.loads(body_str)
            print(f"Body parsed successfully. Keys: {list(body.keys())}")
        except json.JSONDecodeError as e:
            print(f"CHECKPOINT 9: JSON decode error: {str(e)}")
            return create_response(
                400,
                APIResponse.error_response(
                    "Invalid JSON in request body",
                    str(e)
                )
            )
        
        # Route to appropriate handler
        print("CHECKPOINT 10: Routing to appropriate handler")
        
        # /petition/generate now handles text-based verification
        if path.endswith("/generate"):
            print("CHECKPOINT 11: Routing to handle_verify_petition_text")
            return handle_verify_petition_text(body)
        # /petition/clarify now handles PDF-based verification
        elif path.endswith("/clarify"):
            print("CHECKPOINT 12: Routing to handle_verify_petition_pdf")
            return handle_verify_petition_pdf(body)
        else:
            print(f"CHECKPOINT 13: Invalid endpoint - path: {path}")
            return create_response(
                400,
                APIResponse.error_response(
                    "Invalid endpoint",
                    f"Path '{path}' is not supported. Use /petition/generate or /petition/clarify"
                )
            )
    
    except Exception as e:
        print("=" * 80)
        print("CRITICAL ERROR IN LAMBDA_HANDLER")
        print("=" * 80)
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        print("Full traceback:")
        import traceback
        traceback.print_exc()
        print("=" * 80)
        return create_response(
            500,
            APIResponse.error_response(
                "Internal server error",
                f"Unexpected error: {str(e)}"
            )
        )


def handle_s3_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle S3 event - automatically process uploaded documents
    
    Args:
        event: S3 event containing Records with s3 object information
        
    Returns:
        Processing result
    """
    print("*" * 80)
    print("HANDLE_S3_EVENT START")
    print("*" * 80)
    
    try:
        print("S3_CHECKPOINT 1: Parsing S3 event records")
        
        # Process each record (usually just one)
        results = []
        for record in event.get("Records", []):
            try:
                print("S3_CHECKPOINT 2: Extracting S3 bucket and key")
                s3_info = record.get("s3", {})
                bucket_name = s3_info.get("bucket", {}).get("name", "")
                object_key = s3_info.get("object", {}).get("key", "")
                
                print(f"S3_CHECKPOINT 3: Processing file - Bucket: {bucket_name}, Key: {object_key}")
                
                # Validate bucket matches our document bucket
                if bucket_name != DOCUMENT_BUCKET:
                    print(f"S3_CHECKPOINT 4: Skipping - bucket mismatch (expected: {DOCUMENT_BUCKET}, got: {bucket_name})")
                    continue
                
                print("S3_CHECKPOINT 5: Determining file type")
                file_extension = object_key.lower().split('.')[-1] if '.' in object_key else ''
                print(f"File extension: {file_extension}")
                
                # Extract user ID from object key if available (e.g., petitions/userId/...)
                print("S3_CHECKPOINT 6: Extracting user ID from path")
                user_id = "anonymous"
                if "/" in object_key:
                    path_parts = object_key.split("/")
                    if len(path_parts) > 1:
                        user_id = path_parts[1] if path_parts[0] == "petitions" else path_parts[0]
                print(f"User ID: {user_id}")
                
                # Process based on file type
                print("S3_CHECKPOINT 7: Processing file based on type")
                
                if file_extension == 'pdf':
                    print("S3_CHECKPOINT 8: PDF detected - extracting text with Textract")
                    try:
                        petition_text = extract_text_from_pdf(object_key)
                        print(f"S3_CHECKPOINT 9: Extracted {len(petition_text)} characters from PDF")
                    except Exception as e:
                        print(f"S3_CHECKPOINT 10: Error extracting PDF text: {str(e)}")
                        import traceback
                        traceback.print_exc()
                        continue
                
                elif file_extension in ['txt', 'text']:
                    print("S3_CHECKPOINT 11: Text file detected - reading from S3")
                    try:
                        petition_text = s3_helper.read_text_file(bucket_name, object_key)
                        print(f"S3_CHECKPOINT 12: Read {len(petition_text)} characters from text file")
                    except Exception as e:
                        print(f"S3_CHECKPOINT 13: Error reading text file: {str(e)}")
                        import traceback
                        traceback.print_exc()
                        continue
                
                else:
                    print(f"S3_CHECKPOINT 14: Unsupported file type: {file_extension}")
                    continue
                
                # Verify the petition
                print("S3_CHECKPOINT 15: Starting petition verification")
                try:
                    verification_results = verify_petition(petition_text)
                    print(f"S3_CHECKPOINT 16: Verification completed. Status: {verification_results.get('status')}")
                except Exception as e:
                    print(f"S3_CHECKPOINT 17: Error during verification: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    continue
                
                # Generate verification ID and store results
                print("S3_CHECKPOINT 18: Generating verification ID")
                verification_id = str(uuid.uuid4())
                print(f"Generated verification ID: {verification_id}")
                
                try:
                    print("S3_CHECKPOINT 19: Storing verification results to DynamoDB")
                    store_verification_results(user_id, verification_id, verification_results, petition_text, object_key)
                    print(f"S3_CHECKPOINT 20: Successfully stored verification ID: {verification_id}")
                except Exception as e:
                    print(f"S3_CHECKPOINT 21: Warning - Failed to store results: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    # Continue even if storage fails
                
                results.append({
                    "s3Key": object_key,
                    "verificationId": verification_id,
                    "status": verification_results.get("status"),
                    "complianceScore": verification_results.get("complianceScore")
                })
                
                print(f"S3_CHECKPOINT 22: Successfully processed {object_key}")
            
            except Exception as e:
                print("*" * 80)
                print(f"ERROR PROCESSING S3 RECORD")
                print("*" * 80)
                print(f"Error type: {type(e).__name__}")
                print(f"Error message: {str(e)}")
                print("Full traceback:")
                import traceback
                traceback.print_exc()
                print("*" * 80)
                # Continue to next record
                continue
        
        print("S3_CHECKPOINT 23: All records processed")
        print(f"Successfully processed {len(results)} file(s)")
        print("*" * 80)
        
        # Return success response
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": f"Successfully processed {len(results)} file(s)",
                "results": results
            })
        }
    
    except Exception as e:
        print("*" * 80)
        print("CRITICAL ERROR IN HANDLE_S3_EVENT")
        print("*" * 80)
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        print("Full traceback:")
        import traceback
        traceback.print_exc()
        print("*" * 80)
        
        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": "Failed to process S3 event",
                "error": str(e)
            })
        }


def handle_verify_petition_text(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verify petition from text input
    
    Args:
        body: Request body containing petitionText
        
    Returns:
        API Gateway response with verification results
    """
    print("-" * 80)
    print("HANDLE_VERIFY_PETITION_TEXT START")
    print("-" * 80)
    
    try:
        print("TEXT_CHECKPOINT 1: Validating required fields")
        
        # Validate required fields
        if "petitionText" not in body:
            print("TEXT_CHECKPOINT 2: Missing petitionText field")
            return create_response(
                400,
                APIResponse.error_response(
                    "Missing required field: petitionText",
                    "Request body must include 'petitionText' field"
                )
            )
        
        print("TEXT_CHECKPOINT 3: Extracting petition text and user ID")
        petition_text = body["petitionText"]
        user_id = body.get("userId", "anonymous")
        print(f"User ID: {user_id}")
        print(f"Petition text length: {len(petition_text)}")
        
        # Validate petition text is not empty
        print("TEXT_CHECKPOINT 4: Validating petition text is not empty")
        if not petition_text or not petition_text.strip():
            print("TEXT_CHECKPOINT 5: Empty petition text detected")
            return create_response(
                400,
                APIResponse.error_response(
                    "Empty petition text",
                    "petitionText cannot be empty"
                )
            )
        
        print(f"TEXT_CHECKPOINT 6: Starting verification for user: {user_id}")
        
        # Perform verification
        try:
            print("TEXT_CHECKPOINT 7: Calling verify_petition()")
            verification_results = verify_petition(petition_text)
            print(f"TEXT_CHECKPOINT 8: Verification completed. Status: {verification_results.get('status')}")
        except Exception as e:
            print("TEXT_CHECKPOINT 9: Error during verification")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {str(e)}")
            import traceback
            traceback.print_exc()
            return create_response(
                500,
                APIResponse.error_response(
                    "Verification failed",
                    f"Error during petition verification: {str(e)}"
                )
            )
        
        # Always generate verification ID and store results
        print("TEXT_CHECKPOINT 10: Generating verification ID")
        verification_id = str(uuid.uuid4())
        print(f"Generated verification ID: {verification_id}")
        
        try:
            print("TEXT_CHECKPOINT 11: Storing verification results to DynamoDB")
            store_verification_results(user_id, verification_id, verification_results, petition_text)
            print(f"TEXT_CHECKPOINT 12: Successfully stored verification ID: {verification_id}")
        except Exception as e:
            print("TEXT_CHECKPOINT 13: Warning - Failed to store results")
            print(f"Storage error type: {type(e).__name__}")
            print(f"Storage error message: {str(e)}")
            import traceback
            traceback.print_exc()
            # Continue even if storage fails
        
        print("TEXT_CHECKPOINT 14: Building response data")
        response_data = {
            "verificationId": verification_id,
            "status": "completed",
            "results": verification_results,
            "message": "Petition verification completed"
        }
        print(f"TEXT_CHECKPOINT 15: Response data built successfully")
        
        print("TEXT_CHECKPOINT 16: Creating API response")
        response = create_response(
            200,
            APIResponse.success_response(
                "Verification completed",
                response_data
            )
        )
        print("TEXT_CHECKPOINT 17: Returning successful response")
        print("-" * 80)
        return response
    
    except Exception as e:
        print("-" * 80)
        print("ERROR IN HANDLE_VERIFY_PETITION_TEXT")
        print("-" * 80)
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        print("Full traceback:")
        import traceback
        traceback.print_exc()
        print("-" * 80)
        return create_response(
            500,
            APIResponse.error_response(
                "Failed to verify petition",
                f"Unexpected error: {str(e)}"
            )
        )


def handle_verify_petition_pdf(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verify petition from PDF document using Textract
    
    Args:
        body: Request body containing s3Key or documentId
        
    Returns:
        API Gateway response with verification results
    """
    try:
        # Validate required fields
        if "s3Key" not in body and "documentId" not in body:
            return create_response(
                400,
                APIResponse.error_response(
                    "Missing required field: s3Key or documentId",
                    "Invalid request body"
                )
            )
        
        user_id = body.get("userId", "anonymous")
        s3_key = body.get("s3Key")
        
        # If documentId provided, construct s3_key
        if not s3_key and "documentId" in body:
            s3_key = f"petitions/{user_id}/{body['documentId']}/petition.pdf"
        
        # Extract text from PDF using Textract
        petition_text = extract_text_from_pdf(s3_key)
        
        # Perform verification
        try:
            verification_results = verify_petition(petition_text)
        except Exception as e:
            print(f"Error during verification: {str(e)}")
            import traceback
            traceback.print_exc()
            return create_response(
                500,
                APIResponse.error_response(
                    "Verification failed",
                    f"Error during petition verification: {str(e)}"
                )
            )
        
        # Always generate verification ID and store results
        verification_id = str(uuid.uuid4())
        try:
            store_verification_results(user_id, verification_id, verification_results, petition_text, s3_key)
            print(f"Stored verification results with ID: {verification_id}")
        except Exception as e:
            print(f"Warning: Failed to store results: {str(e)}")
            import traceback
            traceback.print_exc()
            # Continue even if storage fails
        
        response_data = {
            "verificationId": verification_id,
            "status": "completed",
            "results": verification_results,
            "extractedText": petition_text[:500] + "..." if len(petition_text) > 500 else petition_text,
            "message": "Petition verification completed"
        }
        
        return create_response(
            200,
            APIResponse.success_response(
                "Verification completed",
                response_data
            )
        )
    
    except Exception as e:
        print(f"Error in handle_verify_petition_pdf: {str(e)}")
        return create_response(
            500,
            APIResponse.error_response(
                "Failed to verify petition from PDF",
                str(e)
            )
        )


def verify_petition(petition_text: str) -> Dict[str, Any]:
    """
    Verify petition for defects, outdated citations, and compliance
    
    Args:
        petition_text: Full text of the petition
        
    Returns:
        Verification results with defects and suggestions
    """
    # Extract outdated citations
    outdated_citations = extract_outdated_citations(petition_text)
    
    # Check for missing sections
    missing_sections = check_missing_sections(petition_text)
    
    # Check procedural compliance using Bedrock
    procedural_defects = check_procedural_compliance(petition_text)
    
    # Calculate overall score
    total_issues = len(outdated_citations) + len(missing_sections) + len(procedural_defects)
    compliance_score = max(0, 100 - (total_issues * 10))
    
    # Determine status
    if total_issues == 0:
        status = "compliant"
    elif total_issues <= 3:
        status = "minor_defects"
    else:
        status = "major_defects"
    
    return {
        "status": status,
        "complianceScore": compliance_score,
        "totalIssues": total_issues,
        "outdatedCitations": outdated_citations,
        "missingSections": missing_sections,
        "proceduralDefects": procedural_defects,
        "summary": generate_summary(status, total_issues, compliance_score)
    }


def extract_outdated_citations(petition_text: str) -> List[Dict[str, Any]]:
    """
    Extract outdated IPC/CrPC citations and suggest BNS/BNSS replacements
    
    Args:
        petition_text: Full text of the petition
        
    Returns:
        List of outdated citations with suggestions
    """
    outdated = []
    
    # Pattern for IPC sections
    ipc_pattern = r'(?:IPC|Indian Penal Code)\s+(?:Section|Sec\.?|§)\s*(\d+[A-Z]?)'
    ipc_matches = re.finditer(ipc_pattern, petition_text, re.IGNORECASE)
    
    for match in ipc_matches:
        section = match.group(1)
        if section in IPC_TO_BNS_MAPPING:
            outdated.append({
                "type": "outdated_ipc",
                "original": f"IPC Section {section}",
                "suggested": f"BNS Section {IPC_TO_BNS_MAPPING[section]}",
                "location": f"Position {match.start()}-{match.end()}",
                "severity": "high",
                "description": f"IPC Section {section} has been replaced by BNS Section {IPC_TO_BNS_MAPPING[section]} under the Bharatiya Nyaya Sanhita, 2023"
            })
    
    # Pattern for CrPC sections
    crpc_pattern = r'(?:CrPC|Cr\.?P\.?C\.?|Criminal Procedure Code)\s+(?:Section|Sec\.?|§)\s*(\d+[A-Z]?)'
    crpc_matches = re.finditer(crpc_pattern, petition_text, re.IGNORECASE)
    
    for match in crpc_matches:
        section = match.group(1)
        if section in CRPC_TO_BNSS_MAPPING:
            outdated.append({
                "type": "outdated_crpc",
                "original": f"CrPC Section {section}",
                "suggested": f"BNSS Section {CRPC_TO_BNSS_MAPPING[section]}",
                "location": f"Position {match.start()}-{match.end()}",
                "severity": "high",
                "description": f"CrPC Section {section} has been replaced by BNSS Section {CRPC_TO_BNSS_MAPPING[section]} under the Bharatiya Nagarik Suraksha Sanhita, 2023"
            })
    
    return outdated


def check_missing_sections(petition_text: str) -> List[Dict[str, Any]]:
    """
    Check for missing mandatory sections in petition
    
    Args:
        petition_text: Full text of the petition
        
    Returns:
        List of missing sections
    """
    missing = []
    
    # Check for Prayer section
    if not re.search(r'(?:PRAYER|WHEREFORE|RELIEF\s+SOUGHT)', petition_text, re.IGNORECASE):
        missing.append({
            "section": "Prayer",
            "severity": "critical",
            "description": "Petition must include a 'Prayer' section specifying the relief sought from the court"
        })
    
    # Check for Grounds section
    if not re.search(r'(?:GROUNDS|LEGAL\s+BASIS|CAUSE\s+OF\s+ACTION)', petition_text, re.IGNORECASE):
        missing.append({
            "section": "Grounds",
            "severity": "critical",
            "description": "Petition must include 'Grounds' section stating the legal basis for the claim"
        })
    
    # Check for Facts section
    if not re.search(r'(?:FACTS|STATEMENT\s+OF\s+FACTS|FACTUAL\s+BACKGROUND)', petition_text, re.IGNORECASE):
        missing.append({
            "section": "Facts",
            "severity": "major",
            "description": "Petition should include a 'Facts' section with chronological narrative"
        })
    
    # Check for Verification
    if not re.search(r'(?:VERIFICATION|VERIFIED\s+AT)', petition_text, re.IGNORECASE):
        missing.append({
            "section": "Verification",
            "severity": "critical",
            "description": "Petition must include a verification statement as required under law"
        })
    
    return missing


def check_procedural_compliance(petition_text: str) -> List[Dict[str, Any]]:
    """
    Check procedural compliance using Bedrock AI
    
    Args:
        petition_text: Full text of the petition
        
    Returns:
        List of procedural defects
    """
    # Build verification prompt for Bedrock
    prompt = f"""You are a legal expert verifying a petition for compliance with Indian legal standards under BNS/BNSS 2023 framework.

Analyze the following petition and identify procedural defects:

PETITION TEXT:
{petition_text[:3000]}  # Limit to avoid token limits

Check for:
1. Missing mandatory clauses required under BNS/BNSS 2023
2. Improper formatting or structure
3. Missing party details or case information
4. Incomplete or vague relief sought
5. Missing dates or timeline information

Respond in JSON format with an array of defects:
[
  {{
    "defect": "description of defect",
    "severity": "critical|major|minor",
    "suggestion": "how to fix it"
  }}
]

If no defects found, return empty array: []
"""
    
    try:
        print("Calling Bedrock for procedural compliance check...")
        response = bedrock_client.invoke_model(
            prompt=prompt,
            max_tokens=2048,
            temperature=0.3
        )
        
        print(f"Bedrock response received: {response}")
        
        # Parse response
        response_text = response["text"].strip()
        
        # Extract JSON from response
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            defects = json.loads(json_match.group(0))
            print(f"Parsed {len(defects)} procedural defects")
            return defects
        else:
            print("No JSON array found in Bedrock response")
            return []
    
    except Exception as e:
        print(f"Error in procedural compliance check: {str(e)}")
        import traceback
        traceback.print_exc()
        # Return empty list instead of failing the entire verification
        return []


def extract_text_from_pdf(s3_key: str) -> str:
    """
    Extract text from PDF using AWS Textract
    
    Args:
        s3_key: S3 key of the PDF document
        
    Returns:
        Extracted text
    """
    try:
        print(f"Extracting text from PDF: s3://{DOCUMENT_BUCKET}/{s3_key}")
        
        # Call Textract
        response = textract_client.detect_document_text(
            Document={
                'S3Object': {
                    'Bucket': DOCUMENT_BUCKET,
                    'Name': s3_key
                }
            }
        )
        
        print(f"Textract response received with {len(response.get('Blocks', []))} blocks")
        
        # Extract text from blocks
        text_blocks = []
        for block in response.get('Blocks', []):
            if block['BlockType'] == 'LINE':
                text_blocks.append(block['Text'])
        
        extracted_text = '\n'.join(text_blocks)
        print(f"Extracted {len(extracted_text)} characters from PDF")
        
        return extracted_text
    
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        print(f"Textract ClientError: {error_code} - {error_message}")
        raise Exception(f"Failed to extract text from PDF: {error_code} - {error_message}")
    
    except Exception as e:
        print(f"Error extracting text from PDF: {str(e)}")
        import traceback
        traceback.print_exc()
        raise


def store_verification_results(
    user_id: str, 
    verification_id: str, 
    results: Dict[str, Any],
    petition_text: str = "",
    s3_key: Optional[str] = None
) -> None:
    """
    Store verification results in DynamoDB DocumentMetadata table
    
    Args:
        user_id: User identifier
        verification_id: Verification identifier (used as documentId)
        results: Verification results
        petition_text: The petition text that was verified
        s3_key: Optional S3 key if petition was from PDF
    """
    try:
        # Prepare S3 location if available
        s3_location = {}
        if s3_key:
            s3_location = {
                "bucket": DOCUMENT_BUCKET,
                "key": s3_key
            }
        
        # Create item for DocumentMetadata table
        item = {
            "documentId": verification_id,
            "document_type": "petition_verification",
            "filing_timestamp": datetime.utcnow().isoformat(),
            "filer_info": {
                "userId": user_id,
                "verifiedAt": datetime.utcnow().isoformat()
            },
            "s3_location": s3_location,
            "status": results.get("status", "unknown"),
            "preferred_language": "en",
            "verification_results": results,
            "petition_text_preview": petition_text[:500] if petition_text else "",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "ttl": int((datetime.utcnow().timestamp()) + (90 * 24 * 60 * 60))  # 90 days
        }
        
        # Use DOCUMENT_TABLE environment variable
        table_name = DOCUMENT_TABLE
        
        print(f"Storing verification results to table: {table_name}")
        
        dynamodb_helper.put_item(
            table_name=table_name,
            item=item
        )
        
        print(f"Successfully stored verification {verification_id} for user {user_id}")
    
    except Exception as e:
        print(f"Error storing verification results: {str(e)}")
        import traceback
        traceback.print_exc()
        # Don't fail the request if storage fails


def generate_summary(status: str, total_issues: int, compliance_score: int) -> str:
    """
    Generate human-readable summary
    
    Args:
        status: Compliance status
        total_issues: Total number of issues
        compliance_score: Compliance score (0-100)
        
    Returns:
        Summary text
    """
    if status == "compliant":
        return f"Petition is compliant with BNS/BNSS 2023 framework. Compliance score: {compliance_score}/100. No defects found."
    elif status == "minor_defects":
        return f"Petition has {total_issues} minor defect(s). Compliance score: {compliance_score}/100. Review and address the flagged issues before filing."
    else:
        return f"Petition has {total_issues} defect(s) requiring attention. Compliance score: {compliance_score}/100. Please address all critical and major defects before filing."


def create_response(status_code: int, body: APIResponse) -> Dict[str, Any]:
    """
    Create API Gateway response
    
    Args:
        status_code: HTTP status code
        body: Response body
        
    Returns:
        API Gateway response format
    """
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "POST,OPTIONS"
        },
        "body": body.model_dump_json()
    }
