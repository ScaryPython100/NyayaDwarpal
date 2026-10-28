"""
AWS Service Integration Helpers

This module provides helper functions for interacting with AWS services
with retry logic and error handling.
"""

import json
import time
import boto3
from typing import Dict, Any, Optional, List
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class RetryableError(Exception):
    """Exception for errors that should be retried"""
    pass


def exponential_backoff_retry(
    func,
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 10.0,
    backoff_factor: float = 2.0,
):
    """
    Retry function with exponential backoff
    
    Args:
        func: Function to retry
        max_attempts: Maximum number of attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        backoff_factor: Backoff multiplier
        
    Returns:
        Function result
        
    Raises:
        Last exception if all attempts fail
    """
    delay = initial_delay
    last_exception = None
    
    for attempt in range(max_attempts):
        try:
            return func()
        except RetryableError as e:
            last_exception = e
            if attempt < max_attempts - 1:
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                time.sleep(delay)
                delay = min(delay * backoff_factor, max_delay)
            else:
                logger.error(f"All {max_attempts} attempts failed")
        except Exception as e:
            # Non-retryable error
            logger.error(f"Non-retryable error: {e}")
            raise
    
    raise last_exception


class S3Helper:
    """Helper for S3 operations"""
    
    def __init__(self, region: str = "ap-south-1"):
        self.client = boto3.client("s3", region_name=region)
        self.region = region
    
    def upload_file(
        self,
        file_content: bytes,
        bucket: str,
        key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Upload file to S3 with retry
        
        Args:
            file_content: File content as bytes
            bucket: S3 bucket name
            key: S3 object key
            content_type: MIME type
            
        Returns:
            S3 URI (s3://bucket/key)
        """
        def _upload():
            try:
                self.client.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=file_content,
                    ContentType=content_type,
                    ServerSideEncryption="AES256",
                )
                return f"s3://{bucket}/{key}"
            except ClientError as e:
                if e.response["Error"]["Code"] in ["ServiceUnavailable", "SlowDown"]:
                    raise RetryableError(f"S3 upload failed: {e}")
                raise
        
        return exponential_backoff_retry(_upload)
    
    def put_object(
        self,
        bucket: str,
        key: str,
        body: str,
        content_type: str = "application/json",
    ) -> str:
        """
        Put object to S3 with retry (alias for upload_file with string body)
        
        Args:
            bucket: S3 bucket name
            key: S3 object key
            body: Object content as string
            content_type: MIME type
            
        Returns:
            S3 URI (s3://bucket/key)
        """
        return self.upload_file(
            file_content=body.encode('utf-8'),
            bucket=bucket,
            key=key,
            content_type=content_type
        )
    
    def download_file(self, bucket: str, key: str) -> bytes:
        """
        Download file from S3 with retry
        
        Args:
            bucket: S3 bucket name
            key: S3 object key
            
        Returns:
            File content as bytes
        """
        def _download():
            try:
                response = self.client.get_object(Bucket=bucket, Key=key)
                return response["Body"].read()
            except ClientError as e:
                if e.response["Error"]["Code"] in ["ServiceUnavailable", "SlowDown"]:
                    raise RetryableError(f"S3 download failed: {e}")
                raise
        
        return exponential_backoff_retry(_download)
    
    def read_text_file(self, bucket: str, key: str, encoding: str = 'utf-8') -> str:
        """
        Read text file from S3 with retry
        
        Args:
            bucket: S3 bucket name
            key: S3 object key
            encoding: Text encoding (default: utf-8)
            
        Returns:
            File content as string
        """
        file_bytes = self.download_file(bucket, key)
        return file_bytes.decode(encoding)
    
    def generate_presigned_url(
        self,
        bucket: str,
        key: str,
        expiration: int = 3600,
    ) -> str:
        """
        Generate presigned URL for S3 object
        
        Args:
            bucket: S3 bucket name
            key: S3 object key
            expiration: URL expiration in seconds
            
        Returns:
            Presigned URL
        """
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expiration,
        )


class DynamoDBHelper:
    """Helper for DynamoDB operations"""
    
    def __init__(self, region: str = "ap-south-1"):
        self.client = boto3.client("dynamodb", region_name=region)
        self.resource = boto3.resource("dynamodb", region_name=region)
        self.region = region
    
    def put_item(self, table_name: str, item: Dict[str, Any]) -> None:
        """
        Put item in DynamoDB table with retry
        
        Args:
            table_name: DynamoDB table name
            item: Item to put (Python dict)
        """
        def _put():
            try:
                table = self.resource.Table(table_name)
                table.put_item(Item=item)
            except ClientError as e:
                if e.response["Error"]["Code"] in ["ProvisionedThroughputExceededException"]:
                    raise RetryableError(f"DynamoDB put failed: {e}")
                raise
        
        exponential_backoff_retry(_put)
    
    def get_item(
        self,
        table_name: str,
        key: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Get item from DynamoDB table with retry
        
        Args:
            table_name: DynamoDB table name
            key: Primary key (Python dict)
            
        Returns:
            Item if found, None otherwise
        """
        def _get():
            try:
                table = self.resource.Table(table_name)
                response = table.get_item(Key=key)
                return response.get("Item")
            except ClientError as e:
                if e.response["Error"]["Code"] in ["ProvisionedThroughputExceededException"]:
                    raise RetryableError(f"DynamoDB get failed: {e}")
                raise
        
        return exponential_backoff_retry(_get)
    
    def query_by_gsi(
        self,
        table_name: str,
        index_name: str,
        key_condition_expression: str,
        expression_attribute_values: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Query DynamoDB table by GSI with retry
        
        Args:
            table_name: DynamoDB table name
            index_name: GSI name
            key_condition_expression: Key condition expression
            expression_attribute_values: Expression attribute values
            
        Returns:
            List of items
        """
        def _query():
            try:
                table = self.resource.Table(table_name)
                response = table.query(
                    IndexName=index_name,
                    KeyConditionExpression=key_condition_expression,
                    ExpressionAttributeValues=expression_attribute_values,
                )
                return response.get("Items", [])
            except ClientError as e:
                if e.response["Error"]["Code"] in ["ProvisionedThroughputExceededException"]:
                    raise RetryableError(f"DynamoDB query failed: {e}")
                raise
        
        return exponential_backoff_retry(_query)
    
    def update_item(
        self,
        table_name: str,
        key: Dict[str, Any],
        update_expression: str,
        expression_attribute_values: Dict[str, Any],
    ) -> None:
        """
        Update item in DynamoDB table with retry
        
        Args:
            table_name: DynamoDB table name
            key: Primary key
            update_expression: Update expression
            expression_attribute_values: Expression attribute values
        """
        def _update():
            try:
                table = self.resource.Table(table_name)
                table.update_item(
                    Key=key,
                    UpdateExpression=update_expression,
                    ExpressionAttributeValues=expression_attribute_values,
                )
            except ClientError as e:
                if e.response["Error"]["Code"] in ["ProvisionedThroughputExceededException"]:
                    raise RetryableError(f"DynamoDB update failed: {e}")
                raise
        
        exponential_backoff_retry(_update)


class SNSHelper:
    """Helper for SNS operations"""
    
    def __init__(self, region: str = "ap-south-1"):
        self.client = boto3.client("sns", region_name=region)
        self.region = region
    
    def publish_message(
        self,
        topic_arn: str,
        message: str,
        subject: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Publish message to SNS topic with retry
        
        Args:
            topic_arn: SNS topic ARN
            message: Message body
            subject: Message subject
            attributes: Message attributes
            
        Returns:
            Message ID
        """
        def _publish():
            try:
                params = {
                    "TopicArn": topic_arn,
                    "Message": message,
                }
                if subject:
                    params["Subject"] = subject
                if attributes:
                    params["MessageAttributes"] = attributes
                
                response = self.client.publish(**params)
                return response["MessageId"]
            except ClientError as e:
                if e.response["Error"]["Code"] in ["ServiceUnavailable"]:
                    raise RetryableError(f"SNS publish failed: {e}")
                raise
        
        return exponential_backoff_retry(_publish)


class TextractHelper:
    """Helper for AWS Textract operations"""
    
    def __init__(self, region: str = "ap-south-1"):
        self.client = boto3.client("textract", region_name=region)
        self.region = region
    
    def analyze_document(
        self,
        bucket: str,
        key: str,
        feature_types: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyze document with Textract
        
        Args:
            bucket: S3 bucket name
            key: S3 object key
            feature_types: Features to extract (FORMS, TABLES)
            
        Returns:
            Textract response
        """
        if feature_types is None:
            feature_types = ["FORMS", "TABLES"]
        
        def _analyze():
            try:
                response = self.client.analyze_document(
                    Document={"S3Object": {"Bucket": bucket, "Name": key}},
                    FeatureTypes=feature_types,
                )
                return response
            except ClientError as e:
                if e.response["Error"]["Code"] in ["ThrottlingException", "ProvisionedThroughputExceededException"]:
                    raise RetryableError(f"Textract analyze failed: {e}")
                raise
        
        return exponential_backoff_retry(_analyze)
    
    def extract_text(self, textract_response: Dict[str, Any]) -> str:
        """
        Extract plain text from Textract response
        
        Args:
            textract_response: Textract API response
            
        Returns:
            Extracted text
        """
        text_lines = []
        for block in textract_response.get("Blocks", []):
            if block["BlockType"] == "LINE":
                text_lines.append(block["Text"])
        return "\n".join(text_lines)


class KendraHelper:
    """Helper for Amazon Kendra operations"""
    
    def __init__(self, index_id: str, region: str = "ap-south-1"):
        self.client = boto3.client("kendra", region_name=region)
        self.index_id = index_id
        self.region = region
    
    def query(
        self,
        query_text: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Query Kendra index
        
        Args:
            query_text: Query text
            top_k: Number of results to return
            
        Returns:
            List of search results
        """
        def _query():
            try:
                response = self.client.query(
                    IndexId=self.index_id,
                    QueryText=query_text,
                    PageSize=top_k,
                )
                return response.get("ResultItems", [])
            except ClientError as e:
                if e.response["Error"]["Code"] in ["ThrottlingException"]:
                    raise RetryableError(f"Kendra query failed: {e}")
                raise
        
        return exponential_backoff_retry(_query)
