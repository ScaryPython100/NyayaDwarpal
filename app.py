#!/usr/bin/env python3
"""
Nyaya-Dwarpal AI Agent - AWS CDK Application Entry Point

This is the main CDK application file that defines the infrastructure
for the Nyaya-Dwarpal AI Agent system.
"""

import os

import aws_cdk as cdk
from infrastructure.nyaya_dwarpal_stack import NyayaDwarpalStack

app = cdk.App()

# The Lambdas get the Sarvam key at deploy time; deploying without it would blank the live key
if not os.environ.get("SARVAM_API_KEY") and not app.node.try_get_context("allowMissingKeys"):
    raise SystemExit(
        "SARVAM_API_KEY is not set. Run `set -a; source .env; set +a` first "
        "(or pass -c allowMissingKeys=true to synth without it)."
    )

# Create the main stack
NyayaDwarpalStack(
    app,
    "NyayaDwarpalStack",
    description="Nyaya-Dwarpal AI Agent - Voice-first legal assistance system for India",
    env=cdk.Environment(
        account=app.node.try_get_context("account"),
        region=app.node.try_get_context("region") or "ap-south-2"  #Hyderabad region
    )
)

app.synth()
