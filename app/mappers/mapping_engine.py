from app.utils.time import utc_now


class MappingEngine:

    def generate_plan(
        self,
        source_cloud,
        target_cloud,
        recommendations
    ):

        plan = {

            "migration_id":
                utc_now().strftime(
                    "MIG-%Y%m%d-%H%M%S"
                ),

            "source_cloud":
                source_cloud,

            "target_cloud":
                target_cloud,

            "created_at":
                utc_now().strftime(
                    "%d-%m-%Y %H:%M:%S"
                ),

            "total_resources":
                len(recommendations),

            "estimated_duration": "requires_assessment",

            "status":
                "Prepared for review",

            "resources":
                []

        }

        for recommendation in recommendations:

            plan["resources"].append({

                "source":
                    recommendation["source_service"],

                "target":
                    recommendation["target_service"],

                "name":
                    recommendation["resource_name"],

                "compatibility":
                    recommendation["compatibility"],

                "recommended_size":
                    recommendation.get(
                        "recommended_size",
                        "-"
                    ),

                "execution_classification":
                    recommendation.get(
                        "execution_classification",
                        "unsupported"
                    ),

                "status":
                    recommendation["status"]

            })

        return plan


mapping_engine = MappingEngine()
