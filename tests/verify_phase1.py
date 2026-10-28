#!/usr/bin/env python3
"""
Phase 1 Verification Script

This script verifies that all Phase 1 components are in place and ready for deployment.
"""

import os
import sys
from pathlib import Path


def check_file_exists(filepath: str, description: str) -> bool:
    """Check if a file exists"""
    if Path(filepath).exists():
        print(f"✅ {description}: {filepath}")
        return True
    else:
        print(f"❌ {description}: {filepath} NOT FOUND")
        return False


def check_directory_exists(dirpath: str, description: str) -> bool:
    """Check if a directory exists"""
    if Path(dirpath).is_dir():
        print(f"✅ {description}: {dirpath}")
        return True
    else:
        print(f"❌ {description}: {dirpath} NOT FOUND")
        return False


def main():
    """Run verification checks"""
    print("=" * 60)
    print("Phase 1 Verification")
    print("=" * 60)
    print()
    
    all_checks_passed = True
    
    # Check CDK infrastructure
    print("📦 CDK Infrastructure")
    print("-" * 60)
    all_checks_passed &= check_file_exists("app.py", "CDK app entry point")
    all_checks_passed &= check_file_exists("cdk.json", "CDK configuration")
    all_checks_passed &= check_file_exists("infrastructure/nyaya_dwarpal_stack.py", "Main CDK stack")
    print()
    
    # Check Lambda functions
    print("⚡ Lambda Functions")
    print("-" * 60)
    all_checks_passed &= check_directory_exists("lambda_functions/voice_triage", "Voice Triage Lambda")
    all_checks_passed &= check_file_exists("lambda_functions/voice_triage/handler.py", "Voice Triage handler")
    all_checks_passed &= check_file_exists("lambda_functions/voice_triage/requirements.txt", "Voice Triage requirements")
    print()
    
    all_checks_passed &= check_directory_exists("lambda_functions/document_translator", "Document Translator Lambda")
    all_checks_passed &= check_file_exists("lambda_functions/document_translator/handler.py", "Document Translator handler")
    all_checks_passed &= check_file_exists("lambda_functions/document_translator/requirements.txt", "Document Translator requirements")
    print()
    
    # Check shared utilities
    print("🔧 Shared Utilities (Lambda Layer)")
    print("-" * 60)
    all_checks_passed &= check_directory_exists("lambda_functions/shared", "Shared utilities")
    all_checks_passed &= check_file_exists("lambda_functions/shared/bedrock_client.py", "Bedrock client")
    all_checks_passed &= check_file_exists("lambda_functions/shared/models.py", "Data models")
    all_checks_passed &= check_file_exists("lambda_functions/shared/aws_helpers.py", "AWS helpers")
    all_checks_passed &= check_file_exists("lambda_functions/shared/requirements.txt", "Shared requirements")
    print()
    
    # Check test infrastructure
    print("🧪 Test Infrastructure")
    print("-" * 60)
    all_checks_passed &= check_directory_exists("tests", "Tests directory")
    all_checks_passed &= check_directory_exists("tests/unit", "Unit tests directory")
    all_checks_passed &= check_file_exists("tests/unit/test_bedrock_client.py", "Bedrock client tests")
    print()
    
    # Check dependencies
    print("📚 Dependencies")
    print("-" * 60)
    all_checks_passed &= check_file_exists("requirements.txt", "Project requirements")
    print()
    
    # Check Python version
    print("🐍 Python Version")
    print("-" * 60)
    python_version = sys.version_info
    if python_version >= (3, 11):
        print(f"✅ Python {python_version.major}.{python_version.minor}.{python_version.micro}")
    else:
        print(f"⚠️  Python {python_version.major}.{python_version.minor}.{python_version.micro} (Recommended: 3.11+)")
    print()
    
    # Check for virtual environment
    print("🌐 Virtual Environment")
    print("-" * 60)
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("✅ Virtual environment is active")
    else:
        print("⚠️  Virtual environment is NOT active (recommended)")
        print("   Run: python3 -m venv venv && source venv/bin/activate")
    print()
    
    # Summary
    print("=" * 60)
    if all_checks_passed:
        print("✅ All checks passed! Ready for deployment.")
        print()
        print("Next steps:")
        print("1. Activate virtual environment: source venv/bin/activate")
        print("2. Install dependencies: pip install -r requirements.txt")
        print("3. Configure Sarvam AI API key")
        print("4. Test CDK synthesis: cdk synth")
        print("5. Deploy to AWS: cdk deploy")
    else:
        print("❌ Some checks failed. Please review the output above.")
        return 1
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
