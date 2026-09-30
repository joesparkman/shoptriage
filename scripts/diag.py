import boto3

session = boto3.Session(profile_name='shoptriage-agent', region_name='us-east-1')

# 1. Check DynamoDB — did start_transcription fire?
ddb = session.resource('dynamodb').Table('shoptriage')
resp = ddb.scan()
items = resp['Items']
print(f'DynamoDB items: {len(items)}')
for i in items:
    pk = i.get('PK', '')
    sk = i.get('SK', '')
    status = i.get('status', 'n/a')
    stage  = i.get('stage', 'n/a')
    s3key  = i.get('s3_key', '')
    print(f'  PK={pk}  SK={sk}  status={status}  stage={stage}  s3_key={s3key}')

# 2. Check Transcribe jobs
tc = session.client('transcribe')
found_any = False
for status in ('IN_PROGRESS', 'COMPLETED', 'FAILED', 'QUEUED'):
    jobs = tc.list_transcription_jobs(
        Status=status,
        JobNameContains='shoptriage-'
    ).get('TranscriptionJobSummaries', [])
    if jobs:
        found_any = True
        print(f'\nTranscribe {status}:')
        for j in jobs:
            print(f'  {j["TranscriptionJobName"]}  created={j.get("CreationTime")}')

if not found_any:
    print('\nNo shoptriage- Transcribe jobs found in any status.')

# 3. Check start_transcription Lambda logs (last 20 log events)
logs = session.client('logs')
log_group = '/aws/lambda/shoptriage-start-transcription'
try:
    streams = logs.describe_log_streams(
        logGroupName=log_group,
        orderBy='LastEventTime',
        descending=True,
        limit=3
    )['logStreams']
    print(f'\nstart_transcription recent log streams: {len(streams)}')
    for stream in streams[:2]:
        print(f'  Stream: {stream["logStreamName"]}  lastEvent={stream.get("lastEventTimestamp")}')
        events = logs.get_log_events(
            logGroupName=log_group,
            logStreamName=stream['logStreamName'],
            limit=20,
            startFromHead=False
        )['events']
        for ev in events[-10:]:
            print(f'    {ev["message"].strip()}')
except Exception as e:
    print(f'  Error reading logs: {e}')
