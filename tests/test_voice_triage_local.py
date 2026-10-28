#!/usr/bin/env python3
"""
Local test script for Voice Triage Lambda
Tests the Groq API integration and category classification
"""

import json
import os
import sys

# Add lambda_functions to path
sys.path.insert(0, 'lambda_functions/shared/python')
sys.path.insert(0, 'lambda_functions/shared')

from bedrock_client import BedrockClient

def test_voice_triage():
    """Test voice triage with Hindi query about auto driver overcharging"""
    
    # Test query
    transcription = "Auto wale ne meter se 3 guna paisa manga"
    language = "hi"
    use_native_script = True
    
    print("=" * 80)
    print("VOICE TRIAGE LOCAL TEST")
    print("=" * 80)
    print(f"\nTest Query: {transcription}")
    print(f"Language: {language}")
    print(f"Use Native Script: {use_native_script}")
    print("\n" + "=" * 80)
    
    # Check if GROQ_API_KEY is set
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("\n❌ ERROR: GROQ_API_KEY environment variable not set!")
        print("Please set it with: export GROQ_API_KEY='your-api-key'")
        return
    
    print(f"\n✓ GROQ_API_KEY found (length: {len(api_key)})")
    
    # Initialize Bedrock client
    print("\n" + "-" * 80)
    print("STEP 1: Initializing BedrockClient")
    print("-" * 80)
    bedrock_client = BedrockClient(region="us-east-1")
    
    # Build prompt
    print("\n" + "-" * 80)
    print("STEP 2: Building Legal Triage Prompt")
    print("-" * 80)
    prompt = bedrock_client.build_legal_triage_prompt(
        transcription, 
        language, 
        use_native_script
    )
    print(f"Prompt length: {len(prompt)} characters")
    print(f"\nPrompt preview (first 1000 chars):")
    print("-" * 80)
    print(prompt[:1000])
    print("...")
    print("-" * 80)
    
    # Call Groq API
    print("\n" + "-" * 80)
    print("STEP 3: Calling Groq API")
    print("-" * 80)
    
    system_prompt = "You are an expert Indian lawyer with 20+ years of experience. You MUST provide detailed, actionable legal advice. NEVER say 'consult a lawyer' as generic advice. Always give specific steps, costs, timelines, and resources. Choose the most specific legal category - DO NOT return 'Other' unless absolutely necessary."
    
    print(f"System Prompt: {system_prompt[:200]}...")
    print(f"Temperature: 0.7")
    print(f"Max Tokens: 3000")
    
    try:
        result = bedrock_client.invoke_model(
            prompt=prompt,
            max_tokens=3000,
            temperature=0.7,
            system_prompt=system_prompt
        )
        
        print("\n✓ Groq API call successful!")
        print(f"Response length: {len(result['text'])} characters")
        print(f"Token usage: {result.get('usage', {})}")
        
        # Parse response
        print("\n" + "-" * 80)
        print("STEP 4: Parsing Response")
        print("-" * 80)
        
        response_text = result['text'].strip()
        
        # Remove markdown code blocks if present
        if response_text.startswith('```'):
            print("Removing markdown code blocks...")
            response_text = response_text.split('```')[1]
            if response_text.startswith('json'):
                response_text = response_text[4:]
            response_text = response_text.rsplit('```', 1)[0]
        
        print(f"\nCleaned response preview (first 2000 chars):")
        print("-" * 80)
        print(response_text[:2000])
        print("...")
        print("-" * 80)
        
        # Parse JSON
        try:
            classification = json.loads(response_text)
            
            print("\n" + "=" * 80)
            print("CLASSIFICATION RESULTS")
            print("=" * 80)
            
            category = classification.get('category', 'MISSING')
            print(f"\n📋 Category: {category}")
            
            if category == "Other":
                print("❌ PROBLEM: Category is 'Other' - this is the bug!")
            elif "Consumer" in category:
                print("✓ SUCCESS: Category correctly identified as Consumer Rights!")
            else:
                print(f"⚠️  Category is '{category}' - not 'Other' but also not Consumer Rights")
            
            print(f"\n📝 Sub-Category: {classification.get('subCategory', 'N/A')}")
            print(f"🚨 Urgency: {classification.get('urgency', 'N/A')}")
            print(f"😟 Emotional State: {classification.get('emotionalState', 'N/A')}")
            
            recommendation = classification.get('recommendation', '')
            print(f"\n💡 Recommendation length: {len(recommendation)} characters")
            
            if len(recommendation) < 500:
                print(f"⚠️  WARNING: Recommendation is too short ({len(recommendation)} chars, should be 500+)")
            else:
                print(f"✓ Recommendation is detailed ({len(recommendation)} chars)")
            
            if "consult a lawyer" in recommendation.lower() or "consult with a legal professional" in recommendation.lower():
                print("❌ PROBLEM: Recommendation contains generic 'consult a lawyer' advice!")
            else:
                print("✓ Recommendation does not contain generic advice")
            
            print(f"\n📄 Next Steps: {len(classification.get('nextSteps', []))} items")
            print(f"📎 Required Documents: {len(classification.get('requiredDocuments', []))} items")
            print(f"💰 Estimated Cost: {classification.get('estimatedCost', 'N/A')}")
            print(f"⏱️  Timeline: {classification.get('timeline', 'N/A')}")
            
            # Show full response for debugging
            print("\n" + "=" * 80)
            print("FULL CLASSIFICATION JSON")
            print("=" * 80)
            print(json.dumps(classification, indent=2, ensure_ascii=False))
            
        except json.JSONDecodeError as e:
            print(f"\n❌ JSON PARSE ERROR: {str(e)}")
            print(f"\nFull response text:")
            print(response_text)
            
    except Exception as e:
        print(f"\n❌ ERROR calling Groq API: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_voice_triage()
