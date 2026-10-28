#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Petition Verifier - Diagnostic Tool${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Step 1: Check Lambda Configuration
echo -e "${YELLOW}Step 1: Checking Lambda Configuration...${NC}"
echo ""
python3 check_lambda_config.py
echo ""
echo -e "${GREEN}✓ Configuration check complete${NC}"
echo ""
read -p "Press Enter to continue to logs..."
echo ""

# Step 2: Check CloudWatch Logs
echo -e "${YELLOW}Step 2: Checking CloudWatch Logs...${NC}"
echo ""
python3 check_lambda_logs.py > /tmp/lambda_logs.txt
cat /tmp/lambda_logs.txt
echo ""

# Check for common errors in logs
if grep -q "ModuleNotFoundError.*pydantic" /tmp/lambda_logs.txt; then
    echo -e "${RED}❌ Found Issue: Missing pydantic module${NC}"
    echo ""
    echo -e "${YELLOW}This is a Lambda layer issue. The pydantic library is not installed correctly.${NC}"
    echo ""
    echo -e "${GREEN}Recommended Fix:${NC}"
    echo "  ./deploy_petition_verifier.sh"
    echo ""
    read -p "Do you want to run the fix now? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo ""
        echo -e "${YELLOW}Running deployment fix...${NC}"
        ./deploy_petition_verifier.sh
        echo ""
        echo -e "${GREEN}✓ Deployment complete. Testing API...${NC}"
        echo ""
        python3 test_petition_verifier.py
        exit 0
    fi
elif grep -q "AccessDeniedException" /tmp/lambda_logs.txt; then
    echo -e "${RED}❌ Found Issue: Access Denied${NC}"
    echo ""
    echo -e "${YELLOW}The Lambda function doesn't have permission to access a service.${NC}"
    echo ""
    SERVICE=$(grep -o "AccessDeniedException.*" /tmp/lambda_logs.txt | head -1)
    echo "Error: $SERVICE"
    echo ""
    echo -e "${GREEN}Recommended Fix:${NC}"
    echo "  Check IAM permissions in the output above."
    echo "  Permissions should already be configured correctly."
    echo "  Wait a few minutes for IAM propagation, then test again."
    echo ""
elif grep -q "Error" /tmp/lambda_logs.txt || grep -q "Exception" /tmp/lambda_logs.txt; then
    echo -e "${RED}❌ Found Issue: Other Error${NC}"
    echo ""
    echo -e "${YELLOW}Check the error message above for details.${NC}"
    echo ""
    echo -e "${GREEN}Recommended Fix:${NC}"
    echo "  Review the error message and stack trace above."
    echo "  Refer to TROUBLESHOOTING_GUIDE.md for solutions."
    echo ""
else
    echo -e "${GREEN}✓ No obvious errors found in logs${NC}"
    echo ""
fi

read -p "Press Enter to continue to API test..."
echo ""

# Step 3: Test API
echo -e "${YELLOW}Step 3: Testing API Endpoint...${NC}"
echo ""
python3 test_petition_verifier.py > /tmp/api_test.txt
cat /tmp/api_test.txt
echo ""

# Check API test results
if grep -q "Status Code: 200" /tmp/api_test.txt; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✓ SUCCESS! API is working correctly${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "The Petition Verifier Lambda is functioning properly."
    echo ""
elif grep -q "Status Code: 500" /tmp/api_test.txt; then
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}❌ API returned 500 error${NC}"
    echo -e "${RED}========================================${NC}"
    echo ""
    echo "The Lambda is still returning errors. Review the logs above."
    echo ""
    echo -e "${GREEN}Next Steps:${NC}"
    echo "  1. Check the error message in the API response above"
    echo "  2. Review the CloudWatch logs for stack traces"
    echo "  3. Refer to TROUBLESHOOTING_GUIDE.md for solutions"
    echo ""
elif grep -q "Status Code: 400" /tmp/api_test.txt; then
    echo -e "${YELLOW}========================================${NC}"
    echo -e "${YELLOW}⚠ API returned 400 error${NC}"
    echo -e "${YELLOW}========================================${NC}"
    echo ""
    echo "This is a client error (bad request format)."
    echo "Check the request payload in the test script."
    echo ""
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}❌ Unable to reach API${NC}"
    echo -e "${RED}========================================${NC}"
    echo ""
    echo "Could not connect to the API endpoint."
    echo "Check that the endpoint URL is correct in test_petition_verifier.py"
    echo ""
fi

# Cleanup
rm -f /tmp/lambda_logs.txt /tmp/api_test.txt

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Diagnostic Complete${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "For more help, see:"
echo "  - QUICK_FIX_CHECKLIST.md"
echo "  - TROUBLESHOOTING_GUIDE.md"
echo "  - DIAGNOSTIC_TOOLS_README.md"
echo ""
