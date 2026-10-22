"""PC의 로고 파일(/app/media)을 Supabase 저장소(S3 방식)로 올린다 — 인터넷 테스트 서버 준비(2026-10-22).
환경 변수: MEDIA_S3_ENDPOINT, MEDIA_S3_REGION, MEDIA_S3_BUCKET, MEDIA_S3_ACCESS_KEY, MEDIA_S3_SECRET_KEY.
버킷이 없으면 비공개로 만든다. 같은 이름 파일은 덮어쓴다(여러 번 돌려도 안전)."""
import mimetypes
import os
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

root = Path(os.environ.get("MEDIA_DIR", "/app/media"))
bucket = os.environ["MEDIA_S3_BUCKET"]
s3 = boto3.client("s3", endpoint_url=os.environ["MEDIA_S3_ENDPOINT"], region_name=os.environ.get("MEDIA_S3_REGION", "ap-southeast-1"),
                  aws_access_key_id=os.environ["MEDIA_S3_ACCESS_KEY"], aws_secret_access_key=os.environ["MEDIA_S3_SECRET_KEY"],
                  config=Config(signature_version="s3v4", s3={"addressing_style": "path"}))
try:
    s3.head_bucket(Bucket=bucket)
except ClientError:
    s3.create_bucket(Bucket=bucket)
    print(f"bucket created: {bucket}")
count = 0
for path in sorted(p for p in root.rglob("*") if p.is_file()):
    key = path.relative_to(root).as_posix()
    s3.upload_file(str(path), bucket, key, ExtraArgs={"ContentType": mimetypes.guess_type(key)[0] or "application/octet-stream"})
    count += 1
print(f"UPLOAD_OK {count} files")
