#!/usr/bin/env python3
"""
Test script for Document Translator Lambda
"""

import requests
import json

BASE_URL = "https://ked0qedvxi.execute-api.ap-south-2.amazonaws.com/prod"

def test_document_translator():
    """Test document translator endpoint"""
    
    endpoint = f"{BASE_URL}/translate/document"
    
    # Test payload - simulating a document translation request
    payload = {
        "userId": "test-user-001",
        "s3Key": "test_petition_s3.txt",
        "sourceLanguage": "en",
        "targetLanguage": "hi"
    }
    
    print("=" * 80)
    print("TESTING DOCUMENT TRANSLATOR LAMBDA")
    print("=" * 80)
    print(f"Endpoint: {endpoint}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print()
    
    try:
        response = requests.post(
            endpoint,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print()
        
        if response.status_code == 200:
            print("✅ SUCCESS - Document Translator Lambda is working!")
            print()
            print("Response Body:")
            print(json.dumps(response.json(), indent=2))
            return True
        else:
            print("❌ FAILED - Document Translator Lambda returned error")
            print()
            print("Response Body:")
            print(response.text)
            return False
            
    except requests.exceptions.Timeout:
        print("❌ FAILED - Request timed out after 60 seconds")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ FAILED - Request error: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ FAILED - Unexpected error: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_document_translator()
    exit(0 if success else 1)
