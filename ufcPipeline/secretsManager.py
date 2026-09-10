"""Retrieve the UFC database credentials from AWS Secrets Manager."""
import json

import boto3
from botocore.exceptions import ClientError

DEFAULT_SECRET_NAME = "ufcDBcred"
DEFAULT_REGION = "us-west-1"


def get_secret(
    profile_name: str | None = None,
    secret_name: str = DEFAULT_SECRET_NAME,
    region_name: str = DEFAULT_REGION,
) -> dict:
    """Return the DB credentials stored in AWS Secrets Manager as a dict.

    Leave ``profile_name`` as ``None`` when running inside AWS (Lambda/EC2) so the
    execution role is used; pass a named profile when running on a workstation.
    """
    session = boto3.session.Session(profile_name=profile_name)
    client = session.client(service_name="secretsmanager", region_name=region_name)
    try:
        response = client.get_secret_value(SecretId=secret_name)
    except ClientError as exc:
        raise exc
    return json.loads(response["SecretString"])
