from flask import current_app


def _resource_group(resource_id):
    """Extract a resource group from an ARM id without assuming its shape."""
    parts = str(resource_id or "").strip("/").split("/")
    for index, part in enumerate(parts[:-1]):
        if part.lower() == "resourcegroups":
            return parts[index + 1]
    return None


def _value(value, attribute, default=None):
    return getattr(value, attribute, default) if value is not None else default


def _arm_segment(resource_id, segment):
    parts = str(resource_id or "").strip("/").split("/")
    for index, part in enumerate(parts[:-1]):
        if part.lower() == segment.lower():
            return parts[index + 1]
    return None


def _failure(service):
    current_app.logger.error(
        "azure_resource_discovery_failed service=%s operation=scan category=cloud",
        service,
    )
    return {
        "success": False,
        "resources": [],
        "message": "Azure resource discovery was unavailable for this service.",
    }


def scan_virtual_machines(compute_client):
    """Return normalized Azure VM metadata without disk contents or secrets."""
    try:
        resources = []
        for vm in compute_client.virtual_machines.list_all():
            hardware = _value(vm, "hardware_profile")
            storage = _value(vm, "storage_profile")
            os_disk = _value(storage, "os_disk")
            resources.append({
                "service": "Azure Virtual Machine",
                "resource_type": "virtual_machine",
                "resource_id": _value(vm, "id"),
                "name": _value(vm, "name"),
                "resource_group": _resource_group(_value(vm, "id")),
                "location": _value(vm, "location"),
                "vm_size": _value(hardware, "vm_size"),
                "provisioning_state": _value(_value(vm, "properties"), "provisioning_state"),
                "os_type": _value(os_disk, "os_type"),
                "data_disk_count": len(_value(storage, "data_disks", []) or []),
                "availability_zones": list(_value(vm, "zones", []) or []),
            })
        return {"success": True, "resources": resources}
    except Exception:
        return _failure("Azure Virtual Machine")


def scan_storage_accounts(storage_client):
    """Return safe Storage Account configuration metadata; never list keys."""
    try:
        resources = []
        for account in storage_client.storage_accounts.list():
            sku = _value(account, "sku")
            encryption = _value(account, "encryption")
            resources.append({
                "service": "Azure Storage Account",
                "resource_type": "storage_account",
                "resource_id": _value(account, "id"),
                "name": _value(account, "name"),
                "resource_group": _resource_group(_value(account, "id")),
                "location": _value(account, "location"),
                "kind": _value(account, "kind"),
                "sku": _value(sku, "name"),
                "access_tier": _value(account, "access_tier"),
                "https_only": _value(account, "enable_https_traffic_only"),
                "public_network_access": _value(account, "public_network_access"),
                "allow_blob_public_access": _value(account, "allow_blob_public_access"),
                "encryption_enabled": bool(encryption) if encryption is not None else None,
            })
        return {"success": True, "resources": resources}
    except Exception:
        return _failure("Azure Storage Account")


def scan_sql_databases(sql_client):
    """Return Azure SQL database management metadata without connectivity data."""
    try:
        resources = []
        for database in sql_client.databases.list_by_subscription():
            sku = _value(database, "sku")
            resources.append({
                "service": "Azure SQL Database",
                "resource_type": "sql_database",
                "resource_id": _value(database, "id"),
                "name": _value(database, "name"),
                "resource_group": _resource_group(_value(database, "id")),
                "server_name": _arm_segment(_value(database, "id"), "servers"),
                "location": _value(database, "location"),
                "status": _value(database, "status"),
                "sku": _value(sku, "name"),
                "sku_tier": _value(sku, "tier"),
                "max_size_bytes": _value(database, "max_size_bytes"),
                "collation": _value(database, "collation"),
            })
        return {"success": True, "resources": resources}
    except Exception:
        return _failure("Azure SQL Database")


def scan_all_resources(compute_client, storage_client, sql_client):
    """Discover each service independently so one provider error is isolated."""
    return {
        "azure_virtual_machines": scan_virtual_machines(compute_client),
        "azure_storage_accounts": scan_storage_accounts(storage_client),
        "azure_sql_databases": scan_sql_databases(sql_client),
    }
