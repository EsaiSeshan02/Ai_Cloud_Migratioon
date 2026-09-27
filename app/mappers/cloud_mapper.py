"""Authoritative deterministic mappings for the AWS-to-Azure prototype.

This project supports one provider direction only: AWS as source and Azure as
target. Mapping capability is never an execution promise; S3 and the
separately validated Lambda subset are the only execution services.
"""

from copy import deepcopy

SUPPORTED_EXECUTION = "supported_execution"
PLANNING_ONLY = "planning_only"
MANUAL_REVIEW = "manual_review"
UNSUPPORTED = "unsupported"

AWS_AZURE_MAPPINGS = {
    "EC2": {
        "target_service": "Azure Virtual Machine", "compatibility": 0,
        "recommended_size": "Azure VM assessment required",
        "execution_classification": PLANNING_ONLY,
        "status": "Planning only — execution is not implemented",
    },
    "S3": {
        "target_service": "Azure Blob Storage", "compatibility": 95,
        "recommended_size": "Standard Storage Account",
        "execution_classification": SUPPORTED_EXECUTION,
        "status": "Migration execution supported",
    },
    "RDS": {
        "target_service": "Azure Database (engine assessment required)", "compatibility": 0,
        "recommended_size": "Database engine assessment required",
        "execution_classification": MANUAL_REVIEW,
        "status": "Manual review required — database engine is unknown",
    },
    "Lambda": {
        "target_service": "Azure Functions", "compatibility": 0,
        "recommended_size": "Function architecture assessment required",
        "execution_classification": PLANNING_ONLY,
        "status": "Planning only — dedicated subset validation is required",
    },
}

_RDS_ENGINE_MAPPINGS = {
    "postgres": ("Azure Database for PostgreSQL", 85),
    "aurora-postgresql": ("Azure Database for PostgreSQL", 80),
    "mysql": ("Azure Database for MySQL", 85),
    "aurora-mysql": ("Azure Database for MySQL", 80),
    "sqlserver": ("Azure SQL Managed Instance", 70),
}

# Compatibility export retained for existing imports. It deliberately contains
# only the official AWS → Azure scope.
CLOUD_MAPPINGS = {"AWS": {"Azure": AWS_AZURE_MAPPINGS}}


def _rds_mapping(resource):
    engine = str((resource or {}).get("engine") or (resource or {}).get("database_engine") or "").strip().lower()
    resolved = _RDS_ENGINE_MAPPINGS.get(engine)
    if not resolved and engine.startswith("postgres"):
        resolved = _RDS_ENGINE_MAPPINGS["postgres"]
    if not resolved and engine.startswith("mysql"):
        resolved = _RDS_ENGINE_MAPPINGS["mysql"]
    if not resolved and engine.startswith("sqlserver"):
        resolved = _RDS_ENGINE_MAPPINGS["sqlserver"]
    if not resolved:
        return deepcopy(AWS_AZURE_MAPPINGS["RDS"])
    target, compatibility = resolved
    return {
        "target_service": target,
        "compatibility": compatibility,
        "recommended_size": "Database migration assessment required",
        "execution_classification": PLANNING_ONLY,
        "status": "Planning only — data migration is not implemented",
    }


def get_cloud_mapping(source_cloud, target_cloud, source_service, resource=None):
    """Return a mapping only for AWS source to Azure target."""
    if str(source_cloud).strip().lower() != "aws" or str(target_cloud).strip().lower() != "azure":
        return None
    service = str(source_service or "").strip()
    if service == "RDS":
        return _rds_mapping(resource)
    mapping = AWS_AZURE_MAPPINGS.get(service)
    return deepcopy(mapping) if mapping else None
