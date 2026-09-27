/* ==========================================================
                AI CLOUD MIGRATION
                  SOLUTIONS MODULE
========================================================== */

document.addEventListener("DOMContentLoaded", () => {

    /* ==========================================
                    ELEMENTS
    ========================================== */

    const migrationCards =
        document.querySelectorAll(".migration-card");

    const migrationButtons =
        document.querySelectorAll(".migration-select-btn");

    if (!migrationCards.length) return;


    /* ==========================================
                SELECT MIGRATION
    ========================================== */

    migrationButtons.forEach((button) => {

        button.addEventListener("click", () => {

            const selectedRoute =
                button.dataset.route;

            const selectedCard =
                button.closest(".migration-card");


            /* ==========================================
                GET SOURCE AND TARGET
            ========================================== */

            const routeParts =
                selectedRoute.split("-");

            const sourceCloud =
                routeParts[0].toUpperCase();

            const targetCloud =
                routeParts[1].toUpperCase();


            /* ==========================================
                REMOVE PREVIOUS SELECTION
            ========================================== */

            migrationCards.forEach((card) => {

                card.classList.remove("selected");

            });


            migrationButtons.forEach((btn) => {

                btn.classList.remove("selected");

                btn.innerHTML = `
                    Select Migration
                    <i data-lucide="arrow-up-right"></i>
                `;

            });


            /* ==========================================
                SELECT CURRENT MIGRATION
            ========================================== */

            selectedCard.classList.add("selected");

            button.classList.add("selected");

            button.innerHTML = `
                Selected
                <i data-lucide="check"></i>
            `;


            /* ==========================================
                SAVE MIGRATION DATA
            ========================================== */

            localStorage.setItem(
                "selectedMigration",
                selectedRoute
            );


            sessionStorage.setItem(
                "source_cloud",
                sourceCloud
            );


            sessionStorage.setItem(
                "target_cloud",
                targetCloud
            );


            console.log(
                "Selected migration:",
                selectedRoute
            );

            console.log(
                "Source cloud:",
                sourceCloud
            );

            console.log(
                "Target cloud:",
                targetCloud
            );


            /* ==========================================
                REFRESH LUCIDE ICONS
            ========================================== */

            if (window.lucide) {

                lucide.createIcons();

            }


            /* ==========================================
                REDIRECT TO SOURCE CONNECTION
            ========================================== */

            setTimeout(() => {

                redirectToSourceConnection(
                    sourceCloud,
                    targetCloud
                );

            }, 500);

        });

    });

});


/* ==========================================================
            REDIRECT TO SOURCE CONNECTION
========================================================== */

function redirectToSourceConnection(
    sourceCloud,
    targetCloud
) {

    let redirectUrl = "";


    /* ==========================================
                    AWS
    ========================================== */

    if (sourceCloud === "AWS") {

        redirectUrl =
            `/migration/aws-source?target=${targetCloud.toLowerCase()}`;

    }


    /* ==========================================
                    AZURE
    ========================================== */

    else if (sourceCloud === "AZURE") {

        redirectUrl =
            `/migration/azure-source?target=${targetCloud.toLowerCase()}`;

    }


    /* ==========================================
                    GCP
    ========================================== */

    else if (sourceCloud === "GCP") {

        redirectUrl =
            `/migration/gcp-source?target=${targetCloud.toLowerCase()}`;

    }


    /* ==========================================
                INVALID CLOUD
    ========================================== */

    else {

        console.error(
            "Invalid source cloud:",
            sourceCloud
        );

        alert(
            "Invalid migration source selected."
        );

        return;

    }


    console.log(
        "Redirecting to:",
        redirectUrl
    );


    window.location.href =
        redirectUrl;

}