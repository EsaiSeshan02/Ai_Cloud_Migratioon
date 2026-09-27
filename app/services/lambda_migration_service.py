"""Real, deliberately narrow Lambda-to-Azure-Functions deployment support.

Only Python ZIP functions without layers, VPC configuration, or discovered AWS
event-source mappings are eligible. Deployment targets are existing Function
Apps selected by the owner; this service never creates Azure infrastructure or
persists AWS/Azure credentials.
"""

import hashlib
import io
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile

import requests
from botocore.exceptions import BotoCoreError, ClientError
from flask import current_app
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.utils.time import utc_now
from app.models.migration import Migration

try:  # Kept lazy-safe for developers until requirements are installed.
    from azure.mgmt.web import WebSiteManagementClient
    from azure.core.exceptions import AzureError
except ImportError:  # pragma: no cover - covered through provider prerequisite response
    WebSiteManagementClient = None
    AzureError = Exception


SUPPORTED_RUNTIMES = {"python3.10", "python3.11"}
MAX_PACKAGE_BYTES = 50 * 1024 * 1024
_HANDLER = re.compile(r"^([A-Za-z_][A-Za-z0-9_\.]{0,240})\.([A-Za-z_][A-Za-z0-9_]{0,120})$")
_RESOURCE_GROUP = re.compile(r"^[A-Za-z0-9_.()\-]{1,90}$")
_FUNCTION_APP = re.compile(r"^[a-z0-9-]{2,60}$")
_SLOT = re.compile(r"^[A-Za-z0-9-]{1,60}$")
_ACTIVE_LAMBDA_STATES = {"preparing", "deploying", "validating"}


class ManualReviewRequired(ValueError):
    """Raised when a real package is outside this prototype's safe subset."""


def _event_sources(client, name):
    try:
        pages = client.get_paginator("list_event_source_mappings").paginate(FunctionName=name)
        return [item.get("EventSourceArn", "") for page in pages for item in page.get("EventSourceMappings", [])]
    except (ClientError, BotoCoreError):
        return None


def get_lambda_details(aws_session, function_name):
    """Fetch actual configuration while returning environment names only."""
    try:
        client = aws_session.client("lambda")
        response = client.get_function(FunctionName=function_name)
        config = response.get("Configuration") or {}
        environment = (config.get("Environment") or {}).get("Variables") or {}
        return {"success": True, "code_location": (response.get("Code") or {}).get("Location"),
                "function_arn": config.get("FunctionArn"), "function_name": config.get("FunctionName"),
                "runtime": config.get("Runtime"), "handler": config.get("Handler"),
                "package_type": config.get("PackageType", "Zip"), "architectures": config.get("Architectures") or [],
                "memory_mb": config.get("MemorySize"), "timeout_seconds": config.get("Timeout"),
                "description": config.get("Description"), "last_modified": config.get("LastModified"),
                "layers": [layer.get("Arn") for layer in config.get("Layers") or [] if layer.get("Arn")],
                "vpc_enabled": bool((config.get("VpcConfig") or {}).get("VpcId")),
                "environment_names": sorted(str(key) for key in environment),
                "event_sources": _event_sources(client, config.get("FunctionName") or function_name)}
    except (ClientError, BotoCoreError):
        return {"success": False, "message": "Lambda configuration could not be retrieved."}


def assess_lambda(details):
    reasons = []
    if details.get("runtime") not in SUPPORTED_RUNTIMES:
        reasons.append("Only Python 3.10 and 3.11 ZIP Lambdas are supported.")
    if details.get("package_type") != "Zip":
        reasons.append("Container-image Lambdas are not supported.")
    if not _HANDLER.fullmatch(str(details.get("handler") or "")):
        reasons.append("The Lambda handler must use module.function syntax.")
    if details.get("layers"):
        reasons.append("Lambda layers require manual dependency review.")
    if details.get("vpc_enabled"):
        reasons.append("VPC-dependent Lambdas require manual network review.")
    if details.get("event_sources") is None:
        reasons.append("Event-source mappings could not be assessed.")
    elif details.get("event_sources"):
        reasons.append("Discovered AWS event-source mappings are not automatically translated.")
    if details.get("environment_names"):
        reasons.append("Environment values are not copied; explicitly configure non-secret target settings after review.")
    return {"classification": "supported_execution" if not reasons else "manual_review_required", "reasons": reasons}


def _safe_extract(source, destination):
    with zipfile.ZipFile(source) as archive:
        total_uncompressed = 0
        for member in archive.infolist():
            name = member.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/") or member.is_dir() and name.startswith("."):
                raise ValueError("Lambda package contains an unsafe path.")
            if stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError("Lambda package contains an unsafe symbolic link.")
            if member.file_size > MAX_PACKAGE_BYTES:
                raise ValueError("Lambda package entry exceeds the prototype size limit.")
            total_uncompressed += member.file_size
            if total_uncompressed > MAX_PACKAGE_BYTES:
                raise ValueError("Lambda package exceeds the prototype extraction size limit.")
            target = os.path.realpath(os.path.join(destination, name))
            if not target.startswith(os.path.realpath(destination) + os.sep):
                raise ValueError("Lambda package contains an unsafe path.")
        archive.extractall(destination)


def _package_review_reasons(source_dir, module):
    """Return deterministic compatibility blockers without reading secret values."""
    reasons = []
    module_path = os.path.join(source_dir, *module.split("."))
    if not (os.path.isfile(module_path + ".py") or os.path.isfile(os.path.join(module_path, "__init__.py"))):
        reasons.append("The configured Lambda handler module was not found in the ZIP package.")

    for root, _, files in os.walk(source_dir):
        for filename in files:
            lower = filename.lower()
            if lower.endswith((".so", ".pyd", ".dll", ".dylib")):
                reasons.append("Native Lambda dependencies require manual Azure Functions compatibility review.")
                return reasons
            if lower.endswith(".py"):
                path = os.path.join(root, filename)
                with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                    text = handle.read()
                if re.search(r"(^|\n)\s*(import\s+(boto3|botocore|aws_[A-Za-z0-9_]+)|from\s+(boto3|botocore|aws_[A-Za-z0-9_]+)\s+import)", text):
                    reasons.append("AWS SDK or AWS-specific code was detected and requires manual code conversion.")
                    return reasons
    return reasons


def _download_and_build_package(location, handler):
    """Download real signed Lambda ZIP, safely transform it, and clean up."""
    if not location:
        raise ValueError("Lambda package location was unavailable.")
    match = _HANDLER.fullmatch(handler or "")
    if not match:
        raise ValueError("Lambda handler is unsupported.")
    module, function = match.groups()
    temp_root = tempfile.mkdtemp(prefix="aicm-lambda-")
    try:
        response = requests.get(location, stream=True, timeout=(10, 60))
        response.raise_for_status()
        raw = io.BytesIO()
        for chunk in response.iter_content(1024 * 256):
            raw.write(chunk)
            if raw.tell() > MAX_PACKAGE_BYTES:
                raise ValueError("Lambda package exceeds the prototype size limit.")
        raw.seek(0)
        source_dir = os.path.join(temp_root, "lambda_source")
        os.makedirs(source_dir)
        _safe_extract(raw, source_dir)
        reasons = _package_review_reasons(source_dir, module)
        if reasons:
            raise ManualReviewRequired(reasons[0])
        wrapper = os.path.join(temp_root, "function_app.py")
        with open(wrapper, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("import json\nimport azure.functions as func\n")
            handle.write(f"from lambda_source.{module} import {function} as lambda_handler\n")
            handle.write("app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)\n")
            handle.write("@app.route(route='{*route}', methods=['GET','POST'])\n")
            handle.write("def migrated_lambda(req: func.HttpRequest):\n")
            handle.write("    event = {'httpMethod': req.method, 'body': req.get_body().decode('utf-8', 'replace')}\n")
            handle.write("    result = lambda_handler(event, {})\n")
            handle.write("    return func.HttpResponse(json.dumps(result, default=str), mimetype='application/json')\n")
        with open(os.path.join(temp_root, "host.json"), "w", encoding="utf-8") as handle:
            json.dump({"version": "2.0"}, handle)
        requirements = ["azure-functions"]
        original_requirements = os.path.join(source_dir, "requirements.txt")
        if os.path.isfile(original_requirements):
            with open(original_requirements, "r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    dependency = line.strip()
                    if not dependency or dependency.startswith("#"):
                        continue
                    if re.match(r"(?i)^(boto3|botocore|aws[-_])", dependency):
                        raise ManualReviewRequired("AWS SDK dependencies require manual code conversion.")
                    requirements.append(dependency)
        with open(os.path.join(temp_root, "requirements.txt"), "w", encoding="utf-8") as handle:
            handle.write("\n".join(dict.fromkeys(requirements)) + "\n")
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for root, _, files in os.walk(temp_root):
                for filename in files:
                    full = os.path.join(root, filename)
                    archive.write(full, os.path.relpath(full, temp_root))
        return output.getvalue()
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def _web_client(target):
    if WebSiteManagementClient is None:
        raise RuntimeError("Azure Functions management dependency is unavailable.")
    return WebSiteManagementClient(target["credential"], target["subscription_id"])


def valid_deployment_configuration(configuration):
    if not isinstance(configuration, dict):
        return False
    resource_group = str(configuration.get("resource_group") or "").strip()
    app_name = str(configuration.get("function_app_name") or "").strip()
    slot = str(configuration.get("deployment_slot") or "").strip()
    return bool(_RESOURCE_GROUP.fullmatch(resource_group) and _FUNCTION_APP.fullmatch(app_name) and (not slot or _SLOT.fullmatch(slot)))


def validate_target(target, configuration):
    resource_group = str(configuration.get("resource_group") or "").strip()
    app_name = str(configuration.get("function_app_name") or "").strip()
    slot = str(configuration.get("deployment_slot") or "").strip()
    if not resource_group or not app_name:
        return {"success": False, "message": "Existing Azure resource group and Function App name are required."}
    if not valid_deployment_configuration(configuration):
        return {"success": False, "message": "Azure target identifiers have an invalid format."}
    if not target.get("credential") or not target.get("subscription_id"):
        return {"success": False, "message": "Authenticated Azure target details are required."}
    try:
        client = _web_client(target)
        site = client.web_apps.get_slot(resource_group, app_name, slot) if slot else client.web_apps.get(resource_group, app_name)
        runtime = str(getattr(getattr(site, "site_config", None), "linux_fx_version", "") or "")
        if runtime and "PYTHON" not in runtime.upper():
            return {"success": False, "message": "Target Function App is not configured for a Python runtime."}
        return {"success": True, "client": client, "resource_group": resource_group, "function_app_name": app_name, "slot": slot}
    except (AzureError, RuntimeError, AttributeError):
        return {"success": False, "message": "Azure Function App validation failed. Check target and permissions."}


def _active_lambda_migration(identity):
    return Migration.query.filter(
        Migration.active_identity == identity,
        Migration.status.in_(_ACTIVE_LAMBDA_STATES),
    ).first()


def _lambda_identity(user_id, function_arn, configuration):
    resource_group = str(configuration.get("resource_group") or "").strip()
    app_name = str(configuration.get("function_app_name") or "").strip()
    slot = str(configuration.get("deployment_slot") or "").strip()
    return hashlib.sha256(f"{user_id}|lambda|{function_arn}|{resource_group}|{app_name}|{slot}".encode()).hexdigest()


def _validate_deployed_function(target):
    """Confirm Azure exposes the function generated by the deployed package."""
    web_apps = target["client"].web_apps
    if target["slot"]:
        site = web_apps.get_slot(target["resource_group"], target["function_app_name"], target["slot"])
        functions = web_apps.list_functions_slot(target["resource_group"], target["function_app_name"], target["slot"])
    else:
        site = web_apps.get(target["resource_group"], target["function_app_name"])
        functions = web_apps.list_functions(target["resource_group"], target["function_app_name"])
    function_names = [str(getattr(item, "name", "")) for item in functions]
    if not any(name.rsplit("/", 1)[-1] == "migrated_lambda" for name in function_names):
        raise RuntimeError("Azure did not report the expected deployed function.")
    return site


def _safe_deployment_failure_reason(error):
    """Map provider failures to non-sensitive persisted/API categories."""
    if isinstance(error, requests.Timeout):
        return "Azure ZIP deployment timed out."
    if isinstance(error, requests.ConnectionError):
        return "Azure ZIP deployment connection failed."
    if isinstance(error, requests.HTTPError):
        return "Azure ZIP deployment was rejected by the target service."
    if isinstance(error, (AzureError, ClientError, BotoCoreError)):
        return "Cloud provider validation or deployment failed."
    return "Deployment or target validation failed."


def _persist_lambda_outcome(migration_id, status, failure_reason=None):
    """Persist a terminal Lambda state without storing raw provider errors."""
    migration = Migration.query.filter_by(migration_id=migration_id).first()
    if not migration:
        return None
    migration.status = status
    migration.active_identity = None
    migration.failure_reason = failure_reason[:255] if failure_reason else None
    migration.completed_at = utc_now()
    db.session.commit()
    return migration


def mark_incomplete_lambda_migrations_requires_review():
    """A process restart cannot safely determine Kudu deployment completion.

    Lambda deployment is synchronous and has no durable provider-operation ID,
    so it is intentionally *not* resumed. Owners must inspect the Function App
    and start a fresh approved deployment attempt if appropriate.
    """
    if "migrations" not in inspect(db.engine).get_table_names():
        return 0
    updated = Migration.query.filter(
        Migration.resource_type == "lambda",
        Migration.status.in_(_ACTIVE_LAMBDA_STATES),
    ).update({
        Migration.status: "manual_review_required",
        Migration.active_identity: None,
        Migration.failure_reason: "Deployment was interrupted by an application restart; inspect the target before retrying.",
        Migration.completed_at: utc_now(),
    }, synchronize_session=False)
    if updated:
        db.session.commit()
    return updated


def deploy_lambda(aws_session, azure_target, function_name, configuration, user_id, plan_id=None):
    """Perform real ZIP deployment only after source/target checks succeed."""
    details = get_lambda_details(aws_session, function_name)
    if not details.get("success"):
        return details
    assessment = assess_lambda(details)
    if assessment["classification"] != "supported_execution":
        return {"success": False, "status": "manual_review_required", "message": "Lambda requires manual review.", "reasons": assessment["reasons"]}
    if not details.get("function_arn"):
        return {"success": False, "message": "Lambda source identity was unavailable."}
    identity = _lambda_identity(user_id, details["function_arn"], configuration)
    existing = _active_lambda_migration(identity)
    if existing:
        return {"success": True, "migration_id": existing.migration_id, "status": existing.status,
                "message": "Existing Lambda migration is already active."}
    safe_config = {"function_arn": details["function_arn"], "runtime": details["runtime"], "handler": details["handler"],
                   "function_app_name": str(configuration.get("function_app_name") or "").strip(),
                   "resource_group": str(configuration.get("resource_group") or "").strip(),
                   "deployment_slot": str(configuration.get("deployment_slot") or "").strip(),
                   "compatibility": assessment}
    migration = Migration(migration_id=hashlib.sha256((identity + str(utc_now())).encode()).hexdigest()[:32], user_id=user_id,
                          plan_id=plan_id, active_identity=identity, source_cloud="aws", target_cloud="azure", resource_type="lambda",
                          resource_name=details["function_name"], status="preparing", destination_resource_group=safe_config["resource_group"],
                          destination_storage_account=safe_config["function_app_name"], destination_container=safe_config["deployment_slot"] or None,
                          execution_configuration=json.dumps(safe_config, separators=(",", ":")), started_at=utc_now())
    try:
        db.session.add(migration); db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = _active_lambda_migration(identity)
        if existing:
            return {"success": True, "migration_id": existing.migration_id, "status": existing.status,
                    "message": "Existing Lambda migration is already active."}
        return {"success": False, "message": "Lambda migration could not be prepared safely."}
    target = validate_target(azure_target, configuration)
    if not target.get("success"):
        migration = _persist_lambda_outcome(migration.migration_id, "failed", "Azure Function App target validation failed.")
        return {"success": False, "migration_id": migration.migration_id, "status": "failed",
                "message": "Azure Function App validation failed. Check target and permissions."}
    try:
        migration.status = "deploying"; db.session.commit()
        payload = _download_and_build_package(details["code_location"], details["handler"])
        credentials = (target["client"].web_apps.list_publishing_credentials_slot(target["resource_group"], target["function_app_name"], target["slot"])
                       if target["slot"] else target["client"].web_apps.list_publishing_credentials(target["resource_group"], target["function_app_name"]))
        kudu = f"https://{target['function_app_name']}{('-' + target['slot']) if target['slot'] else ''}.scm.azurewebsites.net/api/zipdeploy?isAsync=false"
        response = requests.post(kudu, data=payload, auth=(credentials.publishing_user_name, credentials.publishing_password), timeout=(15, 300), headers={"Content-Type": "application/zip"})
        response.raise_for_status()
        migration.status = "validating"; db.session.commit()
        _validate_deployed_function(target)
        migration.status = "completed"; migration.completed_at = utc_now(); migration.active_identity = None; db.session.commit()
        return {"success": True, "migration_id": migration.migration_id, "status": "completed", "message": "Azure Functions deployment completed and target validation succeeded."}
    except ManualReviewRequired as exc:
        db.session.rollback()
        migration = _persist_lambda_outcome(migration.migration_id, "manual_review_required", str(exc))
        current_app.logger.info("lambda_deployment_manual_review operation=package_assessment")
        return {"success": False, "migration_id": migration.migration_id, "status": "manual_review_required",
                "message": "Lambda package requires manual review before deployment.", "reasons": [str(exc)]}
    except Exception as error:
        db.session.rollback()
        failure_reason = _safe_deployment_failure_reason(error)
        migration = _persist_lambda_outcome(migration.migration_id, "failed", failure_reason)
        current_app.logger.error("lambda_deployment_failed operation=deploy category=cloud")
        return {"success": False, "migration_id": migration.migration_id, "status": "failed",
                "message": "Lambda deployment failed; review target permissions and deployment diagnostics."}
