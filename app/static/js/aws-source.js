/* ==========================================================
                AI CLOUD MIGRATION
                AWS SOURCE CONNECTION
========================================================== */

document.addEventListener(
    "DOMContentLoaded",
    () => {


        /* ==================================================
                    GET ELEMENTS
        ================================================== */

        const form =
            document.getElementById(
                "aws-connection-form"
            );


        const accessKey =
            document.getElementById(
                "aws-access-key"
            );


        const secretKey =
            document.getElementById(
                "aws-secret-key"
            );


        const region =
            document.getElementById(
                "aws-region"
            );


        const target =
            document.getElementById(
                "migration-target"
            );


        const secretToggle =
            document.getElementById(
                "secret-toggle"
            );


        const connectButton =
            document.querySelector(
                ".aws-connect-btn"
            );


        const connectionStatus =
            document.getElementById(
                "aws-connection-status"
            );


        /* ==================================================
                    REQUIRED ELEMENT CHECK
        ================================================== */

        if (
            !form ||
            !accessKey ||
            !secretKey ||
            !region ||
            !target ||
            !connectButton
        ) {

            console.error(
                "AWS source page elements were not found."
            );

            return;

        }


        /* ==================================================
                    SHOW / HIDE SECRET
        ================================================== */

        if (secretToggle) {

            secretToggle.addEventListener(
                "click",
                () => {

                    const isHidden =
                        secretKey.type ===
                        "password";


                    secretKey.type =
                        isHidden
                            ? "text"
                            : "password";


                    secretToggle.innerHTML =
                        isHidden
                            ? '<i data-lucide="eye-off"></i>'
                            : '<i data-lucide="eye"></i>';


                    if (window.lucide) {

                        lucide.createIcons();

                    }

                }
            );

        }


        /* ==================================================
                    AWS FORM SUBMIT
        ================================================== */

        form.addEventListener(
            "submit",
            async (event) => {

                event.preventDefault();


                const accessKeyValue =
                    accessKey.value.trim();


                const secretKeyValue =
                    secretKey.value.trim();


                const regionValue =
                    region.value.trim();


                const targetValue =
                    target.value
                        .trim()
                        .toLowerCase();


                /* ==========================================
                            LOCAL VALIDATION
                ========================================== */

                if (!accessKeyValue) {

                    showStatus(
                        "AWS Access Key ID is required.",
                        "error"
                    );

                    return;

                }


                if (!secretKeyValue) {

                    showStatus(
                        "AWS Secret Access Key is required.",
                        "error"
                    );

                    return;

                }


                if (!regionValue) {

                    showStatus(
                        "Please select an AWS region.",
                        "error"
                    );

                    return;

                }


                if (
                    targetValue !== "azure" &&
                    targetValue !== "gcp"
                ) {

                    showStatus(
                        "Invalid target cloud selected.",
                        "error"
                    );

                    return;

                }


                /* ==========================================
                            LOADING
                ========================================== */

                setLoading();


                try {

                    const response =
                        await fetch(

                            "/api/aws/connect",

                            {

                                method:
                                    "POST",

                                headers: {

                                    "Content-Type":
                                        "application/json"

                                },

                                body:
                                    JSON.stringify({

                                        access_key:
                                            accessKeyValue,

                                        secret_key:
                                            secretKeyValue,

                                        region:
                                            regionValue,

                                        target:
                                            targetValue

                                    })

                            }

                        );


                    const result =
                        await response.json();


                    /* ======================================
                            SUCCESS
                    ======================================= */

                    if (
                        response.ok &&
                        result.success
                    ) {

                        sessionStorage.setItem(

                            "aws_session_id",

                            result.session_id

                        );


                        sessionStorage.setItem(

                            "source_cloud",

                            "aws"

                        );


                        sessionStorage.setItem(

                            "target_cloud",

                            targetValue

                        );


                        sessionStorage.setItem(

                            "aws_region",

                            regionValue

                        );


                        showStatus(

                            "AWS credentials verified successfully.",

                            "success"

                        );


                        connectButton.innerHTML = `

                            <i data-lucide="circle-check"></i>

                            AWS Verified

                        `;


                        if (window.lucide) {

                            lucide.createIcons();

                        }


                        /* ================================
                                REDIRECT
                        ================================= */

                        setTimeout(
                            () => {

                                window.location.href =

                                    `/migration/connect-cloud?source=aws&target=${encodeURIComponent(
                                        targetValue
                                    )}&source_session_id=${encodeURIComponent(
                                        result.session_id
                                    )}`;

                            },

                            800
                        );


                    }


                    /* ======================================
                            FAILURE
                    ======================================= */

                    else {

                        showStatus(

                            result.message ||

                            "AWS credential validation failed.",

                            "error"

                        );


                        resetButton();

                    }


                }


                catch (error) {

                    console.error(
                        "AWS validation error:",
                        error
                    );


                    showStatus(

                        "Unable to contact the migration server.",

                        "error"

                    );


                    resetButton();

                }

            }

        );


        /* ==================================================
                    SET LOADING
        ================================================== */

        function setLoading() {

            connectButton.disabled =
                true;


            connectButton.classList.add(
                "loading"
            );


            connectButton.innerHTML = `

                <i data-lucide="loader-circle"></i>

                Validating AWS Credentials...

            `;


            showStatus(
                "Checking AWS credentials...",
                "loading"
            );


            if (window.lucide) {

                lucide.createIcons();

            }

        }


        /* ==================================================
                    RESET BUTTON
        ================================================== */

        function resetButton() {

            connectButton.disabled =
                false;


            connectButton.classList.remove(
                "loading"
            );


            connectButton.innerHTML = `

                <i data-lucide="shield-check"></i>

                Verify AWS Credentials

                <i data-lucide="arrow-right"></i>

            `;


            if (window.lucide) {

                lucide.createIcons();

            }

        }


        /* ==================================================
                    CONNECTION STATUS
        ================================================== */

        function showStatus(
            message,
            type
        ) {

            if (!connectionStatus) {

                return;

            }


            connectionStatus.className =
                `connection-status ${type}`;


            connectionStatus.innerHTML = `

                <span class="status-dot"></span>

                ${message}

            `;

        }


    }
);