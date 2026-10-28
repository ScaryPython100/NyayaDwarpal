# Legal Petition Verifier Lambda Function

## Overview

The Legal Petition Verifier Lambda function verifies existing legal petitions for defects, outdated citations, and compliance with BNS/BNSS 2023 legal framework. It integrates with AWS Bedrock (Claude 3.5 Sonnet) for intelligent verification and Textract for PDF processing.

## Features

- **Outdated Citation Detection**: Scans for IPC/CrPC sections and suggests BNS/BNSS 2023 replacements
- **Missing Section Detection**: Checks for mandatory Prayer, Grounds, Facts, and Verification sections
- **Procedural Compliance Check**: Uses Bedrock AI to identify procedural defects
- **PDF Support**: Extracts text from PDF documents using AWS Textract
- **Compliance Scoring**: Provides 0-100 compliance score based on defects found

## API Endpoints

### POST /petition/generate

Verify petition from text input.

**Request Body:**
```json
{
  "userId": "user-123",
  "petitionText": "IN THE HIGH COURT OF KARNATAKA\n\nPETITION UNDER IPC SECTION 302..."
}
```

**Response:**
```json
{
  "success": true,
  "message": "Verification completed",
  "data": {
    "verificationId": "ver-789",
    "status": "completed",
    "results": {
      "status": "major_defects",
      "complianceScore": 70,
      "totalIssues": 3,
      "outdatedCitations": [
        {
          "type": "outdated_ipc",
          "original": "IPC Section 302",
          "suggested": "BNS Section 103",
          "location": "Position 45-60",
          "severity": "high",
          "description": "IPC Section 302 has been replaced by BNS Section 103 under the Bharatiya Nyaya Sanhita, 2023"
        }
      ],
      "missingSections": [
        {
          "section": "Verification",
          "severity": "critical",
          "description": "Petition must include a verification statement as required under law"
        }
      ],
      "proceduralDefects": [
        {
          "defect": "Missing party details",
          "severity": "major",
          "suggestion": "Include full names and addresses of all parties"
        }
      ],
      "summary": "Petition has 3 defect(s) requiring attention. Compliance score: 70/100. Please address all critical and major defects before filing."
    },
    "message": "Petition verification completed"
  }
}
```

### POST /petition/clarify

Verify petition from PDF document using Textract.

**Request Body:**
```json
{
  "userId": "user-123",
  "s3Key": "petitions/user-123/doc-456/petition.pdf"
}
```

OR

```json
{
  "userId": "user-123",
  "documentId": "doc-456"
}
```

**Response:**
Same format as `/petition/generate` with additional `extractedText` field showing first 500 characters.

## Verification Logic

### 1. Outdated Citation Detection

Scans for:
- **IPC Sections**: Detects patterns like "IPC Section 302", "Indian Penal Code Section 379"
- **CrPC Sections**: Detects patterns like "CrPC Section 154", "Criminal Procedure Code Section 161"

Provides BNS/BNSS 2023 replacements:
- IPC 302 → BNS 103 (Murder)
- IPC 379 → BNS 303 (Theft)
- IPC 420 → BNS 318 (Cheating)
- CrPC 154 → BNSS 173 (FIR)
- CrPC 437 → BNSS 483 (Bail)

### 2. Missing Section Detection

Checks for mandatory sections:
- **Prayer** (Critical): Relief sought from the court
- **Grounds** (Critical): Legal basis for the claim
- **Facts** (Major): Chronological narrative
- **Verification** (Critical): Verification statement

### 3. Procedural Compliance Check

Uses Bedrock AI to identify:
- Missing mandatory clauses under BNS/BNSS 2023
- Improper formatting or structure
- Missing party details or case information
- Incomplete or vague relief sought
- Missing dates or timeline information

### 4. Compliance Scoring

- **100 points**: No defects found (Compliant)
- **-10 points**: Per defect found
- **Status**:
  - `compliant`: 0 issues
  - `minor_defects`: 1-3 issues
  - `major_defects`: 4+ issues

## Environment Variables

- `DOCUMENT_BUCKET`: S3 bucket for storing petitions
- `SESSION_TABLE`: DynamoDB table for storing verification results
- `BEDROCK_REGION`: AWS region for Bedrock service (default: us-east-1)

## BNS/BNSS Mapping

The function includes comprehensive mapping of outdated IPC/CrPC sections to new BNS/BNSS 2023 sections:

**IPC to BNS:**
- 302 → 103 (Murder)
- 304 → 105 (Culpable homicide)
- 307 → 109 (Attempt to murder)
- 376 → 63 (Rape)
- 379 → 303 (Theft)
- 420 → 318 (Cheating)
- 498A → 84 (Cruelty)
- 354 → 74 (Assault on woman)
- 406 → 316 (Criminal breach of trust)
- 323 → 115 (Voluntarily causing hurt)
- 504 → 356 (Intentional insult)

**CrPC to BNSS:**
- 154 → 173 (FIR)
- 161 → 180 (Examination of witnesses)
- 173 → 193 (Report of investigation)
- 207 → 230 (Supply of copies)
- 313 → 347 (Examination of accused)
- 437 → 483 (Bail in non-bailable offences)

## Dependencies

- boto3: AWS SDK
- pydantic: Data validation
- bedrock_client: Shared Bedrock integration (from Lambda layer)
- models: Shared data models (from Lambda layer)
- aws_helpers: Shared AWS helpers (from Lambda layer)

## Deployment

The function is deployed as part of the Nyaya-Dwarpal CDK stack:

```bash
npx cdk deploy
```

## Testing

Test the function via API Gateway:

```bash
# Verify petition from text
curl -X POST https://API_ENDPOINT/prod/petition/generate \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "test-user",
    "petitionText": "IN THE HIGH COURT\n\nPETITION UNDER IPC SECTION 302\n\nPRAYER: Grant bail to the accused..."
  }'

# Verify petition from PDF
curl -X POST https://API_ENDPOINT/prod/petition/clarify \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "test-user",
    "s3Key": "petitions/test-user/doc-123/petition.pdf"
  }'
```

## Error Handling

The function includes comprehensive error handling:
- Invalid request validation
- Textract extraction failures
- Bedrock API failures with graceful degradation
- S3 and DynamoDB operation retries
- Proper HTTP status codes and error messages

## Limitations

- PDF text extraction limited by Textract capabilities
- Bedrock prompt limited to first 3000 characters of petition
- Verification results stored for 30 days (TTL)
- Requires valid S3 key for PDF verification

## Legal Framework

Based on:
- **Bharatiya Nyaya Sanhita (BNS), 2023**: Replaces Indian Penal Code (IPC)
- **Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023**: Replaces Code of Criminal Procedure (CrPC)
- Effective from: July 1, 2024
