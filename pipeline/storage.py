"""Raw file storage: an S3 bucket in production, a local folder for tests.

JSON is stored gzip-compressed as <key>.json.gz with Content-Encoding: gzip,
so a browser shows plain JSON when the file is opened from the S3 console.
"""
import gzip
import hashlib
from dataclasses import dataclass
from pathlib import Path

from .config import CONFIG


@dataclass
class Stored:
    key: str
    bytes: int         # size of the JSON as received
    stored_bytes: int  # size of the gzip file
    sha256: str        # of the JSON as received


class LocalStorage:
    def __init__(self, root):
        self.root = Path(root)

    def put(self, key, body, content_type, content_encoding=None):
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

    def get(self, key):
        return (self.root / key).read_bytes()


class S3Storage:
    def __init__(self, bucket):
        import boto3  # imported here so local tests do not need boto3

        self.bucket = bucket
        self.s3 = boto3.client("s3", region_name=CONFIG.aws_region)

    def put(self, key, body, content_type, content_encoding=None):
        extra = {"ContentEncoding": content_encoding} if content_encoding else {}
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType=content_type, **extra)

    def get(self, key):
        return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()


def open_storage(url=None):
    url = url or CONFIG.storage
    if url.startswith("s3://"):
        return S3Storage(url[len("s3://"):].strip("/"))
    return LocalStorage(url)


def put_json(storage, key, raw):
    """Store raw JSON bytes as key + '.json.gz'. Returns sizes and the checksum."""
    key = f"{key}.json.gz"
    body = gzip.compress(raw, compresslevel=6, mtime=0)
    storage.put(key, body, "application/json", "gzip")
    return Stored(key, len(raw), len(body), hashlib.sha256(raw).hexdigest())


def get_json(storage, key):
    """Return the original JSON bytes of a stored .json.gz file."""
    return gzip.decompress(storage.get(key))
