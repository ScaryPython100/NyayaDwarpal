#!/usr/bin/env python3
"""
Script to fetch recent CloudWatch logs for PetitionArchitect Lambda
"""

import boto3
import time
from datetime import datetime, timedelta

# Initialize CloudWatch Logs client
logs_client = boto3.client('logs', region_name='ap-south-2')

# Lambda function name
FUNCTION_NAME = 'NyayaDwarpal-PetitionArchitect'
LOG_GROUP = f'/aws/lambda/{FUNCTION_NAME}'

def get_recent_logs(minutes=10):
    """Fetch logs from the last N minutes"""
    
    # Calculate time range
    end_time = int(time.time() * 1000)
    start_time = int((time.time() - (minutes * 60)) * 1000)
    
    try:
        # Get log streams
        streams_response = logs_client.describe_log_streams(
            logGroupName=LOG_GROUP,
            orderBy='LastEventTime',
            descending=True,
            limit=5
        )
        
        print(f"=== Recent logs for {FUNCTION_NAME} (last {minutes} minutes) ===\n")
        
        for stream in streams_response['logStreams']:
            stream_name = stream['logStreamName']
            print(f"\n--- Log Stream: {stream_name} ---")
            
            # Get log events
            events_response = logs_client.get_log_events(
                logGroupName=LOG_GROUP,
                logStreamName=stream_name,
                startTime=start_time,
                endTime=end_time,
                startFromHead=True
            )
            
            for event in events_response['events']:
                timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
                message = event['message']
                print(f"[{timestamp}] {message}")
        
    except logs_client.exceptions.ResourceNotFoundException:
        print(f"Log group {LOG_GROUP} not found. Lambda may not have been invoked yet.")
    except Exception as e:
        print(f"Error fetching logs: {str(e)}")

if __name__ == "__main__":
    get_recent_logs(minutes=30)
