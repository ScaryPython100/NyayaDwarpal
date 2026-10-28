"""
Nyaya-Dwarpal AI Agent - Main CDK Stack

This stack defines the core infrastructure for the Nyaya-Dwarpal AI Agent system,
including S3 buckets, DynamoDB tables, API Gateway, Lambda functions, and Step Functions.
"""

import os
from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_dynamodb as dynamodb,
    aws_apigateway as apigateway,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_logs as logs,
    RemovalPolicy,
    Duration,
)
from constructs import Construct


class NyayaDwarpalStack(Stack):
    """
    Main CDK Stack for Nyaya-Dwarpal AI Agent
    
    This stack creates:
    - S3 buckets for document storage
    - DynamoDB tables for metadata
    - API Gateway for REST endpoints
    - Lambda functions for each feature
    - IAM roles and policies
    - CloudWatch log groups
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ========================================
        # S3 Buckets
        # ========================================
        
        # Document upload bucket (V2 - renamed to avoid cleanup conflict)
        self.document_bucket = s3.Bucket(
            self,
            "NyayaDocBucketV2",
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldVersions",
                    noncurrent_version_expiration=Duration.days(90),
                )
            ],
        )

        # Archive bucket for processed documents (V2 - renamed to avoid cleanup conflict)
        self.archive_bucket = s3.Bucket(
            self,
            "NyayaArchiveBucketV2",
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="TransitionToGlacier",
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after=Duration.days(90),
                        )
                    ],
                )
            ],
        )

        # ========================================
        # DynamoDB Tables
        # ========================================
        
        # Document metadata table
        self.document_table = dynamodb.Table(
            self,
            "DocumentMetadataTable",
            partition_key=dynamodb.Attribute(
                name="documentId",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.RETAIN,
            time_to_live_attribute="ttl",
        )
        
        # Add GSI for case number queries
        self.document_table.add_global_secondary_index(
            index_name="CaseNumberIndex",
            partition_key=dynamodb.Attribute(
                name="caseNumber",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="filingTimestamp",
                type=dynamodb.AttributeType.STRING
            ),
        )

        # Add GSI for status queries
        self.document_table.add_global_secondary_index(
            index_name="StatusIndex",
            partition_key=dynamodb.Attribute(
                name="status",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="filingTimestamp",
                type=dynamodb.AttributeType.STRING
            ),
        )

        # User sessions table for conversational state
        self.session_table = dynamodb.Table(
            self,
            "SessionTable",
            partition_key=dynamodb.Attribute(
                name="sessionId",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            removal_policy=RemovalPolicy.RETAIN,
            time_to_live_attribute="ttl",
        )
        
        # Legal glossary table
        self.glossary_table = dynamodb.Table(
            self,
            "GlossaryTable",
            partition_key=dynamodb.Attribute(
                name="term",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="language",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            removal_policy=RemovalPolicy.RETAIN,
        )
        
        # ========================================
        
        # Lambda execution role with Bedrock access
        self.lambda_role = iam.Role(
            self,
            "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AWSXRayDaemonWriteAccess"
                ),
            ],
        )

        # Grant Bedrock access
        self.lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=["*"],  # Bedrock models
            )
        )

        # Grant Textract access
        self.lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "textract:AnalyzeDocument",
                    "textract:DetectDocumentText",
                ],
                resources=["*"],
            )
        )

        # Grant Kendra access
        self.lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "kendra:Query",
                    "kendra:Retrieve",
                ],
                resources=["*"],  # Kendra index ARN will be added later
            )
        )

        # Grant S3 access
        self.document_bucket.grant_read_write(self.lambda_role)
        self.archive_bucket.grant_read_write(self.lambda_role)

        # Grant DynamoDB access
        self.document_table.grant_read_write_data(self.lambda_role)
        self.session_table.grant_read_write_data(self.lambda_role)
        self.glossary_table.grant_read_write_data(self.lambda_role)

        # ========================================
        # API Gateway
        # ========================================
        
        # Create REST API
        self.api = apigateway.RestApi(
            self,
            "NyayaDwarpalApi",
            rest_api_name="Nyaya-Dwarpal AI Agent API",
            description="REST API for Nyaya-Dwarpal AI Agent",
            deploy_options=apigateway.StageOptions(
                stage_name="prod",
                logging_level=apigateway.MethodLoggingLevel.INFO,
                data_trace_enabled=True,
                tracing_enabled=True,
            ),
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=apigateway.Cors.ALL_ORIGINS,
                allow_methods=apigateway.Cors.ALL_METHODS,
                allow_headers=[
                    "Content-Type",
                    "X-Amz-Date",
                    "Authorization",
                    "X-Api-Key",
                    "X-Amz-Security-Token"
                ],
            ),
        )

        # Create API resources (endpoints will be added in feature-specific constructs)
        self.voice_resource = self.api.root.add_resource("voice")
        self.petition_resource = self.api.root.add_resource("petition")
        self.translate_resource = self.api.root.add_resource("translate")
        self.review_resource = self.api.root.add_resource("review")
        self.validate_resource = self.api.root.add_resource("validate")

        # ========================================
        # CloudWatch Log Groups
        # ========================================
        
        # Create log group for API Gateway
        self.api_log_group = logs.LogGroup(
            self,
            "ApiLogGroup",
            log_group_name=f"/aws/apigateway/nyaya-dwarpal",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ========================================
        # Lambda Layer for Shared Code
        # ========================================
        
        # Create Lambda layer with shared utilities
        self.shared_layer = lambda_.LayerVersion(
            self,
            "SharedLayer",
            layer_version_name="NyayaDwarpal-Shared",
            code=lambda_.Code.from_asset("lambda_functions/shared"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_11],
            description="Shared utilities for Nyaya-Dwarpal Lambda functions",
        )

        # ========================================
        # Lambda Functions
        # ========================================
        
        # Voice Triage Lambda
        self.voice_triage_lambda = lambda_.Function(
            self,
            "VoiceTriageLambda",
            function_name="NyayaDwarpal-VoiceTriage",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("lambda_functions/voice_triage"),
            role=self.lambda_role,
            layers=[self.shared_layer],
            timeout=Duration.seconds(30),
            memory_size=512,
            environment={
                "DOCUMENT_BUCKET": self.document_bucket.bucket_name,
                "SESSION_TABLE": self.session_table.table_name,
                "BEDROCK_REGION": "us-east-1",
                "SARVAM_AI_ENDPOINT": "https://api.sarvam.ai/v1",
                "GROQ_API_KEY": os.environ.get("GROQ_API_KEY", ""),
            },
            tracing=lambda_.Tracing.ACTIVE,
        )
        
        # Document Translation Lambda
        self.translation_lambda = lambda_.Function(
            self,
            "DocumentTranslationLambda",
            function_name="NyayaDwarpal-DocumentTranslation",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("lambda_functions/document_translator"),
            role=self.lambda_role,
            layers=[self.shared_layer],
            timeout=Duration.seconds(60),
            memory_size=1024,
            environment={
                "DOCUMENT_BUCKET": self.document_bucket.bucket_name,
                "ARCHIVE_BUCKET": self.archive_bucket.bucket_name,
                "GLOSSARY_TABLE": self.glossary_table.table_name,
                "SARVAM_AI_ENDPOINT": "https://api.sarvam.ai",
                "SARVAM_AI_API_KEY": os.environ.get("SARVAM_API_KEY", ""),
            },
            tracing=lambda_.Tracing.ACTIVE,
        )
        
        # Petition Architect Lambda
        self.petition_architect_lambda = lambda_.Function(
            self,
            "PetitionArchitectLambda",
            function_name="NyayaDwarpal-PetitionArchitect",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("lambda_functions/petition_architect"),
            role=self.lambda_role,
            layers=[self.shared_layer],
            timeout=Duration.seconds(60),
            memory_size=1024,
            environment={
                "DOCUMENT_BUCKET": self.document_bucket.bucket_name,
                "DOCUMENT_TABLE": self.document_table.table_name,
                "SESSION_TABLE": self.session_table.table_name,
                "BEDROCK_REGION": "us-east-1",
            },
            tracing=lambda_.Tracing.ACTIVE,
        )
        
        # Case Memory Lambda
        self.case_memory_lambda = lambda_.Function(
            self,
            "CaseMemoryLambda",
            function_name="NyayaDwarpal-CaseMemory",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("lambda_functions/case_memory"),
            role=self.lambda_role,
            layers=[self.shared_layer],
            timeout=Duration.seconds(30),
            memory_size=512,
            environment={
                "SESSION_TABLE": self.session_table.table_name,
            },
            tracing=lambda_.Tracing.ACTIVE,
        )
        
        # Audio Transcribe Lambda Layer (with requests library)
        self.audio_transcribe_layer = lambda_.LayerVersion(
            self,
            "AudioTranscribeLayer",
            layer_version_name="NyayaDwarpal-AudioTranscribe-Dependencies",
            code=lambda_.Code.from_asset("lambda_functions/audio_transcribe"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_11],
            description="Dependencies for Audio Transcribe Lambda (requests library)",
        )
        
        # Audio Transcribe Lambda
        self.audio_transcribe_lambda = lambda_.Function(
            self,
            "AudioTranscribeLambda",
            function_name="NyayaDwarpal-AudioTranscribe",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("lambda_functions/audio_transcribe"),
            role=self.lambda_role,
            layers=[self.audio_transcribe_layer],
            timeout=Duration.seconds(60),
            memory_size=512,
            environment={
                "SARVAM_API_KEY": os.environ.get("SARVAM_API_KEY", ""),
            },
            tracing=lambda_.Tracing.ACTIVE,
        )
        
        # Document Verifier Lambda
        self.document_verifier_lambda = lambda_.Function(
            self,
            "DocumentVerifierLambda",
            function_name="NyayaDwarpal-DocumentVerifier",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("lambda_functions/document_verifier"),
            role=self.lambda_role,
            layers=[self.shared_layer],
            timeout=Duration.seconds(60),
            memory_size=1024,
            environment={
                "GROQ_API_KEY": os.environ.get("GROQ_API_KEY", ""),
            },
            tracing=lambda_.Tracing.ACTIVE,
        )
        
        # ========================================
        # API Gateway Integrations
        # ========================================
        
        # Voice Triage endpoint: POST /voice/triage
        triage_integration = apigateway.LambdaIntegration(self.voice_triage_lambda)
        triage_method = self.voice_resource.add_resource("triage")
        triage_method.add_method("POST", triage_integration)
        
        # Document Translation endpoint: POST /translate/document
        translate_integration = apigateway.LambdaIntegration(self.translation_lambda)
        translate_method = self.translate_resource.add_resource("document")
        translate_method.add_method("POST", translate_integration)
        
        # Petition Architect endpoints
        # POST /petition/generate
        petition_integration = apigateway.LambdaIntegration(self.petition_architect_lambda)
        petition_generate = self.petition_resource.add_resource("generate")
        petition_generate.add_method("POST", petition_integration)
        
        # POST /petition/clarify
        petition_clarify = self.petition_resource.add_resource("clarify")
        petition_clarify.add_method("POST", petition_integration)
        
        # Case Memory endpoint: GET /cases
        cases_resource = self.api.root.add_resource("cases")
        case_memory_integration = apigateway.LambdaIntegration(self.case_memory_lambda)
        cases_resource.add_method("GET", case_memory_integration)
        
        # Audio Transcribe endpoint: POST /transcribe
        transcribe_resource = self.api.root.add_resource(
            "transcribe",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=["*"],
                allow_methods=["POST", "OPTIONS"],
                allow_headers=[
                    "Content-Type",
                    "X-Amz-Date",
                    "Authorization",
                    "X-Api-Key",
                    "X-Amz-Security-Token"
                ],
            )
        )
        audio_transcribe_integration = apigateway.LambdaIntegration(
            self.audio_transcribe_lambda,
            proxy=True,
            integration_responses=[
                apigateway.IntegrationResponse(
                    status_code="200",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": "'*'"
                    }
                )
            ]
        )
        transcribe_resource.add_method(
            "POST",
            audio_transcribe_integration,
            method_responses=[
                apigateway.MethodResponse(
                    status_code="200",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True
                    }
                )
            ]
        )
        
        # Document Verifier endpoint: POST /verify/document
        verify_resource = self.validate_resource.add_resource("document")
        document_verifier_integration = apigateway.LambdaIntegration(
            self.document_verifier_lambda,
            proxy=True
        )
        verify_resource.add_method("POST", document_verifier_integration)
        
        # ========================================
        # Outputs
        # ========================================
        
        # Export important values
        from aws_cdk import CfnOutput
        
        CfnOutput(
            self,
            "ApiEndpoint",
            value=self.api.url,
            description="API Gateway endpoint URL",
        )
        
        CfnOutput(
            self,
            "VoiceTriageEndpoint",
            value=f"{self.api.url}voice/triage",
            description="Voice Triage API endpoint",
        )
        
        CfnOutput(
            self,
            "TranslationEndpoint",
            value=f"{self.api.url}translate/document",
            description="Document Translation API endpoint",
        )
        
        CfnOutput(
            self,
            "PetitionGenerateEndpoint",
            value=f"{self.api.url}petition/generate",
            description="Petition Generation API endpoint",
        )
        
        CfnOutput(
            self,
            "PetitionClarifyEndpoint",
            value=f"{self.api.url}petition/clarify",
            description="Petition Clarification API endpoint",
        )
        
        CfnOutput(
            self,
            "CasesEndpoint",
            value=f"{self.api.url}cases",
            description="Case Memory API endpoint",
        )
        
        CfnOutput(
            self,
            "TranscribeEndpoint",
            value=f"{self.api.url}transcribe",
            description="Audio Transcribe API endpoint",
        )
        
        CfnOutput(
            self,
            "DocumentVerifierEndpoint",
            value=f"{self.api.url}validate/document",
            description="Document Verifier API endpoint",
        )
        
        CfnOutput(
            self,
            "DocumentBucketName",
            value=self.document_bucket.bucket_name,
            description="S3 bucket for document uploads",
        )
        
        CfnOutput(
            self,
            "DocumentTableName",
            value=self.document_table.table_name,
            description="DynamoDB table for document metadata",
        )

