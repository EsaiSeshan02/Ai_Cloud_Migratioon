"""Authoritative deterministic cloud-service mappings.

Execution classification is capability metadata, not a promise that a target
resource has been created. S3-to-Azure-Blob and a separately preflighted,
deliberately narrow Python-ZIP Lambda-to-Azure-Functions path have execution
services. This mapping layer remains conservative: Lambda mappings are planning
until package and target validation confirms that narrow subset.
"""

from copy import deepcopy

SUPPORTED_EXECUTION = "supported_execution"
PLANNING_ONLY = "planning_only"
MANUAL_REVIEW = "manual_review"
UNSUPPORTED = "unsupported"


# The single source used by the AWS-to-Azure scan, analysis, and plan flow.
AWS_AZURE_MAPPINGS = {
    "EC2": {
        "target_service": "Azure Virtual Machine",
        "compatibility": 0,
        "recommended_size": "Azure VM assessment required",
        "execution_classification": PLANNING_ONLY,
        "status": "Planning only — execution is not implemented",
    },
    "S3": {
        "target_service": "Azure Blob Storage",
        "compatibility": 95,
        "recommended_size": "Standard Storage Account",
        "execution_classification": SUPPORTED_EXECUTION,
        "status": "Migration execution supported",
    },
    "RDS": {
        "target_service": "Azure Database (engine assessment required)",
        "compatibility": 0,
        "recommended_size": "Database engine assessment required",
        "execution_classification": MANUAL_REVIEW,
        "status": "Manual review required — database engine is unknown",
    },
    "Lambda": {
        "target_service": "Azure Functions",
        "compatibility": 0,
        "recommended_size": "Function architecture assessment required",
        "execution_classification": PLANNING_ONLY,
        "status": "Planning only — deployment is not implemented",
    },
}

_RDS_ENGINE_MAPPINGS = {
    "postgres": ("Azure Database for PostgreSQL", 85),
    "aurora-postgresql": ("Azure Database for PostgreSQL", 80),
    "mysql": ("Azure Database for MySQL", 85),
    "aurora-mysql": ("Azure Database for MySQL", 80),
    "sqlserver": ("Azure SQL Managed Instance", 70),
}


# Kept for existing imports and non-AWS/Azure UI routes. No entry below claims
# executable migration support because those engines do not exist yet.
CLOUD_MAPPINGS = {
    "AWS": {
        "Azure": AWS_AZURE_MAPPINGS,
        "GCP": {
            "EC2": {"target_service": "Google Compute Engine", "compatibility": 0,
                    "execution_classification": PLANNING_ONLY, "status": "Planning only"},
            "S3": {"target_service": "Google Cloud Storage", "compatibility": 0,
                   "execution_classification": PLANNING_ONLY, "status": "Planning only"},
            "RDS": {"target_service": "Google Cloud SQL", "compatibility": 0,
                    "execution_classification": MANUAL_REVIEW, "status": "Manual review required"},
            "Lambda": {"target_service": "Google Cloud Functions", "compatibility": 0,
                       "execution_classification": PLANNING_ONLY, "status": "Planning only"},
        },
    },
    "Azure": {
        "AWS": {
            "Azure Virtual Machine": {"target_service": "EC2", "compatibility": 0,
                                      "execution_classification": PLANNING_ONLY, "status": "Planning only"},
            "Azure Blob Storage": {"target_service": "S3", "compatibility": 0,
                                   "execution_classification": PLANNING_ONLY, "status": "Planning only"},
            "Azure Storage Account": {"target_service": "S3", "compatibility": 0,
                                      "execution_classification": PLANNING_ONLY, "status": "Planning only"},
            "Azure SQL Database": {"target_service": "RDS", "compatibility": 0,
                                   "execution_classification": MANUAL_REVIEW, "status": "Manual review required"},
        },
        "GCP": {
            "Azure Virtual Machine": {"target_service": "Google Compute Engine", "compatibility": 0,
                                      "execution_classification": PLANNING_ONLY, "status": "Planning only"},
            "Azure Blob Storage": {"target_service": "Google Cloud Storage", "compatibility": 0,
                                   "execution_classification": PLANNING_ONLY, "status": "Planning only"},
            "Azure Storage Account": {"target_service": "Google Cloud Storage", "compatibility": 0,
                                      "execution_classification": PLANNING_ONLY, "status": "Planning only"},
            "Azure SQL Database": {"target_service": "Google Cloud SQL", "compatibility": 0,
                                   "execution_classification": MANUAL_REVIEW, "status": "Manual review required"},
        },
    },
    "GCP": {
        "AWS": {
            "GCE": {"target_service": "EC2", "compatibility": 0,
                    "execution_classification": PLANNING_ONLY, "status": "Planning only"},
            "GCS": {"target_service": "S3", "compatibility": 0,
                    "execution_classification": PLANNING_ONLY, "status": "Planning only"},
            "Cloud SQL": {"target_service": "RDS", "compatibility": 0,
                          "execution_classification": MANUAL_REVIEW, "status": "Manual review required"},
        },
        "Azure": {
            "GCE": {"target_service": "Azure Virtual Machine", "compatibility": 0,
                    "execution_classification": PLANNING_ONLY, "status": "Planning only"},
            "GCS": {"target_service": "Azure Blob Storage", "compatibility": 0,
                    "execution_classification": PLANNING_ONLY, "status": "Planning only"},
            "Cloud SQL": {"target_service": "Azure SQL Database", "compatibility": 0,
                          "execution_classification": MANUAL_REVIEW, "status": "Manual review required"},
        },
    },
}

_CLOUD_NAMES = {
    "aws": "AWS", "azure": "Azure", "gcp": "GCP", "google": "GCP",
    "google cloud": "GCP", "google cloud platform": "GCP",
}


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
    """Return deterministic mapping metadata, or ``None`` if no mapping exists."""
    source_key = _CLOUD_NAMES.get(str(source_cloud).strip().lower(), str(source_cloud).strip())
    target_key = _CLOUD_NAMES.get(str(target_cloud).strip().lower(), str(target_cloud).strip())
    service = str(source_service or "").strip()
    if source_key == "AWS" and target_key == "Azure" and service == "RDS":
        return _rds_mapping(resource)
    mapping = CLOUD_MAPPINGS.get(source_key, {}).get(target_key, {}).get(service)
    return deepcopy(mapping) if mapping else None
