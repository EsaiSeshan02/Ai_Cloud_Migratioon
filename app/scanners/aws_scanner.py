from flask import current_app
from botocore.exceptions import BotoCoreError, ClientError


def _scan_failure(event, message):
    current_app.logger.error("%s operation=scan category=cloud", event)
    return {"success": False, "count": 0, "resources": [], "message": message}


def _name_from_tags(tags, default="Unnamed"):
    for tag in tags or []:
        if tag.get("Key") == "Name":
            return tag.get("Value") or default
    return default


def _ebs_mappings(instance):
    root_device = instance.get("RootDeviceName")
    volumes = []
    root_volume = None
    for mapping in instance.get("BlockDeviceMappings", []):
        ebs = mapping.get("Ebs") or {}
        item = {
            "device_name": mapping.get("DeviceName"),
            "volume_id": ebs.get("VolumeId"),
            "delete_on_termination": ebs.get("DeleteOnTermination"),
            "encrypted": ebs.get("Encrypted"),
        }
        volumes.append(item)
        if mapping.get("DeviceName") == root_device:
            root_volume = item
    return root_device, root_volume, volumes


def _security_groups(instance):
    return [
        {"group_id": group.get("GroupId"), "group_name": group.get("GroupName")}
        for group in instance.get("SecurityGroups", [])
    ]


def scan_ec2(session):
    """Paginate EC2 instances and return migration-assessment metadata."""
    try:
        paginator = session.client("ec2").get_paginator("describe_instances")
        resources = []
        for page in paginator.paginate():
            for reservation in page.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    root_device, root_volume, volumes = _ebs_mappings(instance)
                    instance_id = instance.get("InstanceId", "Unknown")
                    resources.append({
                        "service": "EC2",
                        "resource_type": "aws_ec2_instance",
                        "resource_id": instance_id,
                        "instance_id": instance_id,
                        "name": _name_from_tags(instance.get("Tags"), instance_id),
                        "type": instance.get("InstanceType"),
                        "state": (instance.get("State") or {}).get("Name"),
                        "availability_zone": (instance.get("Placement") or {}).get("AvailabilityZone"),
                        "image_id": instance.get("ImageId"),
                        "architecture": instance.get("Architecture"),
                        "platform": instance.get("PlatformDetails") or instance.get("Platform") or "unknown",
                        "root_device_name": root_device,
                        "root_device_type": instance.get("RootDeviceType"),
                        "root_volume": root_volume,
                        "ebs_volumes": volumes,
                        "vpc_id": instance.get("VpcId"),
                        "subnet_id": instance.get("SubnetId"),
                        "security_groups": _security_groups(instance),
                    })
        return {"success": True, "count": len(resources), "resources": resources}
    except (ClientError, BotoCoreError):
        return _scan_failure("aws_ec2_scan_failed", "Unable to scan EC2 resources.")
    except Exception:
        return _scan_failure("aws_ec2_scan_failed", "Unable to scan EC2 resources.")


def _bucket_region(s3, bucket_name):
    try:
        location = s3.get_bucket_location(Bucket=bucket_name).get("LocationConstraint")
        return "us-east-1" if location in (None, "") else ("eu-west-1" if location == "EU" else location)
    except (ClientError, BotoCoreError):
        return None


def _bucket_versioning(s3, bucket_name):
    try:
        return s3.get_bucket_versioning(Bucket=bucket_name).get("Status", "Disabled")
    except (ClientError, BotoCoreError):
        return "Unknown"


def _bucket_encryption(s3, bucket_name):
    try:
        rules = s3.get_bucket_encryption(Bucket=bucket_name).get("ServerSideEncryptionConfiguration", {}).get("Rules", [])
        return "Configured" if rules else "Not configured"
    except ClientError as error:
        code = str(error.response.get("Error", {}).get("Code", ""))
        if code == "ServerSideEncryptionConfigurationNotFoundError":
            return "Not configured"
        return "Unknown"
    except BotoCoreError:
        return "Unknown"


def scan_s3(session):
    """Assess bucket configuration without listing or downloading objects."""
    try:
        s3 = session.client("s3")
        resources = []
        for bucket in s3.list_buckets().get("Buckets", []):
            name = bucket.get("Name", "Unnamed")
            created = bucket.get("CreationDate")
            resources.append({
                "service": "S3",
                "resource_type": "aws_s3_bucket",
                "resource_id": name,
                "bucket_name": name,
                "name": name,
                "creation_date": str(created) if created else "-",
                "region": _bucket_region(s3, name),
                "versioning_status": _bucket_versioning(s3, name),
                "encryption_status": _bucket_encryption(s3, name),
                "object_inventory_scanned": False,
            })
        return {"success": True, "count": len(resources), "resources": resources}
    except (ClientError, BotoCoreError):
        return _scan_failure("aws_s3_scan_failed", "Unable to scan S3 resources.")
    except Exception:
        return _scan_failure("aws_s3_scan_failed", "Unable to scan S3 resources.")


def scan_rds(session):
    """Paginate RDS instance metadata; no database connection is attempted."""
    try:
        paginator = session.client("rds").get_paginator("describe_db_instances")
        resources = []
        for page in paginator.paginate():
            for database in page.get("DBInstances", []):
                identifier = database.get("DBInstanceIdentifier", "Unknown")
                engine = database.get("Engine")
                resources.append({
                    "service": "RDS",
                    "resource_type": "aws_rds_instance",
                    "resource_id": identifier,
                    "name": identifier,
                    "identifier": identifier,
                    "engine": engine,
                    "engine_family": _rds_engine_family(engine),
                    "engine_version": database.get("EngineVersion"),
                    "instance_class": database.get("DBInstanceClass"),
                    "status": database.get("DBInstanceStatus"),
                    "availability_zone": database.get("AvailabilityZone"),
                    "allocated_storage_gb": database.get("AllocatedStorage"),
                    "storage_type": database.get("StorageType"),
                    "storage_encrypted": database.get("StorageEncrypted"),
                    "multi_az": database.get("MultiAZ"),
                    "publicly_accessible": database.get("PubliclyAccessible"),
                    "backup_retention_days": database.get("BackupRetentionPeriod"),
                    "endpoint_configured": bool(database.get("Endpoint")),
                })
        return {"success": True, "count": len(resources), "resources": resources}
    except (ClientError, BotoCoreError):
        return _scan_failure("aws_rds_scan_failed", "Unable to scan RDS resources.")
    except Exception:
        return _scan_failure("aws_rds_scan_failed", "Unable to scan RDS resources.")


def _rds_engine_family(engine):
    value = str(engine or "").lower()
    if "aurora" in value:
        return "aurora_postgresql" if "postgres" in value else "aurora_mysql"
    if value.startswith("postgres"):
        return "postgresql"
    if value.startswith("mysql"):
        return "mysql"
    if value.startswith("sqlserver"):
        return "sql_server"
    return "other"


def _event_source_type(arn):
    value = str(arn or "").lower()
    for source in ("dynamodb", "kinesis", "sqs", "kafka", "mq"):
        if source in value:
            return source
    return "other"


def _lambda_event_sources(client, function_name):
    """Return source types only, deliberately excluding event-source ARNs."""
    try:
        paginator = client.get_paginator("list_event_source_mappings")
        types = set()
        for page in paginator.paginate(FunctionName=function_name):
            for mapping in page.get("EventSourceMappings", []):
                types.add(_event_source_type(mapping.get("EventSourceArn")))
        return sorted(types), True
    except (ClientError, BotoCoreError):
        return [], False


def scan_lambda(session):
    """Paginate Lambda metadata and retrieve safe configuration details.

    ``list_functions`` does not include environment configuration. A separate
    ``get_function_configuration`` call supplies names only, never values.
    """
    try:
        client = session.client("lambda")
        paginator = client.get_paginator("list_functions")
        resources = []
        for page in paginator.paginate():
            for function in page.get("Functions", []):
                name = function.get("FunctionName", "Unknown")
                event_sources, event_source_discovery_available = _lambda_event_sources(client, name)
                try:
                    configuration = client.get_function_configuration(FunctionName=name)
                except (ClientError, BotoCoreError, AttributeError):
                    configuration = {}
                vpc_config = configuration.get("VpcConfig") or function.get("VpcConfig") or {}
                environment = (configuration.get("Environment") or {}).get("Variables") or {}
                resources.append({
                    "service": "Lambda",
                    "resource_type": "aws_lambda_function",
                    "resource_id": name,
                    "function_arn": configuration.get("FunctionArn") or function.get("FunctionArn"),
                    "name": name,
                    "runtime": configuration.get("Runtime") or function.get("Runtime"),
                    "architectures": function.get("Architectures", []),
                    "architecture": (function.get("Architectures") or [None])[0],
                    "memory_mb": configuration.get("MemorySize") or function.get("MemorySize"),
                    "timeout_seconds": configuration.get("Timeout") or function.get("Timeout"),
                    "last_modified": function.get("LastModified"),
                    "handler": configuration.get("Handler") or function.get("Handler"),
                    "package_type": configuration.get("PackageType", function.get("PackageType", "Zip")),
                    "description": configuration.get("Description") or function.get("Description"),
                    "vpc_enabled": bool(vpc_config.get("VpcId")),
                    "layers_count": len(function.get("Layers") or []),
                    "tracing_mode": (function.get("TracingConfig") or {}).get("Mode"),
                    "event_source_types": event_sources,
                    "event_source_discovery_available": event_source_discovery_available,
                    "environment_variables_included": False,
                    "environment_variable_names": sorted(str(key) for key in environment),
                })
        return {"success": True, "count": len(resources), "resources": resources}
    except (ClientError, BotoCoreError):
        return _scan_failure("aws_lambda_scan_failed", "Unable to scan Lambda resources.")
    except Exception:
        return _scan_failure("aws_lambda_scan_failed", "Unable to scan Lambda resources.")


def scan_all_resources(session):
    """Return a uniform service-result shape consumed by AIEngine."""
    return {
        "ec2": scan_ec2(session),
        "s3": scan_s3(session),
        "rds": scan_rds(session),
        "lambda": scan_lambda(session),
    }
