#!/bin/bash
set -e

echo "=== Deploying Petition Verifier Lambda ==="

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Step 1: Installing dependencies for shared layer${NC}"
cd lambda_functions/shared
pip install -r requirements.txt -t python/ --upgrade
cd ../..

echo -e "${YELLOW}Step 2: Synthesizing CDK stack${NC}"
npx cdk synth

echo -e "${YELLOW}Step 3: Deploying to AWS${NC}"
npx cdk deploy --require-approval never

echo -e "${GREEN}Deployment complete!${NC}"
echo ""
echo "Test your API with:"
echo "  python3 test_petition_verifier.py"
echo ""
echo "Check logs with:"
echo "  python3 check_lambda_logs.py"
