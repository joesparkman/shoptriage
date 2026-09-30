"""Delete all DynamoDB records with status=new (stuck after failed Transcribe)."""
import boto3

TABLE = "shoptriage"
REGION = "us-east-1"
PROFILE = "shoptriage-agent"

session = boto3.Session(profile_name=PROFILE, region_name=REGION)
ddb = session.resource("dynamodb")
table = ddb.Table(TABLE)

# Scan for all items — table should be small during dev
resp = table.scan()
items = resp["Items"]
print(f"Total items found: {len(items)}")

deleted = 0
for item in items:
    pk = item["PK"]
    sk = item["SK"]
    status = item.get("status", "")
    stage = item.get("stage", "")
    # Delete any item that belongs to a stuck call (status=new or stage=uploaded)
    # Keep nothing — table should be clean before the real e2e test
    table.delete_item(Key={"PK": pk, "SK": sk})
    print(f"DELETED  {pk}  |  {sk}  status={status} stage={stage}")
    deleted += 1

print(f"\nDeleted {deleted} items")
resp2 = table.scan(Select="COUNT")
print(f"Table count after: {resp2['Count']}")
