EC2 CloudWatch

```text
You are an AWS cloud engineer.

Create an AWS Lambda function in Python that will be used as an Action for an Amazon Bedrock Agent.

Requirements:

1. The Lambda function should check Amazon CloudWatch alarms in the AWS account.
2. Specifically check the alarm named "EC2_Instance_CPU_Utilization".
3. If the alarm state is "ALARM", return the EC2 instance ID and describe that the instance has high CPU utilization.
4. If there are no alarms in ALARM state, return a message indicating that all alarms are OK and there is no operational issue.
5. The Lambda function will receive an event payload from a Bedrock Agent Action Group.

The event structure includes:
- actionGroup
- apiPath
- httpMethod
- requestBody
- promptSessionAttributes

The function must:

• Inspect event["apiPath"]  
• If apiPath == "/get_all_alarms", query CloudWatch alarms using boto3  
• Return a structured response compatible with Amazon Bedrock Agent action response format.

Response format must follow this structure:

{
  "messageVersion": "1.0",
  "response": {
    "actionGroup": "...",
    "apiPath": "...",
    "httpMethod": "...",
    "httpStatusCode": 200,
    "responseBody": {
      "application/json": {
        "body": "..."
      }
    }
  },
  "promptSessionAttributes": {}
}

Technical requirements:

- Use Python
- Use boto3
- Use CloudWatch describe_alarms API
- Return JSON responses
- Handle cases where no alarms exist
- Ensure the code is production-ready and clear.

Also include comments explaining each step.
```

Remediation Function

```text
You are an AWS cloud engineer.

Create a Python AWS Lambda function that will be used as an Action Group tool for an Amazon Bedrock Agent.

The purpose of the Lambda function is to remediate EC2 operational issues automatically.

Requirements:

1. The Lambda function must use boto3.
2. The function should support two API paths:
   - /create_snapshot_of_EC2_volume
   - /restart_ec2_instance

3. The Lambda function receives an event payload from a Bedrock Agent with the following fields:
   - actionGroup
   - apiPath
   - httpMethod
   - requestBody
   - promptSessionAttributes

4. When apiPath is "/create_snapshot_of_EC2_volume":

   • Extract the EC2 instance ARN from the request body.
   • Parse the instance ID from the ARN.
   • Call EC2 describe_instances to retrieve the attached EBS volume.
   • Create a snapshot of the EBS volume using create_snapshot.
   • Return the SnapshotId in the response.

5. When apiPath is "/restart_ec2_instance":

   • Extract the instance ID from the ARN.
   • Restart the instance using reboot_instances.
   • Return a response message confirming the instance restart.

6. The function must return responses in the Amazon Bedrock Agent Action response format:

{
  "messageVersion": "1.0",
  "response": {
    "actionGroup": "...",
    "apiPath": "...",
    "httpMethod": "...",
    "httpStatusCode": 200,
    "responseBody": {
      "application/json": {
        "body": "..."
      }
    }
  },
  "promptSessionAttributes": {}
}

7. Use clean Python code and include comments explaining each step.

The function should support automated remediation scenarios such as:

High EC2 CPU utilization detected → create snapshot → restart instance.
```


