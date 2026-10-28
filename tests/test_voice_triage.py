#!/usr/bin/env python3
"""
Test script for Voice Triage Lambda
"""

import requests
import json

BASE_URL = "https://ked0qedvxi.execute-api.ap-south-2.amazonaws.com/prod"

def test_voice_triage():
    """Test voice triage endpoint"""
    
    endpoint = f"{BASE_URL}/voice/triage"
    
    # Test payload - simulating a legal problem description
    payload = {
        "userId": "test-user-001",
        "transcribedText": "My landlord is not returning my security deposit even after 3 months of vacating the property. I have all the receipts and the rental agreement. What should I do?",
        "language": "en"
    }
    
    print("=" * 80)
    print("TESTING VOICE TRIAGE LAMBDA")
    print("=" * 80)
    print(f"Endpoint: {endpoint}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print()
    
    try:
        response = requests.post(
            endpoint,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print()
        
        if response.status_code == 200:
            print("✅ SUCCESS - Voice Triage Lambda is working!")
            print()
            print("Response Body:")
            print(json.dumps(response.json(), indent=2))
            return True
        else:
            print("❌ FAILED - Voice Triage Lambda returned error")
            print()
            print("Response Body:")
            print(response.text)
            return False
            
    except requests.exceptions.Timeout:
        print("❌ FAILED - Request timed out after 30 seconds")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ FAILED - Request error: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ FAILED - Unexpected error: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_voice_triage()
    exit(0 if success else 1)
