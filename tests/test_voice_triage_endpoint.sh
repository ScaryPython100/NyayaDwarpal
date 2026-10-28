#!/bin/bash

# Test Voice Triage Endpoint
# This script tests the deployed Lambda via API Gateway

echo "=========================================="
echo "Voice Triage Endpoint Test"
echo "=========================================="
echo ""

# Get API Gateway URL from CDK outputs
echo "Looking for API Gateway URL..."
API_URL=$(aws cloudformation describe-stacks \
    --stack-name NyayaDwarpalStack \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
    --output text 2>/dev/null)

if [ -z "$API_URL" ]; then
    echo "❌ Could not find API Gateway URL from CloudFormation"
    echo ""
    echo "Please provide the API Gateway URL manually:"
    read -p "API URL: " API_URL
    echo ""
fi

echo "✓ API URL: $API_URL"
echo ""

# Test query
TEST_QUERY="Auto wale ne meter se 3 guna paisa manga"
echo "Test Query: $TEST_QUERY"
echo "Language: Hindi (hi)"
echo ""

# Make request
echo "=========================================="
echo "Sending Request..."
echo "=========================================="
echo ""

RESPONSE=$(curl -s -X POST "${API_URL}voice-triage" \
    -H "Content-Type: application/json" \
    -d "{
        \"userId\": \"test-user-$(date +%s)\",
        \"transcribedText\": \"$TEST_QUERY\",
        \"language\": \"hi\",
        \"useNativeScript\": true
    }")

echo "Response received!"
echo ""

# Parse and display results
echo "=========================================="
echo "Results"
echo "=========================================="
echo ""

# Check if response is valid JSON
if echo "$RESPONSE" | jq . > /dev/null 2>&1; then
    # Extract key fields
    SUCCESS=$(echo "$RESPONSE" | jq -r '.success')
    CATEGORY=$(echo "$RESPONSE" | jq -r '.data.classification.category // "N/A"')
    SUB_CATEGORY=$(echo "$RESPONSE" | jq -r '.data.classification.subCategory // "N/A"')
    URGENCY=$(echo "$RESPONSE" | jq -r '.data.emotion.urgency // "N/A"')
    RECOMMENDATION=$(echo "$RESPONSE" | jq -r '.data.recommendation // "N/A"')
    
    echo "Success: $SUCCESS"
    echo ""
    echo "📋 Category: $CATEGORY"
    echo "📝 Sub-Category: $SUB_CATEGORY"
    echo "🚨 Urgency: $URGENCY"
    echo ""
    echo "💡 Recommendation (first 200 chars):"
    echo "${RECOMMENDATION:0:200}..."
    echo ""
    
    # Check for success
    if [ "$CATEGORY" = "Other" ]; then
        echo "❌ FAILED: Category is 'Other'"
        echo ""
        echo "This means the GROQ_API_KEY is still not set or there's an error."
        echo "Check CloudWatch logs for details."
    elif [[ "$CATEGORY" == *"Consumer"* ]]; then
        echo "✅ SUCCESS: Category correctly identified as Consumer Rights!"
        echo ""
        echo "The fix is working! 🎉"
    else
        echo "⚠️  Category is '$CATEGORY' (not 'Other' but also not Consumer Rights)"
    fi
    
    echo ""
    echo "=========================================="
    echo "Full Response"
    echo "=========================================="
    echo ""
    echo "$RESPONSE" | jq .
    
else
    echo "❌ Invalid JSON response:"
    echo "$RESPONSE"
fi

echo ""
echo "=========================================="
echo "CloudWatch Logs"
echo "=========================================="
echo ""
echo "To check logs, run:"
echo "  aws logs tail /aws/lambda/NyayaDwarpalStack-VoiceTriageFunction --follow"
echo ""
