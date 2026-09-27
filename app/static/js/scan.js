/* ==========================================================
                AI CLOUD MIGRATION
                    RESOURCE SCANNER
========================================================== */


document.addEventListener("DOMContentLoaded", () => {


    /* ======================================================
                        ELEMENTS
    ====================================================== */

    const progressFill =
        document.getElementById("progress-fill");

    const progressText =
        document.getElementById("progress-text");

    const resourceCount =
        document.getElementById("resource-count");

    const scanStatus =
        document.getElementById("scan-status");

    const scanDescription =
        document.getElementById("scan-description");

    const currentActivity =
        document.getElementById("current-activity");


    /* ======================================================
                    VALIDATE PAGE DATA
    ====================================================== */

    if (!SCAN_SOURCE || !SCAN_TARGET) {

        console.error(
            "Missing source or target cloud."
        );

        scanStatus.textContent =
            "Migration Information Missing";

        scanDescription.textContent =
            "Please select a migration path again.";

        currentActivity.textContent =
            "Scan could not start.";

        return;

    }


    /* ======================================================
                    UPDATE PROGRESS
    ====================================================== */

    function updateProgress(
        percentage,
        resources,
        status,
        description,
        activity
    ) {

        progress = percentage;

        progressFill.style.width =
            `${percentage}%`;

        progressText.textContent =
            `${percentage}%`;

        resourceCount.textContent =
            `${resources} resources discovered`;

        scanStatus.textContent =
            status;

        scanDescription.textContent =
            description;

        currentActivity.textContent =
            activity;

    }


    /* ======================================================
                    START VISUAL PROGRESS
    ====================================================== */

    let progress = 0;

    let discoveredResources = 0;


    const scanSteps = [

        {
            progress: 10,
            status: "Connecting to Cloud...",
            description:
                "Establishing a secure connection with your cloud environment.",
            activity:
                "Authenticating cloud credentials..."
        },

        {
            progress: 25,
            status: "Discovering Compute Resources...",
            description:
                "Scanning virtual machines, instances and server workloads.",
            activity:
                "Checking compute infrastructure..."
        },

        {
            progress: 45,
            status: "Scanning Storage Resources...",
            description:
                "Discovering storage buckets, blobs and persistent resources.",
            activity:
                "Analyzing storage configuration..."
        },

        {
            progress: 65,
            status: "Scanning Database Resources...",
            description:
                "Discovering supported database and data services.",
            activity:
                "Checking database infrastructure..."
        },

        {
            progress: 80,
            status: "Analyzing Network Resources...",
            description:
                "Reviewing supported networking configuration.",
            activity:
                "Analyzing network resources..."
        },

        {
            progress: 95,
            status: "Preparing Migration Analysis...",
            description:
                "Organizing discovered resources for migration compatibility.",
            activity:
                "Preparing resource inventory..."
        }

    ];


    /* ======================================================
                    SIMULATE VISUAL SCAN
    ====================================================== */

    function runVisualProgress() {

        updateProgress(
            5,
            0,
            "Preparing Resource Scan...",
            "Waiting for the cloud scanner to report actual progress.",
            "Validating the migration session..."
        );

    }


    /* ======================================================
                    START REAL SCAN
    ====================================================== */

    async function startScan() {

        const sourceSessionId =
            sessionStorage.getItem("source_session_id");

        const targetSessionId =
            sessionStorage.getItem("target_session_id");

        if (!sourceSessionId) {
            updateProgress(
                progress,
                discoveredResources,
                "Scan Failed",
                "Source cloud session is missing. Please reconnect the source cloud.",
                "Unable to begin resource discovery."
            );
            return;
        }

        if (!["aws", "azure"].includes(SCAN_SOURCE)) {
            updateProgress(
                progress,
                discoveredResources,
                "Scan Unavailable",
                "Scanning is not implemented for this source cloud.",
                "Choose AWS or Azure to continue."
            );
            return;
        }

        const endpoint =
            SCAN_SOURCE === "azure"
                ? "/api/azure/scan"
                : "/api/aws/scan";

        const requestBody =
            SCAN_SOURCE === "azure"
                ? { session_id: sourceSessionId }
                : { session_id: sourceSessionId, target: SCAN_TARGET };

        try {

            const response = await fetch(

                endpoint,

                {

                    method: "POST",

                    headers: {

                        "Content-Type":
                            "application/json"

                    },

                    body: JSON.stringify(requestBody)

                }

            );


            const result =
                await response.json();


            if (!response.ok || !result.success) {

                throw new Error(

                    result.message ||
                    "Cloud scan failed."

                );

            }


            /* ==============================================
                    SCAN SUCCESS
            =============================================== */

            const resources =
                result.resources ||
                [
                    ...(result.virtual_machines || []),
                    ...(result.storage_accounts || []),
                    ...(result.sql_databases || [])
                ];


            updateProgress(

                100,

                resources.length,

                "Scan Complete!",

                "Your cloud resources have been successfully discovered.",

                `${resources.length} resources ready for analysis.`

            );


            /* ==============================================
                    SAVE SCAN RESULT
            =============================================== */

            sessionStorage.setItem(

                "migration_resources",

                JSON.stringify(resources)

            );


            sessionStorage.setItem(

                "scan_source",

                SCAN_SOURCE

            );


            sessionStorage.setItem(

                "scan_target",

                SCAN_TARGET

            );


            /* ==============================================
                    REDIRECT
            =============================================== */

            setTimeout(() => {

                window.location.href =

                    `/migration/dashboard?source=${encodeURIComponent(SCAN_SOURCE)}` +
                    `&target=${encodeURIComponent(SCAN_TARGET)}` +
                    `&source_session_id=${encodeURIComponent(sourceSessionId)}` +
                    `&target_session_id=${encodeURIComponent(targetSessionId || "")}`;

            }, 1500);


        }


        catch (error) {

            console.error(
                "Scan Error:",
                error
            );


            updateProgress(

                progress,

                discoveredResources,

                "Scan Failed",

                error.message,

                "Unable to complete cloud resource discovery."

            );

        }

    }


    /* ======================================================
                    INITIALIZE SCAN
    ====================================================== */

    runVisualProgress();


    setTimeout(() => {

        startScan();

    }, 700);


});
