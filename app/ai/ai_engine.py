from app.mappers.cloud_mapper import get_cloud_mapping


class AIEngine:
    def normalize_cloud_name(self, cloud_name):
        names = {"aws": "AWS", "azure": "Azure"}
        return names.get(str(cloud_name).strip().lower(), str(cloud_name).strip())

    def analyze_resources(self, resources, source_cloud, target_cloud):
        """Produce safe recommendations for normalized AWS inventory only."""
        source = self.normalize_cloud_name(source_cloud)
        target = self.normalize_cloud_name(target_cloud)
        recommendations = []
        for service_data in (resources or {}).values():
            if not isinstance(service_data, dict) or not service_data.get("success"):
                continue
            for resource in service_data.get("resources", []):
                service = resource.get("service")
                mapping = get_cloud_mapping(source, target, service, resource=resource)
                resource_id = resource.get("resource_id") or resource.get("instance_id") or resource.get("bucket_name") or resource.get("id") or "Unknown"
                if not mapping:
                    recommendations.append({
                        "source_service": service,
                        "target_service": "Manual Review Required",
                        "resource_name": resource.get("name") or resource_id,
                        "resource_id": resource_id,
                        "compatibility": 0,
                        "recommended_size": "Manual Configuration",
                        "execution_classification": "unsupported",
                        "status": "Unsupported — outside the AWS to Azure scope",
                    })
                    continue
                recommendations.append({
                    "source_service": service,
                    "target_service": mapping["target_service"],
                    "resource_name": resource.get("name") or resource_id,
                    "resource_id": resource_id,
                    "compatibility": mapping.get("compatibility", 0),
                    "recommended_size": self.get_recommended_size(service, resource),
                    "execution_classification": mapping["execution_classification"],
                    "status": mapping["status"],
                })
        return recommendations

    def get_recommended_size(self, source_service, resource):
        if source_service == "EC2":
            return {
                "t2.micro": "Standard_B1s", "t2.small": "Standard_B2s", "t2.medium": "Standard_B2ms",
                "t3.micro": "Standard_B1s", "t3.small": "Standard_B2s", "t3.medium": "Standard_B2ms",
            }.get(resource.get("type"), "Azure VM assessment required")
        if source_service == "S3":
            return "Standard Storage Account"
        if source_service == "RDS":
            return "Database migration assessment required"
        if source_service == "Lambda":
            return "Azure Functions compatibility assessment required"
        return "Manual Configuration"


ai_engine = AIEngine()
