document.addEventListener(
    "DOMContentLoaded",
    () => {

        // ==================================================
        // ELEMENTS
        // ==================================================

        const sourceCloudInput =
            document.getElementById(
                "source-cloud"
            );

        const targetCloudInput =
            document.getElementById(
                "target-cloud"
            );

        const sourceSessionInput =
            document.getElementById(
                "source-session-id"
            );

        const validateButton =
            document.getElementById(
                "validate-clouds-btn"
            );

        const targetStatus =
            document.getElementById(
                "target-connection-status"
            );

        const validationResults =
            document.getElementById(
                "validation-results"
            );


        // ==================================================
        // CLOUD DATA
        // ==================================================

        const sourceCloud =
            sourceCloudInput?.value
                ?.trim()
                .toLowerCase();

        const targetCloud =
            targetCloudInput?.value
                ?.trim()
                .toLowerCase();

        const sourceSessionId =
            sourceSessionInput?.value
                ?.trim();


        // ==================================================
        // INITIALIZE ICONS
        // ==================================================

        refreshIcons();


        // ==================================================
        // VALIDATE PAGE DATA
        // ==================================================

        if (
            !sourceCloud ||
            !targetCloud ||
            !sourceSessionId
        ) {

            console.error(
                "Missing source/target cloud or source session."
            );

            updateTargetStatus(
                "error",
                "Migration session information is missing."
            );

            return;
        }


        // ==================================================
        // BUTTON CLICK
        // ==================================================

        validateButton?.addEventListener(
            "click",
            async () => {

                setButtonLoading(true);


                try {

                    let result;


                    // ======================================
                    // TARGET = AZURE
                    // ======================================

                    if (
                        targetCloud === "azure"
                    ) {

                        result =
                            await validateAzureTarget();

                    }


                    // ======================================
                    // TARGET = AWS
                    // ======================================

                    else if (
                        targetCloud === "aws"
                    ) {

                        result =
                            await validateAwsTarget();

                    }


                    // ======================================
                    // TARGET = GCP
                    // ======================================

                    else if (
                        targetCloud === "gcp"
                    ) {

                        result =
                            await validateGcpTarget();

                    }


                    // ======================================
                    // INVALID TARGET
                    // ======================================

                    else {

                        result = {

                            success: false,

                            message:
                                "Unsupported target cloud."

                        };

                    }


                    // ======================================
                    // VALIDATION FAILED
                    // ======================================

                    if (
                        !result ||
                        !result.success
                    ) {

                        const message =
                            result?.message ||
                            "Target cloud validation failed.";


                        updateTargetStatus(
                            "error",
                            message
                        );


                        updateValidationResult(
                            "error",
                            message
                        );


                        setButtonLoading(false);

                        return;
                    }


                    // ======================================
                    // TARGET VALIDATED
                    // ======================================

                    updateTargetStatus(
                        "success",
                        `${getCloudName(
                            targetCloud
                        )} connection verified`
                    );


                    updateValidationSuccess(
                        result
                    );


                    // ======================================
                    // GET TARGET SESSION
                    // ======================================

                    const targetSessionId =
                        result.session_id ||
                        result.target_session_id ||
                        "";


                    if (!targetSessionId) {

                        throw new Error(
                            "Target cloud connected, but no target session was returned."
                        );

                    }


                    // ======================================
                    // SAVE SESSION LOCALLY
                    // ======================================

                    sessionStorage.setItem(
                        "migration_source",
                        sourceCloud
                    );


                    sessionStorage.setItem(
                        "migration_target",
                        targetCloud
                    );


                    sessionStorage.setItem(
                        "source_session_id",
                        sourceSessionId
                    );


                    sessionStorage.setItem(
                        "target_session_id",
                        targetSessionId
                    );


                    // ======================================
                    // REDIRECT
                    // ======================================

                    setTimeout(
                        () => {

                            redirectToDashboard(
                                targetSessionId
                            );

                        },
                        1000
                    );

                }

                catch (error) {

                    console.error(
                        "TARGET VALIDATION ERROR:",
                        error
                    );


                    updateTargetStatus(
                        "error",
                        error.message ||
                        "Unable to validate target cloud."
                    );


                    updateValidationResult(
                        "error",
                        error.message ||
                        "Unable to validate target cloud."
                    );


                    setButtonLoading(false);

                }

            }
        );


        // ==================================================
        // AZURE TARGET VALIDATION
        // ==================================================

        async function validateAzureTarget() {

            const subscriptionId =
                document.getElementById(
                    "azure-subscription-id"
                )?.value
                    ?.trim();


            const tenantId =
                document.getElementById(
                    "azure-tenant-id"
                )?.value
                    ?.trim();


            const clientId =
                document.getElementById(
                    "azure-client-id"
                )?.value
                    ?.trim();


            const clientSecret =
                document.getElementById(
                    "azure-client-secret"
                )?.value
                    ?.trim();


            // ----------------------------------------------
            // FRONTEND VALIDATION
            // ----------------------------------------------

            if (
                !subscriptionId ||
                !tenantId ||
                !clientId ||
                !clientSecret
            ) {

                return {

                    success: false,

                    message:
                        "Please fill all Azure credential fields."

                };

            }


            // ----------------------------------------------
            // API REQUEST
            // ----------------------------------------------

            const response =
                await fetch("/api/migration/target/validate", 
                    {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json"
                        },
                        body: JSON.stringify
                        ({
                            source: sourceCloud,
                            target: targetCloud,
                            source_session_id: sourceSessionId,

                            tenant_id: tenantId,
                            client_id: clientId,
                            client_secret: clientSecret,
                            subscription_id: subscriptionId
                        })
                    })


            const result =
                await parseJsonResponse(
                    response
                );


            if (!response.ok) {

                return {

                    success: false,

                    message:
                        result.message ||
                        "Azure validation failed."

                };

            }


            return result;

        }


        // ==================================================
        // AWS TARGET VALIDATION
        // ==================================================

        async function validateAwsTarget() {

            const accessKey =
                document.getElementById(
                    "target-aws-access-key"
                )?.value
                    ?.trim();


            const secretKey =
                document.getElementById(
                    "target-aws-secret-key"
                )?.value
                    ?.trim();


            const region =
                document.getElementById(
                    "target-aws-region"
                )?.value
                    ?.trim();


            // ----------------------------------------------
            // FRONTEND VALIDATION
            // ----------------------------------------------

            if (
                !accessKey ||
                !secretKey ||
                !region
            ) {

                return {

                    success: false,

                    message:
                        "Please fill all AWS credential fields."

                };

            }


            // ----------------------------------------------
            // API REQUEST
            // ----------------------------------------------

            const response =
                await fetch(
                    "/api/aws/connect",
                    {

                        method: "POST",

                        headers: {

                            "Content-Type":
                                "application/json"

                        },

                        body: JSON.stringify({

                            access_key:
                                accessKey,

                            secret_key:
                                secretKey,

                            region:
                                region,

                            target:
                                targetCloud

                        })

                    }
                );


            const result =
                await parseJsonResponse(
                    response
                );


            if (!response.ok) {

                return {

                    success: false,

                    message:
                        result.message ||
                        "AWS validation failed."

                };

            }


            return result;

        }


        // ==================================================
        // GCP TARGET VALIDATION
        // ==================================================

        async function validateGcpTarget() {

            const projectId =
                document.getElementById(
                    "gcp-project-id"
                )?.value
                    ?.trim();


            const serviceAccountInput =
                document.getElementById(
                    "gcp-service-account"
                );


            // ----------------------------------------------
            // PROJECT ID
            // ----------------------------------------------

            if (!projectId) {

                return {

                    success: false,

                    message:
                        "Google Cloud Project ID is required."

                };

            }


            // ----------------------------------------------
            // SERVICE ACCOUNT
            // ----------------------------------------------

            if (
                !serviceAccountInput ||
                !serviceAccountInput.files ||
                serviceAccountInput.files.length === 0
            ) {

                return {

                    success: false,

                    message:
                        "Please select a Google Cloud service account JSON file."

                };

            }


            /*
             * GCP backend is not implemented yet.
             *
             * We deliberately do NOT send this request
             * to a non-existent endpoint.
             */

            return {

                success: false,

                message:
                    "Google Cloud target validation is not implemented yet."

            };

        }


        // ==================================================
        // UPDATE TARGET STATUS
        // ==================================================

        function updateTargetStatus(
            status,
            message
        ) {

            if (!targetStatus) {

                return;

            }


            targetStatus.classList.remove(
                "success",
                "error",
                "pending"
            );


            targetStatus.classList.add(
                status
            );


            targetStatus.innerHTML = `

                <span
                    class="status-dot"
                ></span>

                ${escapeHtml(
                    message
                )}

            `;

        }


        // ==================================================
        // UPDATE VALIDATION ERROR
        // ==================================================

        function updateValidationResult(
            status,
            message
        ) {

            if (!validationResults) {

                return;

            }


            const icon =
                status === "success"
                    ? "circle-check"
                    : "circle-x";


            validationResults.innerHTML = `

                <div
                    class="validation-item success"
                >

                    <i
                        data-lucide="circle-check"
                    ></i>

                    <span>

                        ${getCloudName(
                            sourceCloud
                        )}

                        source credentials verified

                    </span>

                </div>


                <div
                    class="validation-item ${status}"
                >

                    <i
                        data-lucide="${icon}"
                    ></i>

                    <span>

                        ${escapeHtml(
                            message
                        )}

                    </span>

                </div>


                <div
                    class="validation-item pending"
                >

                    <i
                        data-lucide="clock-3"
                    ></i>

                    <span>

                        Resource discovery will begin
                        after target validation

                    </span>

                </div>

            `;


            refreshIcons();

        }


        // ==================================================
        // UPDATE VALIDATION SUCCESS
        // ==================================================

        function updateValidationSuccess(
            result
        ) {

            if (!validationResults) {

                return;

            }


            validationResults.innerHTML = `

                <div
                    class="validation-item success"
                >

                    <i
                        data-lucide="circle-check"
                    ></i>

                    <span>

                        ${getCloudName(
                            sourceCloud
                        )}

                        source credentials verified

                    </span>

                </div>


                <div
                    class="validation-item success"
                >

                    <i
                        data-lucide="circle-check"
                    ></i>

                    <span>

                        ${getCloudName(
                            targetCloud
                        )}

                        target credentials verified

                    </span>

                </div>


                <div
                    class="validation-item success"
                >

                    <i
                        data-lucide="circle-check"
                    ></i>

                    <span>

                        Both cloud environments
                        are ready for migration

                    </span>

                </div>

            `;


            refreshIcons();

        }


        // ==================================================
        // BUTTON LOADING
        // ==================================================

        function setButtonLoading(
            loading
        ) {

            if (!validateButton) {

                return;

            }


            if (loading) {

                validateButton.disabled =
                    true;


                validateButton.classList.add(
                    "loading"
                );


                validateButton.innerHTML = `

                    <i
                        data-lucide="loader-circle"
                    ></i>

                    Validating Cloud Credentials...

                `;

            }

            else {

                validateButton.disabled =
                    false;


                validateButton.classList.remove(
                    "loading"
                );


                validateButton.innerHTML = `

                    <i
                        data-lucide="shield-check"
                    ></i>

                    Validate Target & Continue

                    <i
                        data-lucide="arrow-right"
                    ></i>

                `;

            }


            refreshIcons();

        }


        // ==================================================
        // REDIRECT TO MIGRATION DASHBOARD
        // ==================================================

        function redirectToDashboard(
            targetSessionId
        ) {

            const parameters =
                new URLSearchParams({

                    source:
                        sourceCloud,

                    target:
                        targetCloud,

                    source_session_id:
                        sourceSessionId,

                    target_session_id:
                        targetSessionId

                });


            window.location.href =
                `/migration/dashboard?${parameters.toString()}`;

        }


        // ==================================================
        // CLOUD DISPLAY NAME
        // ==================================================

        function getCloudName(
            cloud
        ) {

            const names = {

                aws:
                    "AWS",

                azure:
                    "Azure",

                gcp:
                    "Google Cloud"

            };


            return (
                names[cloud] ||
                cloud
            );

        }


        // ==================================================
        // SAFE JSON RESPONSE
        // ==================================================

        async function parseJsonResponse(
            response
        ) {

            try {

                return await response.json();

            }

            catch (error) {

                return {

                    success: false,

                    message:
                        `Server returned an invalid response (${response.status}).`

                };

            }

        }


        // ==================================================
        // ESCAPE HTML
        // ==================================================

        function escapeHtml(
            value
        ) {

            const div =
                document.createElement(
                    "div"
                );


            div.textContent =
                String(value ?? "");


            return div.innerHTML;

        }


        // ==================================================
        // REFRESH LUCIDE ICONS
        // ==================================================

        function refreshIcons() {

            if (
                typeof lucide !==
                "undefined"
            ) {

                lucide.createIcons();

            }

        }

    }
);