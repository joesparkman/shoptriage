import boto3
session = boto3.Session(profile_name='shoptriage-agent', region_name='us-east-1')
sqs = session.client('sqs')
url = sqs.get_queue_url(QueueName='shoptriage-front-office-queue')['QueueUrl']
attrs = sqs.get_queue_attributes(
    QueueUrl=url,
    AttributeNames=['ApproximateNumberOfMessages', 'ApproximateNumberOfMessagesNotVisible']
)
print("visible :", attrs['Attributes']['ApproximateNumberOfMessages'])
print("in-flight:", attrs['Attributes']['ApproximateNumberOfMessagesNotVisible'])
