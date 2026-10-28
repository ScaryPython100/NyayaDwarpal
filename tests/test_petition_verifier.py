#!/usr/bin/env python3
"""
Script to test the PetitionArchitect Lambda function
"""

import json
import requests

# API endpoint - Hyderabad (ap-south-2) region
API_ENDPOINT = "https://ked0qedvxi.execute-api.ap-south-2.amazonaws.com/prod"

def test_text_verification():
    """Test petition verification from text"""
    
    url = f"{API_ENDPOINT}/petition/generate"
    
    payload = {
        "userId": "test-user-123",
        "petitionText": """IN THE COURT OF CIVIL JUDGE

PETITION UNDER SECTION 138 OF NEGOTIABLE INSTRUMENTS ACT

FACTS:
The petitioner issued a cheque for Rs. 50,000 to the respondent on 15th January 2024.
The cheque was dishonored due to insufficient funds on 20th January 2024.
A legal notice was sent on 25th January 2024 under IPC Section 420.

GROUNDS:
The respondent has committed an offense under CrPC Section 154.
The petitioner seeks relief under IPC Section 302.

PRAYER:
The petitioner prays that this honorable court may be pleased to:
1. Direct the respondent to pay Rs. 50,000 with interest
2. Award costs of this petition

VERIFICATION:
I, the petitioner, verify that the contents of this petition are true to the best of my knowledge."""
    }
    
    print("Testing text-based petition verification...")
    print(f"URL: {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}\n")
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}\n")
        
        try:
            response_json = response.json()
            print(f"Response Body:\n{json.dumps(response_json, indent=2)}")
            
            # Check for verification results
            if response.status_code == 200 and response_json.get('success'):
                results = response_json.get('data', {}).get('results', {})
                print(f"\n=== Verification Results ===")
                print(f"Status: {results.get('status')}")
                print(f"Compliance Score: {results.get('complianceScore')}/100")
                print(f"Total Issues: {results.get('totalIssues')}")
                print(f"Outdated Citations: {len(results.get('outdatedCitations', []))}")
                print(f"Missing Sections: {len(results.get('missingSections', []))}")
                print(f"Procedural Defects: {len(results.get('proceduralDefects', []))}")
        except json.JSONDecodeError:
            print(f"Response Body (raw):\n{response.text}")
        
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {str(e)}")
        import traceback
        traceback.print_exc()

def test_minimal_request():
    """Test with minimal payload to isolate issues"""
    
    url = f"{API_ENDPOINT}/petition/generate"
    
    payload = {
        "petitionText": "This is a test petition with IPC Section 302 and CrPC Section 154."
    }
    
    print("Testing minimal petition verification...")
    print(f"URL: {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}\n")
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        
        print(f"Status Code: {response.status_code}")
        
        try:
            response_json = response.json()
            print(f"Response Body:\n{json.dumps(response_json, indent=2)}")
        except json.JSONDecodeError:
            print(f"Response Body (raw):\n{response.text}")
        
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Run tests
    print("="*80)
    print("PETITION VERIFIER API TEST")
    print("="*80)
    print(f"\nAPI Endpoint: {API_ENDPOINT}")
    print(f"Region: ap-south-2 (Hyderabad)\n")
    print("="*80)
    print()
    
    test_minimal_request()
    print("\n" + "="*80 + "\n")
    test_text_verification()
