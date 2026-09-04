"""Shared MySQL connection helper for the UFC database."""
from typing import Optional

import mysql.connector

from ufcPipeline.secretsManager import get_secret


def connect(profile_name: Optional[str] = None):
    """Open a MySQL connection to the UFC database using Secrets Manager creds."""
    creds = get_secret(profile_name=profile_name)
    return mysql.connector.connect(
        user=creds["username"],
        password=creds["password"],
        host=creds["host"],
        database=creds["dbInstanceIdentifier"],
    )
