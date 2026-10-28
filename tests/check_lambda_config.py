#!/usr/bin/env python3
"""
Script to check Lambda function configuration and permissions
"""

import boto3
import json

# Initialize clients
lambda_client = boto3.client('lambda', region_name='ap-south-2')
iam_client = boto3.client('iam', region_name='ap-south-2')

FUNCTION_NAME = 'NyayaDwarpal-PetitionArchitect'

def check_lambda_config():
    """Check Lambda function configuration"""
    
    try:
        # Get function configuration
        response = lambda_client.get_function(FunctionName=FUNCTION_NAME)
        
        config = response['Configuration']
        
        print("=== Lambda Function Configuration ===\n")
        print(f"Function Name: {config['FunctionName']}")
        print(f"Runtime: {config['Runtime']}")
        print(f"Handler: {config['Handler']}")
        print(f"Memory: {config['MemorySize']} MB")
        print(f"Timeout: {config['Timeout']} seconds")
        print(f"Role: {config['Role']}")
        
        print("\n=== Environment Variables ===")
        env_vars = config.get('Environment', {}).get('Variables', {})
        for key, value in env_vars.items():
            # Mask sensitive values
            if 'KEY' in key or 'SECRET' in key:
                value = '***MASKED***'
            print(f"  {key}: {value}")
        
        print("\n=== Layers ===")
        layers = config.get('Layers', [])
        if layers:
            for layer in layers:
                print(f"  - {layer['Arn']}")
        else:
            print("  No layers attached")
        
        # Get role name from ARN
        role_arn = config['Role']
        role_name = role_arn.split('/')[-1]
        
        print(f"\n=== IAM Role Permissions ({role_name}) ===")
        
        # Get attached policies
        try:
            policies_response = iam_client.list_attached_role_policies(RoleName=role_name)
            
            print("\nAttached Managed Policies:")
            for policy in policies_response['AttachedPolicies']:
                print(f"  - {policy['PolicyName']}")
            
            # Get inline policies
            inline_response = iam_client.list_role_policies(RoleName=role_name)
            
            if inline_response['PolicyNames']:
                print("\nInline Policies:")
                for policy_name in inline_response['PolicyNames']:
                    print(f"  - {policy_name}")
                    
                    # Get policy document
                    policy_doc_response = iam_client.get_role_policy(
                        RoleName=role_name,
                        PolicyName=policy_name
                    )
                    
                    policy_doc = policy_doc_response['PolicyDocument']
                    
                    print(f"\n    Statements:")
                    for statement in policy_doc.get('Statement', []):
                        actions = statement.get('Action', [])
                        if isinstance(actions, str):
                            actions = [actions]
                        
                        print(f"      Effect: {statement.get('Effect')}")
                        print(f"      Actions:")
                        for action in actions:
                            print(f"        - {action}")
                        
                        resources = statement.get('Resource', [])
                        if isinstance(resources, str):
                            resources = [resources]
                        print(f"      Resources: {', '.join(resources[:3])}{'...' if len(resources) > 3 else ''}")
                        print()
        
        except Exception as e:
            print(f"  Error fetching IAM permissions: {str(e)}")
        
        print("\n=== Recent Invocations ===")
        
        # Get CloudWatch metrics
        cloudwatch = boto3.client('cloudwatch', region_name='ap-south-2')
        from datetime import datetime, timedelta
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=1)
        
        metrics_response = cloudwatch.get_metric_statistics(
            Namespace='AWS/Lambda',
            MetricName='Invocations',
            Dimensions=[{'Name': 'FunctionName', 'Value': FUNCTION_NAME}],
            StartTime=start_time,
            EndTime=end_time,
            Period=3600,
            Statistics=['Sum']
        )
        
        if metrics_response['Datapoints']:
            for datapoint in metrics_response['Datapoints']:
                print(f"  Invocations (last hour): {int(datapoint['Sum'])}")
        else:
            print("  No invocations in the last hour")
        
        # Check for errors
        errors_response = cloudwatch.get_metric_statistics(
            Namespace='AWS/Lambda',
            MetricName='Errors',
            Dimensions=[{'Name': 'FunctionName', 'Value': FUNCTION_NAME}],
            StartTime=start_time,
            EndTime=end_time,
            Period=3600,
            Statistics=['Sum']
        )
        
        if errors_response['Datapoints']:
            for datapoint in errors_response['Datapoints']:
                error_count = int(datapoint['Sum'])
                if error_count > 0:
                    print(f"  Errors (last hour): {error_count}")
        
    except lambda_client.exceptions.ResourceNotFoundException:
        print(f"Lambda function '{FUNCTION_NAME}' not found")
    except Exception as e:
        print(f"Error checking Lambda configuration: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_lambda_config()
