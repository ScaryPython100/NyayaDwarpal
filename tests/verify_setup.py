#!/usr/bin/env python3
"""
Verification script for Task 1 setup

This script verifies that all components of Task 1 are properly configured.
"""

import sys
import os
from pathlib import Path


def check_file_exists(filepath: str) -> bool:
    """Check if a file exists"""
    exists = Path(filepath).exists()
    status = "✅" if exists else "❌"
    print(f"{status} {filepath}")
    return exists


def check_directory_exists(dirpath: str) -> bool:
    """Check if a directory exists"""
    exists = Path(dirpath).is_dir()
    status = "✅" if exists else "❌"
    print(f"{status} {dirpath}/")
    return exists


def main():
    """Run verification checks"""
    print("=" * 60)
    print("Nyaya-Dwarpal Task 1 Verification")
    print("=" * 60)
    
    all_checks_passed = True
    
    # Check core files
    print("\n📄 Core Configuration Files:")
    all_checks_passed &= check_file_exists("app.py")
    all_checks_passed &= check_file_exists("cdk.json")
    all_checks_passed &= check_file_exists("requirements.txt")
    all_checks_passed &= check_file_exists(".gitignore")
    all_checks_passed &= check_file_exists("README.md")
    
    # Check infrastructure
    print("\n🏗️  Infrastructure Code:")
    all_checks_passed &= check_directory_exists("infrastructure")
    all_checks_passed &= check_file_exists("infrastructure/__init__.py")
    all_checks_passed &= check_file_exists("infrastructure/nyaya_dwarpal_stack.py")
    
    # Check Lambda functions
    print("\n⚡ Lambda Functions:")
    all_checks_passed &= check_directory_exists("lambda_functions")
    all_checks_passed &= check_file_exists("lambda_functions/__init__.py")
    all_checks_passed &= check_directory_exists("lambda_functions/shared")
    all_checks_passed &= check_file_exists("lambda_functions/shared/__init__.py")
    all_checks_passed &= check_file_exists("lambda_functions/shared/bedrock_client.py")
    all_checks_passed &= check_file_exists("lambda_functions/shared/models.py")
    all_checks_passed &= check_file_exists("lambda_functions/shared/aws_helpers.py")
    
    # Check tests
    print("\n🧪 Test Infrastructure:")
    all_checks_passed &= check_directory_exists("tests")
    all_checks_passed &= check_file_exists("tests/__init__.py")
    all_checks_passed &= check_directory_exists("tests/unit")
    all_checks_passed &= check_file_exists("tests/unit/__init__.py")
    all_checks_passed &= check_file_exists("tests/unit/test_bedrock_client.py")
    
    # Check Python imports
    print("\n🐍 Python Import Checks:")
    try:
        from infrastructure.nyaya_dwarpal_stack import NyayaDwarpalStack
        print("✅ infrastructure.nyaya_dwarpal_stack")
    except ImportError as e:
        print(f"❌ infrastructure.nyaya_dwarpal_stack: {e}")
        all_checks_passed = False
    
    try:
        from lambda_functions.shared.bedrock_client import BedrockClient
        print("✅ lambda_functions.shared.bedrock_client")
    except ImportError as e:
        print(f"❌ lambda_functions.shared.bedrock_client: {e}")
        all_checks_passed = False
    
    try:
        from lambda_functions.shared.models import DocumentMetadata, TriageResult
        print("✅ lambda_functions.shared.models")
    except ImportError as e:
        print(f"❌ lambda_functions.shared.models: {e}")
        all_checks_passed = False
    
    try:
        from lambda_functions.shared.aws_helpers import S3Helper, DynamoDBHelper
        print("✅ lambda_functions.shared.aws_helpers")
    except ImportError as e:
        print(f"❌ lambda_functions.shared.aws_helpers: {e}")
        all_checks_passed = False
    
    # Summary
    print("\n" + "=" * 60)
    if all_checks_passed:
        print("✅ All checks passed! Task 1 setup is complete.")
        print("\nNext steps:")
        print("1. Review the code in TASK_1_SUMMARY.md")
        print("2. Install dependencies: pip install -r requirements.txt")
        print("3. Run tests: pytest tests/unit/")
        print("4. Deploy infrastructure: cdk deploy")
        return 0
    else:
        print("❌ Some checks failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
