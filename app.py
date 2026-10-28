#!/usr/bin/env python3
"""
Nyaya-Dwarpal AI Agent - AWS CDK Application Entry Point

This is the main CDK application file that defines the infrastructure
for the Nyaya-Dwarpal AI Agent system.
"""

import aws_cdk as cdk
from infrastructure.nyaya_dwarpal_stack import NyayaDwarpalStack

app = cdk.App()

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
