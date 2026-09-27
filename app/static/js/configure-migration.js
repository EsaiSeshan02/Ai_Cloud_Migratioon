/* ==========================================================
                AI CLOUD MIGRATION
                CONFIGURE MIGRATION
========================================================== */


/* ==========================================================
                PAGE INITIALIZATION
========================================================== */

document.addEventListener(
    "DOMContentLoaded",
    () => {

        initializeConfigureMigration();

    }
);


/* ==========================================================
                INITIALIZE PAGE
========================================================== */

function initializeConfigureMigration() {

    console.log(
        "Configure Migration page initialized."
    );


    /* ======================================================
            GET MIGRATION INFORMATION
    ====================================================== */

    const migrationInfo =
        loadMigrationInformation();


    if (!migrationInfo.sourceSessionId) {

        console.error(
            "Source session ID is missing."
        );

        showPageError(
            "Source cloud session is missing. Please start the migration again."
        );

        return;

    }


    if (!migrationInfo.targetSessionId) {

        console.error(
            "Target session ID is missing."
        );

        showPageError(
            "Target cloud session is missing. Please connect the target cloud again."
        );

        return;

    }


    /* ======================================================
            LOAD SELECTED RESOURCE
    ====================================================== */

    const resource =
        loadSelectedResource();


    if (!resource) {

        console.error(
            "No selected migration resource found."
        );

        showPageError(
            "Selected migration resource was not found. Please return to the migration dashboard and select a resource again."
        );

        return;

    }


    /* ======================================================
            SAVE SESSION INFORMATION
    ====================================================== */

    saveMigrationSessions(
        migrationInfo
    );


    /* ======================================================
            DISPLAY RESOURCE
    ====================================================== */

    displayResourceInformation(
        resource
    );

    configureServiceSpecificFields(resource);


    /* ======================================================
            GET TARGET CLOUD
    ====================================================== */

    const targetCloud =
        getTargetCloud(
            resource,
            migrationInfo
        );


    /* ======================================================
            SAVE CLOUD INFORMATION
    ====================================================== */

    sessionStorage.setItem(
        "migration_source",
        migrationInfo.sourceCloud
    );

    sessionStorage.setItem(
        "migration_target",
        targetCloud
    );


    /* ======================================================
            LOAD TARGET REGIONS
    ====================================================== */

    loadTargetRegions(
        targetCloud
    );


    /* ======================================================
            PRE-FILL FORM
    ====================================================== */

    prefillConfiguration(
        resource
    );


    /* ======================================================
            INITIALIZE FORM
    ====================================================== */

    initializeConfigurationForm(
        resource,
        targetCloud
    );


    /* ======================================================
            REFRESH LUCIDE ICONS
    ====================================================== */

    refreshIcons();

}


/* ==========================================================
                LOAD MIGRATION INFORMATION
========================================================== */

function loadMigrationInformation() {

    const params =
        new URLSearchParams(
            window.location.search
        );


    /* ======================================================
            SOURCE CLOUD
    ====================================================== */

    const urlSourceCloud =
        params.get(
            "source"
        );


    const storedSourceCloud =
        sessionStorage.getItem(
            "migration_source"
        );


    const sourceCloud =
        (
            urlSourceCloud ||
            storedSourceCloud ||
            ""
        ).trim().toLowerCase();


    /* ======================================================
            TARGET CLOUD
    ====================================================== */

    const urlTargetCloud =
        params.get(
            "target"
        );


    const storedTargetCloud =
        sessionStorage.getItem(
            "migration_target"
        );


    const targetCloud =
        (
            urlTargetCloud ||
            storedTargetCloud ||
            ""
        ).trim().toLowerCase();


    /* ======================================================
            SOURCE SESSION
    ====================================================== */

    const urlSourceSessionId =
        params.get(
            "source_session_id"
        );


    const storedSourceSessionId =
        sessionStorage.getItem(
            "source_session_id"
        );


    const sourceSessionId =
        (
            urlSourceSessionId ||
            storedSourceSessionId ||
            ""
        ).trim();


    /* ======================================================
            TARGET SESSION
    ====================================================== */

    const urlTargetSessionId =
        params.get(
            "target_session_id"
        );


    const storedTargetSessionId =
        sessionStorage.getItem(
            "target_session_id"
        );


    const targetSessionId =
        (
            urlTargetSessionId ||
            storedTargetSessionId ||
            ""
        ).trim();


    return {

        sourceCloud:
            sourceCloud,

        targetCloud:
            targetCloud,

        sourceSessionId:
            sourceSessionId,

        targetSessionId:
            targetSessionId

    };

}


/* ==========================================================
                SAVE MIGRATION SESSIONS
========================================================== */

function saveMigrationSessions(
    migrationInfo
) {

    if (
        migrationInfo.sourceCloud
    ) {

        sessionStorage.setItem(
            "migration_source",
            migrationInfo.sourceCloud
        );

    }


    if (
        migrationInfo.targetCloud
    ) {

        sessionStorage.setItem(
            "migration_target",
            migrationInfo.targetCloud
        );

    }


    if (
        migrationInfo.sourceSessionId
    ) {

        sessionStorage.setItem(
            "source_session_id",
            migrationInfo.sourceSessionId
        );

    }


    if (
        migrationInfo.targetSessionId
    ) {

        sessionStorage.setItem(
            "target_session_id",
            migrationInfo.targetSessionId
        );

    }


    console.log(
        "Migration sessions saved successfully."
    );

}


/* ==========================================================
                LOAD SELECTED RESOURCE
========================================================== */

function loadSelectedResource() {

    const storedResource =
        sessionStorage.getItem(
            "selected_migration_resource"
        );


    if (!storedResource) {

        return null;

    }


    try {

        const resource =
            JSON.parse(
                storedResource
            );


        return resource;

    }

    catch (error) {

        console.error(
            "Unable to parse selected resource:",
            error
        );


        sessionStorage.removeItem(
            "selected_migration_resource"
        );


        return null;

    }

}


/* ==========================================================
                DISPLAY RESOURCE INFORMATION
========================================================== */

function displayResourceInformation(
    resource
) {

    const resourceName =
        document.getElementById(
            "selected-resource-name"
        );


    const sourceService =
        document.getElementById(
            "selected-source-service"
        );


    const targetService =
        document.getElementById(
            "selected-target-service"
        );


    const compatibility =
        document.getElementById(
            "selected-compatibility"
        );


    const configuration =
        document.getElementById(
            "selected-configuration"
        );


    /* ======================================================
            RESOURCE NAME
    ====================================================== */

    if (resourceName) {

        resourceName.textContent =
            resource.name ||
            resource.resource_name ||
            resource.bucket_name ||
            "Unnamed Resource";

    }


    /* ======================================================
            SOURCE SERVICE
    ====================================================== */

    if (sourceService) {

        sourceService.textContent =
            resource.source ||
            resource.source_service ||
            resource.service ||
            "Unknown";

    }


    /* ======================================================
            TARGET SERVICE
    ====================================================== */

    if (targetService) {

        targetService.textContent =
            resource.target ||
            resource.target_service ||
            "Manual Review";

    }


    /* ======================================================
            COMPATIBILITY
    ====================================================== */

    if (compatibility) {

        const compatibilityValue =
            resource.compatibility;


        if (
            compatibilityValue !== undefined &&
            compatibilityValue !== null
        ) {

            compatibility.textContent =
                `${compatibilityValue}%`;

        }

        else {

            compatibility.textContent =
                "N/A";

        }

    }


    /* ======================================================
            RECOMMENDED CONFIGURATION
    ====================================================== */

    if (configuration) {

        configuration.textContent =
            resource.recommended_size ||
            resource.recommended_configuration ||
            "N/A";

    }

}


/* ==========================================================
                GET TARGET CLOUD
========================================================== */

function getTargetCloud(
    resource,
    migrationInfo
) {

    /* ======================================================
            1. RESOURCE TARGET CLOUD
    ====================================================== */

    if (
        resource.target_cloud
    ) {

        return resource.target_cloud
            .toLowerCase();

    }


    /* ======================================================
            2. URL / MIGRATION TARGET
    ====================================================== */

    if (
        migrationInfo &&
        migrationInfo.targetCloud
    ) {

        return migrationInfo.targetCloud
            .toLowerCase();

    }


    /* ======================================================
            3. SESSION STORAGE
    ====================================================== */

    const storedTarget =
        sessionStorage.getItem(
            "migration_target"
        ) ||
        sessionStorage.getItem(
            "target_cloud"
        );


    if (storedTarget) {

        return storedTarget
            .toLowerCase();

    }


    /* ======================================================
            4. DETECT FROM TARGET SERVICE
    ====================================================== */

    const targetService =
        (
            resource.target ||
            resource.target_service ||
            ""
        ).toLowerCase();


    if (
        targetService.includes(
            "azure"
        )
    ) {

        return "azure";

    }


    /* ======================================================
            DEFAULT
    ====================================================== */

    return "azure";

}


/* ==========================================================
                LOAD TARGET REGIONS
========================================================== */

function loadTargetRegions(
    targetCloud
) {

    const regionSelect =
        document.getElementById(
            "target-region"
        );


    if (!regionSelect) {

        console.warn(
            "Target region select not found."
        );

        return;

    }


    /* ======================================================
            CLOUD REGIONS
    ====================================================== */

    const cloudRegions = {

        azure: [

            {
                value: "eastus",
                label: "East US"
            },

            {
                value: "eastus2",
                label: "East US 2"
            },

            {
                value: "centralus",
                label: "Central US"
            },

            {
                value: "westus",
                label: "West US"
            },

            {
                value: "centralindia",
                label: "Central India"
            },

            {
                value: "southindia",
                label: "South India"
            }

        ]

    };


    const regions =
        cloudRegions[targetCloud] ||
        [];


    /* ======================================================
            RESET OPTIONS
    ====================================================== */

    regionSelect.innerHTML =
        `
        <option value="">
            Select target region
        </option>
        `;


    /* ======================================================
            ADD REGIONS
    ====================================================== */

    regions.forEach(
        region => {

            const option =
                document.createElement(
                    "option"
                );


            option.value =
                region.value;


            option.textContent =
                region.label;


            regionSelect.appendChild(
                option
            );

        }
    );

}


/* ==========================================================
                PRE-FILL CONFIGURATION
========================================================== */

function prefillConfiguration(
    resource
) {

    const nameInput =
        document.getElementById(
            "target-resource-name"
        );


    const sizeSelect =
        document.getElementById(
            "target-size"
        );


    /* ======================================================
            RESOURCE NAME
    ====================================================== */

    if (nameInput) {

        nameInput.value =
            resource.name ||
            resource.resource_name ||
            resource.bucket_name ||
            "";

    }


    /* ======================================================
            RECOMMENDED SIZE
    ====================================================== */

    if (
        sizeSelect &&
        resource.recommended_size
    ) {

        const recommendedSize =
            resource.recommended_size;


        const matchingOption =
            Array.from(
                sizeSelect.options
            ).find(
                option =>
                    option.value ===
                    recommendedSize
            );


        if (matchingOption) {

            sizeSelect.value =
                recommendedSize;

        }

    }

}


/* ==========================================================
                INITIALIZE CONFIGURATION FORM
========================================================== */

function initializeConfigurationForm(
    resource,
    targetCloud
) {

    const form =
        document.getElementById(
            "migration-config-form"
        );


    const startMigrationButton =
        document.getElementById(
            "start-migration-btn"
        );


    if (!form) {

        console.error(
            "Migration configuration form not found."
        );

        return;

    }


    /* ======================================================
            SAVE CONFIGURATION
    ====================================================== */

    form.addEventListener(
        "submit",
        event => {

            event.preventDefault();


            saveConfiguration(
                resource,
                targetCloud
            );

        }
    );


    /* ======================================================
            START MIGRATION
    ====================================================== */

    if (startMigrationButton) {

        startMigrationButton.addEventListener(
            "click",
            event => {

                event.preventDefault();


                startMigration();

            }
        );

    }

}


function executionPath(resource) {
    const service = String(resource.source || resource.source_service || resource.service || "").toUpperCase();
    if (service === "S3") return "s3";
    // Lambda remains planning-only in the generic mapper. This path only
    // exposes its already-gated dedicated workflow; the backend still requires
    // an approved plan, supported package, and validated existing Function App.
    if (service === "LAMBDA") return "lambda";
    return "planning";
}


/* ==========================================================
                SAVE CONFIGURATION
========================================================== */

function saveConfiguration(
    resource,
    targetCloud
) {

    const path = executionPath(resource);
    if (path === "planning") {
        const status = document.getElementById("configuration-status");
        if (status) status.textContent = "Planning / manual review required";
        return;
    }

    const nameInput =
        document.getElementById(
            "target-resource-name"
        );


    const regionSelect =
        document.getElementById(
            "target-region"
        );


    const sizeSelect =
        document.getElementById(
            "target-size"
        );


    const statusElement =
        document.getElementById(
            "configuration-status"
        );


    const startMigrationButton =
        document.getElementById(
            "start-migration-btn"
        );


    /* ======================================================
            VALIDATE ELEMENTS
    ====================================================== */

    if (!nameInput || !regionSelect || !sizeSelect) {

        alert(
            "Migration configuration form is incomplete."
        );

        return;

    }


    /* ======================================================
            VALIDATE VALUES
    ====================================================== */

    const resourceGroup = document.getElementById("azure-resource-group")?.value.trim() || "";
    const functionAppName = document.getElementById("azure-function-app-name")?.value.trim() || "";
    const deploymentSlot = document.getElementById("azure-deployment-slot")?.value.trim() || "";
    if (path === "s3" && (!nameInput.value.trim() || !regionSelect.value || !sizeSelect.value)) {

        alert(
            "Please complete all configuration fields."
        );

        return;

    }

    if (path === "lambda" && (!resourceGroup || !functionAppName)) {
        alert("Provide an existing Azure resource group and Function App for the Lambda target.");
        return;
    }


    /* ======================================================
            GET SESSION IDS
    ====================================================== */

    const sourceSessionId =
        sessionStorage.getItem(
            "source_session_id"
        );


    const targetSessionId =
        sessionStorage.getItem(
            "target_session_id"
        );


    if (!sourceSessionId) {

        alert(
            "Source cloud session is missing. Please reconnect the source cloud."
        );

        return;

    }


    if (!targetSessionId) {

        alert(
            "Target cloud session is missing. Please reconnect the target cloud."
        );

        return;

    }


    /* ======================================================
            CREATE CONFIGURATION OBJECT
    ====================================================== */

    const configuration = {

        /* SESSION INFORMATION */

        source_session_id:
            sourceSessionId,

        target_session_id:
            targetSessionId,


        /* RESOURCE INFORMATION */

        resource_name:
            resource.name ||
            resource.resource_name ||
            resource.bucket_name ||
            "",

        source_service:
            resource.source ||
            resource.source_service ||
            resource.service ||
            "",

        target_service:
            resource.target ||
            resource.target_service ||
            "",

        compatibility:
            resource.compatibility ??
            null,


        /* CLOUD */

        source_cloud:
            sessionStorage.getItem(
                "migration_source"
            ) || "",

        target_cloud:
            targetCloud,


        /* TARGET CONFIGURATION */

        target_resource_name:
            path === "s3" ? nameInput.value.trim() : "",

        target_region:
            path === "s3" ? regionSelect.value : "",

        target_size:
            path === "s3" ? sizeSelect.value : "",

        provision_destination:
            document.getElementById("provision-destination")?.checked === true,

        resource_group:
            resourceGroup,

        function_app_name:
            functionAppName,

        deployment_slot:
            deploymentSlot,


        /* STATUS */

        status:
            "Configured",

        configured_at:
            new Date().toISOString()

    };


    /* ======================================================
            SAVE CONFIGURATION
    ====================================================== */

    sessionStorage.setItem(
        "migration_configuration",
        JSON.stringify(
            configuration
        )
    );


    /* ======================================================
            UPDATE STATUS
    ====================================================== */

    if (statusElement) {

        statusElement.textContent = path === "lambda"
            ? (sessionStorage.getItem("persisted_migration_plan_id")
                ? "Target configured; backend package and target validation still required"
                : "Target configured; save and approve a persisted plan before deployment")
            : "Configured";

    }


    /* ======================================================
            ENABLE START BUTTON
    ====================================================== */

    if (startMigrationButton) {

        startMigrationButton.disabled = path === "lambda" && !sessionStorage.getItem("persisted_migration_plan_id");

    }


    /* ======================================================
            SUCCESS
    ====================================================== */

    alert(
        "Migration configuration saved successfully!"
    );


    console.log(
        "Configuration saved successfully."
    );

}


/* ==========================================================
                START MIGRATION
========================================================== */

async function startMigration() {

    /* ======================================================
            LOAD CONFIGURATION
    ====================================================== */

    const storedConfiguration =
        sessionStorage.getItem(
            "migration_configuration"
        );


    if (!storedConfiguration) {

        alert(
            "Please save the configuration first."
        );

        return;

    }


    let configuration;


    try {

        configuration =
            JSON.parse(
                storedConfiguration
            );

    }

    catch (error) {

        console.error(
            "Invalid migration configuration:",
            error
        );


        alert(
            "Migration configuration is invalid. Please save the configuration again."
        );

        return;

    }

    /* ======================================================
            LOAD SELECTED RESOURCE
    ====================================================== */

    const storedResource =
        sessionStorage.getItem(
            "selected_migration_resource"
        );


    if (!storedResource) {

        alert(
            "Selected resource not found. Please return to the dashboard."
        );

        return;

    }


    let resource;


    try {

        resource =
            JSON.parse(
                storedResource
            );

    }

    catch (error) {

        console.error(
            "Unable to parse selected resource:",
            error
        );


        alert(
            "Selected resource data is invalid."
        );

        return;

    }

    if (executionPath(resource) === "planning") {
        alert("This resource is available for planning and manual review only. No migration execution path is implemented.");
        return;
    }


    /* ======================================================
            GET SOURCE SESSION
    ====================================================== */

    const sourceSessionId =
        sessionStorage.getItem(
            "source_session_id"
        );


    /* ======================================================
            GET TARGET SESSION
    ====================================================== */

    const targetSessionId =
        sessionStorage.getItem(
            "target_session_id"
        );


    /* ======================================================
            VALIDATE SESSIONS
    ====================================================== */

    if (!sourceSessionId) {

        alert(
            "Source cloud session not found. Please connect the source cloud again."
        );

        return;

    }


    if (!targetSessionId) {

        alert(
            "Target cloud session not found. Please connect the target cloud again."
        );

        return;

    }


    /* ======================================================
            GET SOURCE SERVICE
    ====================================================== */

    const sourceService =
        (
            resource.source ||
            resource.source_service ||
            resource.service ||
            ""
        ).toUpperCase();


    /* ======================================================
            S3 MIGRATION
    ====================================================== */

    if (
        sourceService === "S3"
    ) {

        await startS3Migration(
            sourceSessionId,
            targetSessionId,
            resource,
            configuration
        );

        return;

    }


    if (sourceService === "LAMBDA") {
        await startLambdaMigration(sourceSessionId, targetSessionId, resource, configuration);
        return;
    }


    /* ======================================================
            UNSUPPORTED RESOURCE
    ====================================================== */

    alert(
        `${sourceService || "This resource"} migration is not implemented yet.`
    );

}


/* ==========================================================
                START S3 MIGRATION
========================================================== */

async function startLambdaMigration(sourceSessionId, targetSessionId, resource, configuration) {
    const button = document.getElementById("start-migration-btn");
    const status = document.getElementById("configuration-status");
    const functionName = resource.name || resource.resource_name || "";
    if (!functionName || !configuration.resource_group || !configuration.function_app_name) {
        alert("Select a Lambda and provide an existing Azure resource group and Function App.");
        return;
    }
    if (button) setMigrationButtonState(button, "loading");
    if (status) status.textContent = "Validating Lambda and Azure Function App...";
    try {
        const response = await fetch("/api/migration/lambda/start", {
            method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                source_session_id: sourceSessionId, target_session_id: targetSessionId,
                function_name: functionName,
                plan_id: sessionStorage.getItem("persisted_migration_plan_id") || "",
                configuration: {
                    resource_group: configuration.resource_group,
                    function_app_name: configuration.function_app_name,
                    deployment_slot: configuration.deployment_slot || ""
                }
            })
        });
        const result = await parseJSONResponse(response);
        if (!response.ok || !result.success) {
            const reasons = Array.isArray(result.reasons) && result.reasons.length ? ` ${result.reasons.join(" ")}` : "";
            throw new Error((result.message || "Lambda deployment was not started.") + reasons);
        }
        if (result.status === "completed") {
            if (status) status.textContent = "Deployment completed and target validated";
            if (button) setMigrationButtonState(button, "success");
            alert(result.message || "Lambda deployment completed.");
            return;
        }
        if (status) status.textContent = "Deployment is already active; review migration history before retrying.";
        if (button) setMigrationButtonState(button, "error");
        alert(result.message || "Lambda deployment is already active.");
    } catch (error) {
        if (status) status.textContent = "Manual review or deployment failure";
        alert(error.message || "Lambda migration could not be completed.");
        if (button) setMigrationButtonState(button, "error");
    }
}


function configureServiceSpecificFields(resource) {
    const path = executionPath(resource);
    const isLambda = path === "lambda";
    const isS3 = path === "s3";
    document.querySelectorAll("[data-lambda-target]").forEach((field) => {
        field.hidden = !isLambda;
    });
    document.querySelectorAll("[data-s3-target]").forEach((field) => {
        field.hidden = !isS3;
    });

    const targetName = document.getElementById("target-resource-name");
    const region = document.getElementById("target-region");
    const size = document.getElementById("target-size");
    if (targetName) targetName.required = isS3;
    if (region) region.required = isS3;
    if (size) size.required = isS3;

    const resourceGroup = document.getElementById("azure-resource-group");
    const functionApp = document.getElementById("azure-function-app-name");
    if (resourceGroup) resourceGroup.required = isLambda;
    if (functionApp) functionApp.required = isLambda;

    const planningNotice = document.getElementById("planning-only-notice");
    if (planningNotice) planningNotice.hidden = path !== "planning";

    const saveButton = document.querySelector(".save-configuration-btn");
    const startButton = document.getElementById("start-migration-btn");
    if (saveButton) saveButton.hidden = path === "planning";
    if (startButton) {
        startButton.hidden = path === "planning";
        startButton.disabled = path === "planning";
    }
}

async function startS3Migration(
    sourceSessionId,
    targetSessionId,
    resource,
    configuration
) {

    const startMigrationButton =
        document.getElementById(
            "start-migration-btn"
        );


    const statusElement =
        document.getElementById(
            "configuration-status"
        );


    /* ======================================================
            GET BUCKET NAME
    ====================================================== */

    const bucketName =
        resource.bucket_name ||
        resource.name ||
        resource.resource_name ||
        "";


    if (!bucketName) {

        alert(
            "S3 bucket name could not be found."
        );

        return;

    }


    /* ======================================================
            BUTTON LOADING STATE
    ====================================================== */

    setMigrationButtonState(
        startMigrationButton,
        "loading"
    );


    if (statusElement) {

        statusElement.textContent =
            "Migration in Progress";

    }


    try {

        /* ==================================================
                BACKEND REQUEST
        ================================================== */

        const response =
            await fetch(
                "/api/migration/s3/start",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({

                        source_session_id:
                            sourceSessionId,

                        target_session_id:
                            targetSessionId,

                        bucket_name:
                            bucketName,

                        plan_id:
                            sessionStorage.getItem("persisted_migration_plan_id") || "",

                        configuration:
                            {
                                ...configuration,
                                container_name: configuration.target_resource_name || undefined,
                                provision_destination: configuration.provision_destination === true
                            }

                    })
                }
            );


        /* ==================================================
                PARSE RESPONSE
        ================================================== */

        const result =
            await parseJSONResponse(
                response
            );


        /* ==================================================
                SUCCESS
        ================================================== */

        if (
            response.ok &&
            result.success
        ) {

            if (statusElement) {

                statusElement.textContent =
                    "Migration Running";

            }


            setMigrationButtonState(
                startMigrationButton,
                "loading"
            );


            sessionStorage.setItem(
                "migration_result",
                JSON.stringify(
                    result
                )
            );


            if (result.migration_id) {
                monitorS3Migration(result.migration_id, statusElement, startMigrationButton);
            }

            alert(result.message || "S3 migration started.");


            return;

        }


        /* ==================================================
                FAILURE
        ================================================== */

        throw new Error(
            result.message ||
            "S3 migration failed."
        );

    }

    catch (error) {

        console.error(
            "S3 migration error:",
            error
        );


        if (statusElement) {

            statusElement.textContent =
                "Migration Failed";

        }


        setMigrationButtonState(
            startMigrationButton,
            "error"
        );


        alert(
            error.message ||
            "S3 migration failed."
        );

    }

}


/* ==========================================================
                S3 MIGRATION PROGRESS
========================================================== */

async function monitorS3Migration(migrationId, statusElement, button) {
    const poll = async () => {
        try {
            const response = await fetch(`/api/migrations/${encodeURIComponent(migrationId)}`);
            const result = await parseJSONResponse(response);
            const migration = result.migration;
            if (!response.ok || !migration) {
                throw new Error(result.message || "Migration status is unavailable.");
            }
            const processed = migration.processed_files || 0;
            if (statusElement) {
                const batch = migration.current_batch
                    ? ` / batch ${migration.current_batch} of ${migration.total_batches}`
                    : "";
                const retries = migration.retry_attempts
                    ? ` / ${migration.retry_attempts} attempts`
                    : "";
                statusElement.textContent = `${migration.status}: ${processed}/${migration.total_files} objects${batch}${retries}`;
            }
            if (["running", "preparing"].includes(migration.status)) {
                window.setTimeout(poll, 2000);
                return;
            }
            if (migration.status === "completed") {
                setMigrationButtonState(button, "success");
            } else {
                setMigrationButtonState(button, "error");
            }
        } catch (error) {
            console.error("Migration status error:", error);
            if (statusElement) statusElement.textContent = "Migration status unavailable. Refresh to retry.";
            setMigrationButtonState(button, "error");
        }
    };
    await poll();
}


/* ==========================================================
                PARSE JSON RESPONSE
========================================================== */

async function parseJSONResponse(
    response
) {

    const text =
        await response.text();


    if (!text) {

        return {

            success: false,

            message:
                `Server returned an empty response (${response.status}).`

        };

    }


    try {

        return JSON.parse(
            text
        );

    }

    catch (error) {

        console.error(
            "Invalid JSON response:",
            text
        );


        return {

            success: false,

            message:
                `Server returned an invalid response (${response.status}).`

        };

    }

}


/* ==========================================================
                MIGRATION BUTTON STATE
========================================================== */

function setMigrationButtonState(
    button,
    state
) {

    if (!button) {

        return;

    }


    /* ======================================================
            LOADING
    ====================================================== */

    if (
        state === "loading"
    ) {

        button.disabled =
            true;


        button.innerHTML =
            `
            <i data-lucide="loader-circle"></i>
            Migrating...
            `;


        refreshIcons();


        return;

    }


    /* ======================================================
            SUCCESS
    ====================================================== */

    if (
        state === "success"
    ) {

        button.disabled =
            true;


        button.innerHTML =
            `
            <i data-lucide="circle-check"></i>
            Migration Completed
            `;


        refreshIcons();


        return;

    }


    /* ======================================================
            ERROR
    ====================================================== */

    if (
        state === "error"
    ) {

        button.disabled =
            false;


        button.innerHTML =
            `
            <i data-lucide="rocket"></i>
            Start Migration
            `;


        refreshIcons();

    }

}


/* ==========================================================
                PAGE ERROR
========================================================== */

function showPageError(
    message
) {

    const resourceName =
        document.getElementById(
            "selected-resource-name"
        );


    if (resourceName) {

        resourceName.textContent =
            "Unable to Load Resource";

    }


    const sourceService =
        document.getElementById(
            "selected-source-service"
        );


    if (sourceService) {

        sourceService.textContent =
            "Error";

    }


    const targetService =
        document.getElementById(
            "selected-target-service"
        );


    if (targetService) {

        targetService.textContent =
            message;

    }


    console.error(
        message
    );

}


/* ==========================================================
                REFRESH LUCIDE ICONS
========================================================== */

function refreshIcons() {

    if (
        window.lucide &&
        typeof window.lucide.createIcons ===
            "function"
    ) {

        window.lucide.createIcons();

    }

}


/* ==========================================================
                ESCAPE HTML
========================================================== */

function escapeHTML(
    value
) {

    const div =
        document.createElement(
            "div"
        );


    div.textContent =
        value ??
        "";


    return div.innerHTML;

}
