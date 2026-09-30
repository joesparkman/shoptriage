"""Read the most recent process_transcript Lambda log stream."""
import boto3

session = boto3.Session(profile_name='shoptriage-agent', region_name='us-east-1')
logs = session.client('logs')

log_group = '/aws/lambda/shoptriage-process-transcript'
streams = logs.describe_log_streams(
    logGroupName=log_group,
    orderBy='LastEventTime',
    descending=True,
    limit=1
)['logStreams']

if not streams:
    print("No log streams found.")
else:
    stream = streams[0]
    print(f"Stream: {stream['logStreamName']}")
    events = logs.get_log_events(
        logGroupName=log_group,
        logStreamName=stream['logStreamName'],
        limit=50,
        startFromHead=True
    )['events']
    for ev in events:
        print(ev['message'].rstrip())
