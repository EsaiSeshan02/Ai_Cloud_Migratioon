"""Backward-compatible facade for the authoritative mapper."""

from app.mappers.cloud_mapper import CLOUD_MAPPINGS, get_cloud_mapping


def get_service_mapping(source_cloud, target_cloud, source_service, resource=None):
    """Retain the historical import path without maintaining a second table."""
    mapping = get_cloud_mapping(source_cloud, target_cloud, source_service, resource=resource)
    if mapping:
        return mapping
    return {
        "target_service": "Manual Review Required",
        "compatibility": 0,
        "recommended_size": "Manual Configuration",
        "execution_classification": "unsupported",
        "status": "Unsupported — manual review required",
    }
