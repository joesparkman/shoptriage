"""Read the most recent process_transcript Lambda log streams."""
import boto3

session = boto3.Session(profile_name='shoptriage-agent', region_name='us-east-1')
logs = session.client('logs')

log_group = '/aws/lambda/shoptriage-process-transcript'
streams = logs.describe_log_streams(
    logGroupName=log_group,
    orderBy='LastEventTime',
    descending=True,
    limit=2
)['logStreams']

for stream in streams:
    print(f"\nStream: {stream['logStreamName']}")
    events = logs.get_log_events(
        logGroupName=log_group,
        logStreamName=stream['logStreamName'],
        limit=30,
        startFromHead=True
    )['events']
    for ev in events:
        msg = ev['message'].rstrip()
        # Skip long event dumps
        if 'Event: {' in msg and len(msg) > 200:
            print(f"  [INFO] Event received (truncated)")
        else:
            print(f"  {msg}")
