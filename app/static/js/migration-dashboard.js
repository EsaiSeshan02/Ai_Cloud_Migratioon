/* ==========================================================
                AI CLOUD MIGRATION
                MIGRATION DASHBOARD
========================================================== */

document.addEventListener("DOMContentLoaded", () => {

    initializeDashboard();

});


/* ==========================================================
                INITIALIZE DASHBOARD
========================================================== */

function initializeDashboard() {

    const startScanButton =
        document.getElementById(
            "start-scan-btn"
        );

    const savePlanButton =
        document.getElementById(
            "save-plan-btn"
        );


    if (!startScanButton) {

        console.error(
            "Start scan button not found."
        );

        return;

    }


    /* ==============================================
            LOAD PREVIOUS SCAN DATA
    ============================================== */

    loadStoredScanData();


    /* ==============================================
            START NEW SCAN
    ============================================== */

    startScanButton.addEventListener(
        "click",
        async () => {

            await startResourceScan(
                startScanButton
            );

        }
    );

    if (savePlanButton) {
        savePlanButton.addEventListener("click", async () => {
            const planId = sessionStorage.getItem("persisted_migration_plan_id");
            if (planId) {
                await openPersistedMigrationPlan(planId, savePlanButton);
            } else {
                await savePersistedMigrationPlan(savePlanButton);
            }
        });
    }

}


/* ==========================================================
                LOAD STORED SCAN DATA
========================================================== */

function loadStoredScanData() {

    const storedPlan =
        sessionStorage.getItem(
            "migration_plan"
        );


    if (!storedPlan) {

        console.log(
            "No previous migration plan found."
        );

        return;

    }


    try {

        const migrationPlan =
            JSON.parse(storedPlan);


        if (
            migrationPlan &&
            migrationPlan.resources
        ) {

            displayScanResults(
                migrationPlan.resources
            );

            updateSummary(migrationPlan.resources);
            if (migrationPlan.plan_id) {
                updatePersistedPlanStatus(migrationPlan.status, migrationPlan.plan_id);
                const savePlanButton = document.getElementById("save-plan-btn");
                if (savePlanButton) {
                    savePlanButton.disabled = false;
                    savePlanButton.textContent = "View Saved Plan";
                }
            }

        }

    }

    catch (error) {

        console.error(
            "Unable to load stored migration plan:",
            error
        );

    }

}


/* ==========================================================
                START RESOURCE SCAN
========================================================== */

async function startResourceScan(
    startButton
) {

    /* ==============================================
            GET CLOUD INFORMATION
    ============================================== */

    const sourceCloud =
        startButton.dataset.source;

    const targetCloud =
        startButton.dataset.target;

    const sourceSessionId =
    startButton.dataset.sourceSession ||
    sessionStorage.getItem(
        "source_session_id"
    );

    const targetSessionId =
        startButton.dataset.targetSession ||
        sessionStorage.getItem(
            "target_session_id"
    );


    /* ==============================================
         VALIDATE SOURCE SESSION
    ============================================== */

    if (!sourceSessionId) {

        updateScanStatus(
            "Source cloud session not found. Please connect the source cloud again.",
            0,
            "failed"
        );

        console.error(
            "Missing source session ID."
        );

        return;

    }


    /* ==============================================
            BUTTON LOADING STATE
    ============================================== */

    const originalButtonHTML =
        startButton.innerHTML;


    startButton.disabled = true;


    startButton.innerHTML = `
        <i data-lucide="loader-circle"></i>
        Scanning Resources...
    `;


    if (window.lucide) {

        lucide.createIcons();

    }


    /* ==============================================
            START PROGRESS
    ============================================== */

    updateScanStatus(
        "Connecting to cloud...",
        10,
        "scanning"
    );


    try {

        /* ==========================================
                PROGRESS SIMULATION
        ========================================== */

        await wait(400);

        updateScanStatus(
            "Discovering cloud resources...",
            35,
            "scanning"
        );


        await wait(400);


        updateScanStatus(
            "Scanning supported services...",
            60,
            "scanning"
        );


        /* ==========================================
                CALL BACKEND
        ========================================== */

        const scanRequest = getSourceScanRequest(sourceCloud, sourceSessionId, targetCloud);
        const response =
            await fetch(
                scanRequest.endpoint,
                {

                    method: "POST",

                    headers: {

                        "Content-Type":
                            "application/json"

                    },

                    body: JSON.stringify(scanRequest.body)

                }
            );


        /* ==========================================
                PARSE RESPONSE
        ========================================== */

        const result =
            await response.json();


        /* ==========================================
                CHECK SUCCESS
        ========================================== */

        if (
            response.ok &&
            result.success
        ) {

            updateScanStatus(
                "Processing migration recommendations...",
                80,
                "scanning"
            );


            await wait(400);


            /* ======================================
                    SAVE DATA
            ====================================== */

            sessionStorage.setItem(

                "migration_resources",

                JSON.stringify(
                    result.resources || {}
                )

            );


            sessionStorage.setItem(

                "migration_recommendations",

                JSON.stringify(
                    result.recommendations || []
                )

            );


            sessionStorage.setItem(

                "migration_plan",

                JSON.stringify(
                    result.migration_plan || {}
                )

            );
            sessionStorage.removeItem("persisted_migration_plan_id");
            updatePersistedPlanStatus("Not saved");


            /* ======================================
                    GET RESOURCES
            ====================================== */

            const resources =
                result.migration_plan?.resources || [];


            /* ======================================
                    DISPLAY RESULTS
            ====================================== */

            displayScanResults(
                resources
            );

            const savePlanButton = document.getElementById("save-plan-btn");
            if (savePlanButton) {
                savePlanButton.disabled = false;
            }


            /* ======================================
                    COMPLETE PROGRESS
            ====================================== */

            updateScanStatus(
                "Scan completed successfully",
                100,
                "success"
            );


            /* ======================================
                    UPDATE BUTTON
            ====================================== */

            startButton.innerHTML = `
                <i data-lucide="circle-check"></i>
                Scan Completed
            `;


            startButton.classList.add(
                "scan-completed"
            );


            console.log(
                "Resource scan completed successfully."
            );


            if (window.lucide) {

                lucide.createIcons();

            }

        }


        /* ==========================================
                SCAN FAILED
        ========================================== */

        else {

            updateScanStatus(
                result.message ||
                "Resource scan failed.",
                0,
                "failed"
            );


            resetScanButton(
                startButton,
                originalButtonHTML
            );

        }

    }


    /* ==============================================
            NETWORK / SERVER ERROR
    ============================================== */

    catch (error) {

        console.error(
            "Resource scan error:",
            error
        );


        updateScanStatus(
            "Unable to contact the migration server.",
            0,
            "failed"
        );


        resetScanButton(
            startButton,
            originalButtonHTML
        );

    }

}


function getSourceScanRequest(sourceCloud, sourceSessionId, targetCloud) {
    return {
        endpoint: "/api/aws/scan",
        body: {session_id: sourceSessionId, target: "azure"}
    };
}


/* ==========================================================
                PERSISTED MIGRATION PLAN
========================================================== */

async function savePersistedMigrationPlan(button) {
    const cloudContext = getDashboardCloudContext();
    const sourceCloud = cloudContext.sourceCloud;
    const targetCloud = cloudContext.targetCloud;
    const sourceSessionId = cloudContext.sourceSessionId;
    const targetSessionId = cloudContext.targetSessionId;
    if (!sourceSessionId || !targetSessionId) {
        updatePersistedPlanStatus("Cloud sessions are unavailable.");
        return;
    }
    const originalLabel = button.textContent;
    button.disabled = true;
    button.textContent = "Saving Plan...";
    try {
        const response = await fetch("/api/migration-plans", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                source_cloud: sourceCloud,
                target_cloud: targetCloud,
                source_session_id: sourceSessionId,
                target_session_id: targetSessionId
            })
        });
        const result = await response.json();
        if (!response.ok || !result.success || !result.plan) {
            throw new Error(result.message || "Migration plan could not be saved.");
        }
        sessionStorage.setItem("migration_plan", JSON.stringify(result.plan));
        sessionStorage.setItem("persisted_migration_plan_id", result.plan.plan_id);
        displayScanResults(result.plan.resources || []);
        updateSummary(result.plan.resources || []);
        updatePersistedPlanStatus(result.plan.status, result.plan.plan_id);
        button.textContent = "View Saved Plan";
        button.disabled = false;
    } catch (error) {
        console.error("Migration plan save error:", error);
        updatePersistedPlanStatus("Plan save failed");
        button.textContent = originalLabel;
        button.disabled = false;
    }
}


function getDashboardCloudContext() {
    const scanButton = document.getElementById("start-scan-btn");
    return {
        sourceCloud: document.getElementById("source-cloud")?.value || scanButton?.dataset.source || "aws",
        targetCloud: document.getElementById("target-cloud")?.value || scanButton?.dataset.target || "azure",
        sourceSessionId: document.getElementById("source-session-id")?.value || scanButton?.dataset.sourceSession || sessionStorage.getItem("source_session_id"),
        targetSessionId: document.getElementById("target-session-id")?.value || scanButton?.dataset.targetSession || sessionStorage.getItem("target_session_id"),
    };
}


function updatePersistedPlanStatus(status, planId = "") {
    const statusElement = document.getElementById("persisted-plan-status");
    const idElement = document.getElementById("persisted-plan-id");
    if (statusElement) statusElement.textContent = status || "Not saved";
    if (idElement) idElement.textContent = planId ? `Plan ID: ${planId}` : "";
}


async function openPersistedMigrationPlan(planId, button) {
    try {
        const response = await fetch(`/api/migration-plans/${encodeURIComponent(planId)}`);
        const result = await response.json();
        if (!response.ok || !result.success || !result.plan) {
            throw new Error(result.message || "Saved migration plan is unavailable.");
        }
        sessionStorage.setItem("migration_plan", JSON.stringify(result.plan));
        displayScanResults(result.plan.resources || []);
        updateSummary(result.plan.resources || []);
        updatePersistedPlanStatus(result.plan.status, result.plan.plan_id);
        button.textContent = "View Saved Plan";
    } catch (error) {
        console.error("Migration plan retrieval error:", error);
        updatePersistedPlanStatus("Saved plan unavailable");
    }
}


/* ==========================================================
                DISPLAY SCAN RESULTS
========================================================== */

function displayScanResults(
    resources
) {

    const emptyState =
        document.getElementById(
            "resources-empty-state"
        );


    const resourcesGrid =
        document.getElementById(
            "resources-grid"
        );


    const scanState =
        document.getElementById(
            "resource-scan-state"
        );


    /* ==============================================
            VALIDATE
    ============================================== */

    if (!resourcesGrid) {

        console.error(
            "Resources grid not found."
        );

        return;

    }


    /* ==============================================
            UPDATE COUNTS
    ============================================== */

    updateSummary(
        resources
    );


    /* ==============================================
            NO RESOURCES
    ============================================== */

    if (
        !resources ||
        resources.length === 0
    ) {

        if (scanState) {

            scanState.textContent =
                "No resources found";

        }


        resourcesGrid.innerHTML = "";


        resourcesGrid.classList.add(
            "hidden"
        );


        if (emptyState) {

            emptyState.classList.remove(
                "hidden"
            );

        }


        return;

    }


    /* ==============================================
            SHOW RESULTS
    ============================================== */

    if (emptyState) {

        emptyState.classList.add(
            "hidden"
        );

    }


    resourcesGrid.classList.remove(
        "hidden"
    );


    resourcesGrid.innerHTML = "";


    if (scanState) {

        scanState.textContent =
            `${resources.length} Resources Found`;

    }


    /* ==============================================
            CREATE RESOURCE CARDS
    ============================================== */

    resources.forEach(
        resource => {

            const resourceCard =
                document.createElement(
                    "div"
                );


            resourceCard.className =
                "resource-card";

            /* ==========================================
            MAKE RESOURCE CARD CLICKABLE
            ========================================== */

            resourceCard.style.cursor = "pointer";


            resourceCard.addEventListener(
                "click",
                () => {
                    
                    /* ======================================
                    STORE SELECTED RESOURCE
                    ====================================== */

                    sessionStorage.setItem(
                        "selected_migration_resource",
                        JSON.stringify(
                            resource
                        )
                    );


                    /* ======================================
                    OPEN CONFIGURATION PAGE
                    ====================================== */

                    const params = new URLSearchParams(
                        window.location.search
                    );

                    const sourceCloud =
                        params.get("source") || "aws";

                    const targetCloud =
                        params.get("target") || "azure";

                    const sourceSessionId =
                        params.get("source_session_id") || "";

                    const targetSessionId =
                        params.get("target_session_id") || "";

                    const resourceType =
                        resource.service ||
                        resource.source_service ||
                        "";

                    const resourceName =
                        resource.name ||
                        resource.resource_name ||
                        resource.bucket_name ||
                        "";

                    window.location.href =
                        `/migration/configure?source=${encodeURIComponent(sourceCloud)}` +
                        `&target=${encodeURIComponent(targetCloud)}` +
                        `&source_session_id=${encodeURIComponent(sourceSessionId)}` +
                        `&target_session_id=${encodeURIComponent(targetSessionId)}` +
                        `&resource_type=${encodeURIComponent(resourceType)}` +
                        `&resource_name=${encodeURIComponent(resourceName)}`;

                }
            );


            /* ==========================================
                    DETERMINE STATUS
            ========================================== */

            const status =
                resource.status ||
                "Manual review required";


            const isReady =
                resource.execution_classification ===
                "supported_execution";


            const statusClass =
                isReady
                    ? "ready"
                    : "review";

            const capability = String(
                resource.execution_classification || "manual_review"
            ).replace(/_/g, " ");

            const findings = Array.isArray(resource.preflight_findings)
                ? resource.preflight_findings.slice(0, 2)
                : [];

            const dependencies = Array.isArray(resource.dependencies)
                ? resource.dependencies
                : [];


            /* ==========================================
                    CARD CONTENT
            ========================================== */

            resourceCard.innerHTML = `

                <div class="resource-card-header">

                    <div class="resource-service-icon">

                        <i data-lucide="server"></i>

                    </div>


                    <span
                        class="resource-status ${statusClass}"
                    >

                        ${escapeHTML(status)}

                    </span>

                </div>


                <h3>

                    ${escapeHTML(
                        resource.name ||
                        "Unnamed Resource"
                    )}

                </h3>


                <div class="resource-details">


                    <div class="resource-detail">

                        <span>

                            Source

                        </span>


                        <strong>

                            ${escapeHTML(
                                resource.source ||
                                "Unknown"
                            )}

                        </strong>

                    </div>

                    <div class="resource-detail">

                        <span>

                            Capability

                        </span>


                        <strong>

                            ${escapeHTML(capability)}

                        </strong>

                    </div>

                    ${resource.risk_level ? `
                    <div class="resource-detail">
                        <span>Risk</span>
                        <strong>${escapeHTML(resource.risk_level)}</strong>
                    </div>` : ""}


                    <div class="resource-detail">

                        <span>

                            Target

                        </span>


                        <strong>

                            ${escapeHTML(
                                resource.target ||
                                "Manual Review"
                            )}

                        </strong>

                    </div>


                    <div class="resource-detail">

                        <span>

                            Compatibility

                        </span>


                        <strong>

                            ${resource.compatibility || 0}%

                        </strong>

                    </div>


                    <div class="resource-detail">

                        <span>

                            Configuration

                        </span>


                        <strong>

                            ${escapeHTML(
                                resource.recommended_size ||
                                "N/A"
                            )}

                        </strong>

                    </div>


                </div>

                ${Array.isArray(resource.manual_review_reasons) && resource.manual_review_reasons.length ? `
                <div class="resource-detail">
                    <span>Review Required</span>
                    <strong>${escapeHTML(resource.manual_review_reasons.join(" "))}</strong>
                </div>` : ""}

                ${dependencies.length ? `
                <div class="resource-detail">
                    <span>Dependencies</span>
                    <strong>${escapeHTML(dependencies.join(" / "))}</strong>
                </div>` : ""}

                ${findings.length ? `
                <div class="resource-detail">
                    <span>Preflight</span>
                    <strong>${escapeHTML(findings.map(finding => finding.message || finding.code || "Assessment finding").join(" "))}</strong>
                </div>` : ""}

                <button class="configure-migration-btn">
                    <span>

                        ${isReady ? "Configure S3 Migration" : "Review Assessment"}

                    </span>

                    <i data-lucide="arrow-right"></i>

                </button>

            `;
            
            resourceCard.addEventListener(
                "click",
                () => {

                    /* ==========================================
                            STORE SELECTED RESOURCE
                    ========================================== */

                    sessionStorage.setItem(
                        "selected_migration_resource",
                        JSON.stringify(resource)

                    );


                    /* ==========================================
                        GO TO CONFIGURE PAGE
                    ========================================== */

                    const sourceCloud =
                        document.getElementById("source-cloud").value;

                    const targetCloud =
                        document.getElementById("target-cloud").value;

                    const sourceSessionId =
                        document.getElementById("source-session-id").value;

                    const targetSessionId =
                        document.getElementById("target-session-id").value;

                    window.location.href =
                        `/migration/configure?source=${encodeURIComponent(sourceCloud)}` +
                        `&target=${encodeURIComponent(targetCloud)}` +
                        `&source_session_id=${encodeURIComponent(sourceSessionId)}` +
                        `&target_session_id=${encodeURIComponent(targetSessionId)}`;

                }
            );


            resourcesGrid.appendChild(
                resourceCard
            );

        }
    );


    /* ==============================================
            REFRESH LUCIDE ICONS
    ============================================== */

    if (window.lucide) {

        lucide.createIcons();

    }

}


/* ==========================================================
                UPDATE SUMMARY
========================================================== */

function updateSummary(
    resources
) {

    const resourceCount =
        document.getElementById(
            "resource-count"
        );


    const readyCount =
        document.getElementById(
            "ready-count"
        );


    const reviewCount =
        document.getElementById(
            "review-count"
        );


    const total =
        resources.length;


    const ready =
        resources.filter(
            resource => {

                return resource.execution_classification ===
                    "supported_execution";

            }
        ).length;


    const review =
        resources.filter(
            resource => {

                return resource.execution_classification !==
                    "supported_execution";

            }
        ).length;


    if (resourceCount) {

        resourceCount.textContent =
            total;

    }


    if (readyCount) {

        readyCount.textContent =
            ready;

    }


    if (reviewCount) {

        reviewCount.textContent =
            review;

    }

}


/* ==========================================================
                UPDATE SCAN PROGRESS
========================================================== */

function updateScanStatus(
    message,
    percentage,
    state
) {

    const statusElement =
        document.getElementById(
            "scan-status"
        );


    const percentageElement =
        document.getElementById(
            "scan-percentage"
        );


    const progressFill =
        document.getElementById(
            "scan-progress-fill"
        );


    const scanState =
        document.getElementById(
            "resource-scan-state"
        );


    if (statusElement) {

        statusElement.textContent =
            message;

    }


    if (percentageElement) {

        percentageElement.textContent =
            `${percentage}%`;

    }


    if (progressFill) {

        progressFill.style.width =
            `${percentage}%`;

    }


    if (scanState) {

        if (state === "success") {

            scanState.textContent =
                "Scan completed";

        }

        else if (state === "failed") {

            scanState.textContent =
                "Scan failed";

        }

        else if (state === "scanning") {

            scanState.textContent =
                "Scanning...";

        }

    }

}


/* ==========================================================
                RESET SCAN BUTTON
========================================================== */

function resetScanButton(
    startButton,
    originalButtonHTML
) {

    startButton.disabled =
        false;


    startButton.innerHTML =
        originalButtonHTML;


    if (window.lucide) {

        lucide.createIcons();

    }

}


/* ==========================================================
                WAIT HELPER
========================================================== */

function wait(
    milliseconds
) {

    return new Promise(

        resolve => {

            setTimeout(
                resolve,
                milliseconds
            );

        }

    );

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
        value;


    return div.innerHTML;

}
