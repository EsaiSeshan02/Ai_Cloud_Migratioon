/* ==========================================================
                AZURE SOURCE CONNECTION
========================================================== */

document.addEventListener("DOMContentLoaded", () => {


    /* ==========================================
                    ELEMENTS
    ========================================== */

    const form =
        document.getElementById(
            "azure-connect-form"
        );


    if (!form) {

        return;

    }


    const connectButton =
        form.querySelector(
            ".connect-cloud-btn"
        );


    /* ==========================================
                CREATE STATUS BOX
    ========================================== */

    const statusBox =
        document.createElement("div");

    statusBox.className =
        "azure-form-status";

    form.appendChild(
        statusBox
    );


    /* ==========================================
                FORM SUBMIT
    ========================================== */

    form.addEventListener(
        "submit",
        async (event) => {

            event.preventDefault();


            /* ======================================
                    GET FORM DATA
            ======================================= */

            const formData =
                new FormData(form);


            const data = {

                tenant_id:
                    formData.get("tenant_id"),

                client_id:
                    formData.get("client_id"),

                client_secret:
                    formData.get("client_secret"),

                subscription_id:
                    formData.get("subscription_id"),

                target:
                    form.dataset.target

            };


            /*
            ==========================================
                    DISABLE BUTTON
            ==========================================
            */

            connectButton.disabled =
                true;

            connectButton.innerHTML = `

                <i data-lucide="loader-circle"></i>

                Connecting Azure...

            `;


            if (window.lucide) {

                lucide.createIcons();

            }


            statusBox.textContent = "";

            statusBox.className =
                "azure-form-status";


            try {


                /* ==================================
                        SEND REQUEST
                =================================== */

                const response =
                    await fetch(

                        "/api/azure/connect",

                        {

                            method: "POST",

                            headers: {

                                "Content-Type":
                                    "application/json"

                            },

                            body:
                                JSON.stringify(data)

                        }

                    );


                const result =
                    await response.json();


                /* ==================================
                        SUCCESS
                =================================== */

                if (result.success) {


                    statusBox.textContent =
                        result.message;

                    statusBox.classList.add(
                        "success"
                    );


                    /*
                    SAVE SESSION
                    */

                    sessionStorage.setItem(

                        "migration_session_id",

                        result.session_id

                    );


                    sessionStorage.setItem(

                        "source_cloud",

                        "AZURE"

                    );


                    sessionStorage.setItem(

                        "target_cloud",

                        result.target.toUpperCase()

                    );


                    /*
                    REDIRECT TO SCAN
                    */

                    setTimeout(() => {

                        window.location.href =
                            "/migration/scan";

                    }, 1200);


                    return;

                }


                /* ==================================
                        ERROR
                =================================== */

                statusBox.textContent =
                    result.message ||
                    "Unable to connect Azure.";

                statusBox.classList.add(
                    "error"
                );


            }

            catch (error) {


                console.error(
                    "Azure connection error:",
                    error
                );


                statusBox.textContent =
                    "Unable to connect to the server.";

                statusBox.classList.add(
                    "error"
                );

            }


            /* ======================================
                    RESET BUTTON
            ======================================= */

            connectButton.disabled =
                false;

            connectButton.innerHTML = `

                <i data-lucide="plug"></i>

                Connect Azure

            `;


            if (window.lucide) {

                lucide.createIcons();

            }

        }

    );

});