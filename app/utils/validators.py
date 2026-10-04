import re

_S3_BUCKET = re.compile(r"^(?!\d+\.\d+\.\d+\.\d+$)(?!.*\.\.)[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_AZURE_CONTAINER = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$")
_AZURE_STORAGE = re.compile(r"^[a-z0-9]{3,24}$")


def valid_s3_bucket_name(value):
    return bool(_S3_BUCKET.fullmatch(str(value or "")))


def valid_azure_container_name(value):
    return bool(_AZURE_CONTAINER.fullmatch(str(value or "")))


def valid_azure_storage_account_name(value):
    return bool(_AZURE_STORAGE.fullmatch(str(value or "")))


def safe_migration_configuration(value):
    """Validate only supported non-secret S3 destination fields."""
    if not isinstance(value, dict):
        return False
    account = value.get("destination_storage_account")
    container = value.get("container_name")
    return (not account or valid_azure_storage_account_name(account)) and (not container or valid_azure_container_name(container))
