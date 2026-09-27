"""Persisted, owner-scoped migration assessment plans.

This service is deliberately assessment-only.  It records safe scanner
metadata and deterministic recommendations, never cloud credentials, database
passwords, Lambda environment values, or execution results.
"""

import json
import uuid

from app.extensions import db
from app.mappers.cloud_mapper import (
    MANUAL_REVIEW,
    PLANNING_ONLY,
    SUPPORTED_EXECUTION,
    get_cloud_mapping,
)
from app.models.migration import MigrationPlan, MigrationPlanResource


_SAFE_METADATA = {
    "EC2": {
        "instance_id", "type", "state", "availability_zone", "image_id", "architecture", "platform",
        "root_device_name", "root_device_type", "root_volume", "ebs_volumes", "vpc_id", "subnet_id", "security_groups",
    },
    "S3": {"bucket_name", "creation_date", "region", "versioning_status", "encryption_status", "object_inventory_scanned"},
    "RDS": {
        "identifier", "engine", "engine_family", "engine_version", "instance_class", "status", "availability_zone",
        "allocated_storage_gb", "storage_type", "storage_encrypted", "multi_az", "publicly_accessible",
        "backup_retention_days", "endpoint_configured",
    },
    "Lambda": {
        "runtime", "architecture", "architectures", "memory_mb", "timeout_seconds", "last_modified", "handler",
        "package_type", "vpc_enabled", "layers_count", "tracing_mode", "event_source_types",
        "event_source_discovery_available", "environment_variables_included",
    },
}


def _json(value):
    return json.dumps(value, default=str, separators=(",", ":"))


def _read_json(value, fallback):
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def _safe_metadata(resource):
    allowed = _SAFE_METADATA.get(resource.get("service"), set())
    return {key: resource[key] for key in allowed if key in resource}


def _finding(level, code, message):
    return {"level": level, "code": code, "message": message}


def _s3_assessment(resource, source_session_reference, target_session_reference):
    findings = []
    reasons = []
    if source_session_reference and target_session_reference:
        findings.append(_finding("pass", "sessions_referenced", "Source and target cloud sessions are referenced by this plan."))
    else:
        findings.append(_finding("warning", "sessions_missing", "Source and target cloud sessions must be connected before execution."))
        reasons.append("Source or target session reference is missing.")
    if not resource.get("object_inventory_scanned", False):
        findings.append(_finding("info", "object_inventory_deferred", "Object count and total size are assessed when an S3 migration is explicitly started."))
    findings.append(_finding("info", "bucket_policy_lifecycle_review", "Bucket policy and lifecycle configuration are not included in this inventory and require review before cutover."))
    if resource.get("region"):
        findings.append(_finding("pass", "bucket_region_discovered", "Bucket region was discovered for target-region planning."))
    else:
        findings.append(_finding("warning", "bucket_region_unknown", "Bucket region requires confirmation before target storage planning."))
    if resource.get("versioning_status") == "Enabled":
        findings.append(_finding("info", "bucket_versioning_enabled", "Versioning is enabled; version and delete-marker handling requires review."))
    if resource.get("encryption_status") == "Unknown":
        findings.append(_finding("warning", "bucket_encryption_unknown", "Bucket encryption settings could not be assessed."))
    elif resource.get("encryption_status") == "Not configured":
        findings.append(_finding("warning", "bucket_encryption_not_configured", "Source bucket encryption is not configured and target encryption requirements need review."))
    else:
        findings.append(_finding("pass", "bucket_encryption_assessed", "Bucket encryption configuration was assessed without reading object contents."))
    risk = "low"
    if reasons or resource.get("encryption_status") in {"Unknown", "Not configured"} or not resource.get("region"):
        risk = "medium"
    return risk, ["Azure Storage account", "Azure Blob container"], findings, reasons


def _ec2_assessment(resource):
    findings, reasons = [], []
    dependencies = []
    if resource.get("type"):
        findings.append(_finding("info", "instance_type_discovered", "Instance type was discovered; Azure VM sizing requires a separate sizing assessment."))
    else:
        findings.append(_finding("warning", "instance_type_missing", "Instance type is unavailable for Azure VM sizing assessment."))
    if resource.get("availability_zone"):
        findings.append(_finding("info", "availability_zone_discovered", "Availability-zone placement was discovered for resilience and cutover planning."))
    if not resource.get("image_id"):
        findings.append(_finding("warning", "image_missing", "AMI/image information is required before VM migration planning can continue."))
        reasons.append("AMI/image information is missing.")
    else:
        findings.append(_finding("warning", "image_conversion_required", "AMI/image conversion or an approved replication/import path is required; VM execution is not implemented."))
        dependencies.append("AMI/image conversion or replication path")
    if not resource.get("root_volume"):
        findings.append(_finding("warning", "root_volume_missing", "Root-volume details require assessment before disk conversion planning."))
        reasons.append("Root-volume details are unavailable.")
    else:
        dependencies.append("Root-volume disk conversion")
        if resource.get("root_volume", {}).get("encrypted") is False:
            findings.append(_finding("warning", "root_volume_unencrypted", "The root-volume encryption indicator is false; disk and target encryption requirements require review."))
        elif resource.get("root_volume", {}).get("encrypted") is True:
            findings.append(_finding("info", "root_volume_encryption_discovered", "Root-volume encryption metadata was discovered; Azure disk encryption design still requires review."))
    volumes = resource.get("ebs_volumes") or []
    if volumes:
        dependencies.append("Attached EBS volume conversion")
        if any(volume.get("encrypted") is False for volume in volumes if isinstance(volume, dict)):
            findings.append(_finding("warning", "ebs_encryption_review", "One or more attached EBS volumes are not marked encrypted; disk encryption requirements require review."))
    if not resource.get("vpc_id") or not resource.get("subnet_id"):
        findings.append(_finding("warning", "network_missing", "VPC and subnet mapping must be assessed before Azure network planning."))
        reasons.append("VPC or subnet reference is missing.")
    else:
        dependencies.extend(["VPC mapping", "Subnet mapping"])
    if not resource.get("security_groups"):
        findings.append(_finding("warning", "security_groups_missing", "Security-group to NSG conversion requires review."))
        reasons.append("Security-group references are unavailable.")
    else:
        dependencies.append("Security-group to NSG mapping")
    platform = str(resource.get("platform") or "").lower()
    architecture = str(resource.get("architecture") or "").lower()
    if not platform or platform == "unknown":
        findings.append(_finding("warning", "platform_unknown", "Operating-system/platform information is unavailable for Azure boot compatibility assessment."))
    if not architecture:
        findings.append(_finding("warning", "architecture_missing", "CPU architecture is unavailable for Azure VM compatibility assessment."))
    findings.append(_finding("info", "architecture_os_review", "Architecture and OS boot compatibility require review before any VM conversion."))
    findings.append(_finding("warning", "cutover_rollback_required", "Boot validation, cutover sequencing, and rollback planning are required; this application does not execute VM migration."))
    return "manual_review" if reasons else "high", dependencies, findings, reasons


def _rds_assessment(resource, classification):
    findings = [
        _finding("warning", "database_migration_not_implemented", "Database schema/data migration is not implemented by this application."),
        _finding("warning", "database_credentials_required", "An approved database credential and connectivity workflow is required later; no password is stored in this plan."),
        _finding("info", "engine_version_review", "Engine version, extensions, and feature compatibility require assessment."),
    ]
    reasons = []
    dependencies = ["Database connectivity", "Schema compatibility assessment", "Approved migration mechanism", "Cutover and validation plan", "Rollback plan"]
    if resource.get("engine"):
        findings.append(_finding("info", "database_engine_discovered", "Database engine was discovered and used for deterministic target assessment."))
    else:
        findings.append(_finding("warning", "database_engine_missing", "Database engine is unavailable for target selection."))
        reasons.append("Database engine information is missing.")
    if not resource.get("engine_version"):
        findings.append(_finding("warning", "engine_version_missing", "Database engine version is unavailable for compatibility assessment."))
    if resource.get("availability_zone"):
        findings.append(_finding("info", "availability_zone_discovered", "Availability-zone metadata was discovered for availability planning."))
    if resource.get("storage_encrypted") is False:
        findings.append(_finding("warning", "database_storage_encryption_review", "Database storage is not marked encrypted; encryption requirements require review."))
    if resource.get("backup_retention_days") is not None:
        findings.append(_finding("info", "backup_retention_discovered", "Backup retention metadata was discovered; backup and rollback coverage require review."))
    if classification == MANUAL_REVIEW:
        reasons.append("The RDS engine is unknown or unsupported for deterministic target selection.")
        findings.append(_finding("warning", "engine_manual_review", "Select a compatible Azure database target after engine assessment."))
    return "manual_review" if classification == MANUAL_REVIEW else "high", dependencies, findings, reasons


def _lambda_assessment(resource):
    findings = [
        _finding("info", "function_execution_preflight_required", "Only the narrow Python ZIP Lambda subset can proceed to Azure Functions target validation and real deployment."),
        _finding("info", "runtime_dependency_review", "Runtime, handler, package dependencies, and layers require review."),
        _finding("info", "trigger_identity_review", "Triggers, IAM permissions, and identity mappings require review."),
    ]
    dependencies = ["Function package", "Azure Function App plan", "IAM to managed-identity mapping", "Trigger mapping"]
    reasons = []
    if not resource.get("runtime"):
        findings.append(_finding("warning", "runtime_missing", "Lambda runtime is unavailable for Azure Functions compatibility assessment."))
        reasons.append("Runtime information is missing.")
    if not resource.get("handler") and resource.get("package_type", "Zip") == "Zip":
        findings.append(_finding("warning", "handler_missing", "Lambda handler is unavailable for package compatibility assessment."))
        reasons.append("Handler information is missing.")
    if resource.get("layers_count", 0):
        findings.append(_finding("warning", "layers_review", "Lambda layers require dependency and package compatibility review."))
        dependencies.append("Layer dependency review")
    if resource.get("vpc_enabled"):
        findings.append(_finding("warning", "vpc_review", "VPC networking requires an Azure network design review."))
        dependencies.append("VPC/network design")
    if not resource.get("event_source_discovery_available"):
        findings.append(_finding("warning", "trigger_discovery_incomplete", "Event-source mappings could not be fully assessed."))
        reasons.append("Event-source discovery is incomplete.")
    event_types = set(resource.get("event_source_types") or [])
    if event_types:
        dependencies.append("Event-source trigger conversion")
    if "other" in event_types:
        findings.append(_finding("warning", "unsupported_trigger_integration", "At least one discovered event source needs manual integration assessment."))
        reasons.append("An unsupported or unclassified trigger integration was detected.")
    findings.append(_finding("info", "environment_secret_handling", "Environment-variable values were deliberately excluded; secret migration must use an approved target secret-management design."))
    return "manual_review" if reasons else "high", dependencies, findings, reasons


def _assessment(resource, classification, source_session_reference, target_session_reference):
    service = resource.get("service")
    if service == "S3":
        return _s3_assessment(resource, source_session_reference, target_session_reference)
    if service == "EC2":
        return _ec2_assessment(resource)
    if service == "RDS":
        return _rds_assessment(resource, classification)
    if service == "Lambda":
        return _lambda_assessment(resource)
    return "high", [], [_finding("warning", "unsupported_service", "No deterministic migration assessment is available.")], ["Service is unsupported."]


def _execution_mode(classification):
    if classification == SUPPORTED_EXECUTION:
        return "existing_s3_execution_engine"
    if classification == PLANNING_ONLY:
        return "assessment_only"
    return "manual_review_required"


def approve_lambda_execution_target(plan, function_name, configuration):
    """Persist the user-approved, non-secret Lambda deployment target on its plan.

    The authoritative capability classification remains planning-only here.  The
    Lambda deployment service performs the final package and target validation
    before it permits execution.
    """
    if not isinstance(plan, MigrationPlan):
        raise ValueError("A persisted migration plan is required.")
    if not isinstance(configuration, dict):
        raise ValueError("Lambda deployment configuration is invalid.")
    resource = next((item for item in plan.resources if item.service == "Lambda" and item.resource_name == function_name), None)
    if resource is None:
        raise ValueError("The selected plan does not contain this AWS Lambda resource.")
    target = {
        "resource_group": str(configuration.get("resource_group") or "").strip(),
        "function_app_name": str(configuration.get("function_app_name") or "").strip(),
        "deployment_slot": str(configuration.get("deployment_slot") or "").strip(),
    }
    if not target["resource_group"] or not target["function_app_name"]:
        raise ValueError("An existing Azure resource group and Function App are required.")
    recommendation = _read_json(resource.recommendation_data, {})
    recommendation["approved_lambda_target"] = target
    recommendation["execution_gate"] = "package_and_target_validation_required"
    resource.recommendation_data = _json(recommendation)
    resource.status = "Approved for Lambda target validation"
    plan.status = "approved_for_lambda_target_validation"
    db.session.commit()
    return resource


def _iter_normalized_resources(normalized_resources):
    if not isinstance(normalized_resources, dict):
        raise ValueError("Normalized scanner output must be an object.")
    for service_result in normalized_resources.values():
        if not isinstance(service_result, dict):
            raise ValueError("Normalized scanner output contains an invalid service result.")
        if not service_result.get("success"):
            continue
        resources = service_result.get("resources", [])
        if not isinstance(resources, list):
            raise ValueError("Normalized scanner output contains invalid resources.")
        for resource in resources:
            if not isinstance(resource, dict) or not resource.get("service"):
                raise ValueError("Normalized scanner output contains an invalid resource.")
            yield resource


def generate_migration_plan(*, user_id, source_cloud, target_cloud, source_session_reference, target_session_reference, normalized_resources):
    """Create an owner-scoped plan from safe normalized scanner output."""
    source = str(source_cloud or "").lower()
    target = str(target_cloud or "").lower()
    if (source, target) != ("aws", "azure"):
        raise ValueError("Persisted planning supports AWS to Azure assessment only.")

    resources = list(_iter_normalized_resources(normalized_resources))
    plan = MigrationPlan(
        plan_id=uuid.uuid4().hex,
        user_id=user_id,
        source_cloud=source,
        target_cloud=target,
        source_session_reference=source_session_reference,
        target_session_reference=target_session_reference,
        status="generated" if resources else "empty",
    )
    db.session.add(plan)
    db.session.flush()

    executable = 0
    for resource in resources:
        mapping = get_cloud_mapping(source, target, resource.get("service"), resource=resource)
        if not mapping:
            mapping = {
                "target_service": "Manual Review Required", "compatibility": 0,
                "execution_classification": "unsupported", "status": "Unsupported — manual review required",
                "recommended_size": "Manual configuration",
            }
        classification = mapping["execution_classification"]
        risk, dependencies, findings, reasons = _assessment(
            resource, classification, source_session_reference, target_session_reference
        )
        if classification == SUPPORTED_EXECUTION:
            executable += 1
        resource_id = str(resource.get("resource_id") or resource.get("id") or resource.get("name") or "Unknown")
        recommendation = {
            "target_service": mapping["target_service"],
            "recommended_size": mapping.get("recommended_size"),
            "execution_classification": classification,
            "risk_level": risk,
            "dependencies": dependencies,
            "preflight_findings": findings,
            "manual_review_reasons": reasons,
        }
        db.session.add(MigrationPlanResource(
            plan_id=plan.id, source_cloud=source, target_cloud=target, service=resource["service"],
            resource_id=resource_id, resource_name=str(resource.get("name") or resource_id),
            target_service=mapping["target_service"], capability_classification=classification,
            compatibility=int(mapping.get("compatibility") or 0), execution_mode=_execution_mode(classification),
            status=mapping["status"], risk_level=risk, dependencies=_json(dependencies),
            preflight_findings=_json(findings), manual_review_reasons=_json(reasons),
            recommendation_data=_json(recommendation), source_metadata=_json(_safe_metadata(resource)),
        ))
    plan.resource_count = len(resources)
    plan.execution_ready_count = executable
    plan.planning_review_count = len(resources) - executable
    db.session.commit()
    return plan


def serialize_plan_resource(resource):
    """Return safe plan data suitable for an owner-authorized browser response."""
    return {
        "service": resource.service,
        "source": resource.service,
        "target": resource.target_service,
        "resource_id": resource.resource_id,
        "name": resource.resource_name,
        "compatibility": resource.compatibility,
        "execution_classification": resource.capability_classification,
        "execution_mode": resource.execution_mode,
        "status": resource.status,
        "risk_level": resource.risk_level,
        "dependencies": _read_json(resource.dependencies, []),
        "preflight_findings": _read_json(resource.preflight_findings, []),
        "manual_review_reasons": _read_json(resource.manual_review_reasons, []),
        "recommendation": _read_json(resource.recommendation_data, {}),
    }


def serialize_plan(plan, include_resources=True):
    payload = {
        "plan_id": plan.plan_id,
        "source_cloud": plan.source_cloud,
        "target_cloud": plan.target_cloud,
        "status": plan.status,
        "resource_count": plan.resource_count,
        "execution_ready_count": plan.execution_ready_count,
        "planning_review_count": plan.planning_review_count,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
    }
    if include_resources:
        payload["resources"] = [serialize_plan_resource(resource) for resource in plan.resources]
    return payload


def get_user_plan(plan_id, user_id):
    return MigrationPlan.query.filter_by(plan_id=plan_id, user_id=user_id).first()


def list_user_plans(user_id):
    return MigrationPlan.query.filter_by(user_id=user_id).order_by(MigrationPlan.updated_at.desc()).all()
