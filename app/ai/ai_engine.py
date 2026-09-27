"""
==========================================================
AI CLOUD MIGRATION
AI ENGINE
==========================================================

Analyzes scanned cloud resources and generates
migration recommendations based on:

    Source Cloud
    Target Cloud
    Source Service
"""

from app.mappers.cloud_mapper import get_cloud_mapping


# ==========================================================
# AI ENGINE
# ==========================================================

class AIEngine:

    # ------------------------------------------------------
    # NORMALIZE CLOUD NAME
    # ------------------------------------------------------

    def normalize_cloud_name(self, cloud_name):

        cloud_names = {

            "aws": "AWS",

            "azure": "Azure",

            "gcp": "GCP",

            "google": "GCP",

            "google cloud": "GCP",

            "google cloud platform": "GCP"

        }


        return cloud_names.get(

            str(cloud_name).strip().lower(),

            str(cloud_name).strip()

        )


    # ------------------------------------------------------
    # ANALYZE RESOURCES
    # ------------------------------------------------------

    def analyze_resources(

        self,
        resources,
        source_cloud,
        target_cloud

    ):

        recommendations = []


        # --------------------------------------------------
        # NORMALIZE CLOUD NAMES
        # --------------------------------------------------

        source_cloud = self.normalize_cloud_name(

            source_cloud

        )


        target_cloud = self.normalize_cloud_name(

            target_cloud

        )


        # --------------------------------------------------
        # LOOP THROUGH ALL SCANNED SERVICES
        # --------------------------------------------------

        for service_key, service_data in resources.items():

            # Skip unsuccessful scans

            if not service_data.get("success"):

                continue


            # Get resources from scanner

            scanned_resources = service_data.get(

                "resources",

                []

            )


            # --------------------------------------------------
            # FIND EACH RESOURCE
            # --------------------------------------------------

            for resource in scanned_resources:


                # Get service name

                source_service = resource.get(

                    "service"

                )


                # --------------------------------------------------
                # GET MAPPING
                # --------------------------------------------------

                mapping = get_cloud_mapping(

                    source_cloud,

                    target_cloud,

                    source_service,

                    resource=resource

                )


                # --------------------------------------------------
                # IF MAPPING DOES NOT EXIST
                # --------------------------------------------------

                if not mapping:

                    recommendations.append({

                        "source_service":

                            source_service,

                        "target_service":

                            "Manual Review Required",

                        "resource_name":

                            resource.get(

                                "name",

                                "Unknown"

                            ),

                        "resource_id":

                            resource.get(

                                "resource_id",

                                resource.get(

                                "instance_id",

                                resource.get(

                                    "bucket_name",

                                    resource.get(

                                        "id",

                                        "Unknown"

                                    )

                                )

                                )

                            ),

                        "compatibility":

                            0,

                        "recommended_size":

                            "Manual Configuration",

                        "execution_classification":

                            "unsupported",

                        "status":

                            "Unsupported — manual review required"

                    })

                    continue


                # --------------------------------------------------
                # CREATE RECOMMENDATION
                # --------------------------------------------------

                recommendation = {

                    "source_service":

                        source_service,

                    "target_service":

                        mapping.get(

                            "target_service"

                        ),

                    "resource_name":

                        resource.get(

                            "name",

                            resource.get(

                                "bucket_name",

                                resource.get(

                                    "id",

                                    "Unknown"

                                )

                            )

                        ),

                    "resource_id":

                        resource.get(

                            "resource_id",

                            resource.get(

                            "instance_id",

                            resource.get(

                                "bucket_name",

                                resource.get(

                                    "id",

                                    "Unknown"

                                )

                            )

                            )

                        ),

                    "compatibility":

                        mapping.get(

                            "compatibility",

                            0

                        ),

                    "recommended_size":

                        self.get_recommended_size(

                            source_service,

                            resource,

                            target_cloud

                        ),

                    "execution_classification":

                        mapping.get(

                            "execution_classification",

                            "unsupported"

                        ),

                    "status":

                        mapping.get(

                            "status",

                            "Manual review required"

                        )

                }


                recommendations.append(

                    recommendation

                )


        return recommendations


    # ------------------------------------------------------
    # RECOMMENDED SIZE
    # ------------------------------------------------------

    def get_recommended_size(

        self,
        source_service,
        resource,
        target_cloud

    ):

        # Normalize target cloud

        target_cloud = self.normalize_cloud_name(

            target_cloud

        )


        # ==================================================
        # AWS EC2
        # ==================================================

        if source_service == "EC2":

            instance_type = resource.get(

                "type"

            )


            # --------------------------------------------------
            # AWS -> AZURE
            # --------------------------------------------------

            azure_mapping = {

                "t2.micro":

                    "Standard_B1s",

                "t2.small":

                    "Standard_B2s",

                "t2.medium":

                    "Standard_B2ms",

                "t3.micro":

                    "Standard_B1s",

                "t3.small":

                    "Standard_B2s",

                "t3.medium":

                    "Standard_B2ms"

            }


            # AWS -> Azure

            if target_cloud == "Azure":

                return azure_mapping.get(

                    instance_type,

                    "Standard_B2s"

                )


            # --------------------------------------------------
            # AWS -> GCP
            # --------------------------------------------------

            if target_cloud == "GCP":

                gcp_mapping = {

                    "t2.micro":

                        "e2-micro",

                    "t2.small":

                        "e2-small",

                    "t2.medium":

                        "e2-medium",

                    "t3.micro":

                        "e2-micro",

                    "t3.small":

                        "e2-small",

                    "t3.medium":

                        "e2-medium"

                }


                return gcp_mapping.get(

                    instance_type,

                    "e2-small"

                )


        # ==================================================
        # STORAGE
        # ==================================================

        if source_service in [

            "S3",

            "Azure Blob Storage",

            "GCS",

            "Google Cloud Storage"

        ]:

            return "Storage Configuration Required"


        # ==================================================
        # DATABASE
        # ==================================================

        if source_service in [

            "RDS",

            "Azure SQL Database",

            "Cloud SQL"

        ]:

            return "Database Configuration Required"


        # ==================================================
        # DEFAULT
        # ==================================================

        return "Standard Configuration"


# ==========================================================
# GLOBAL OBJECT
# ==========================================================

ai_engine = AIEngine()
