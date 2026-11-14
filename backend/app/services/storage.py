"""Object storage for photos. Local disk in dev, S3 presigned URLs in prod."""
import os

from ..config import get_settings


def presign_put(key: str, content_type: str) -> tuple[str, dict[str, str]]:
    s = get_settings()
    if s.storage_backend == "s3":
        import boto3

        url = boto3.client("s3", region_name=s.aws_region).generate_presigned_url(
            "put_object",
            Params={"Bucket": s.s3_bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=900,
        )
        return url, {"Content-Type": content_type}
    return f"{s.public_base_url}/api/uploads/local/{key}", {"Content-Type": content_type}


def public_url(key: str) -> str:
    s = get_settings()
    if s.storage_backend == "s3":
        import boto3

        return boto3.client("s3", region_name=s.aws_region).generate_presigned_url(
            "get_object", Params={"Bucket": s.s3_bucket, "Key": key}, ExpiresIn=3600
        )
    return f"{s.public_base_url}/api/uploads/local/{key}"


def local_path(key: str) -> str:
    root = os.path.abspath(get_settings().upload_dir)
    path = os.path.abspath(os.path.join(root, key))
    if not path.startswith(root + os.sep):
        raise ValueError("invalid key")
    return path
