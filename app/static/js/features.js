/* ==========================================================
                AI CLOUD MIGRATION
                  FEATURES MODULE
========================================================== */

document.addEventListener("DOMContentLoaded", () => {

    /* ==========================================
                FEATURE CARDS
    ========================================== */

    const featureCards = document.querySelectorAll(".feature-card");

    if (!featureCards.length) return;


    /* ==========================================
              INITIAL CARD STATE
    ========================================== */

    featureCards.forEach((card) => {

        card.style.opacity = "0";

        card.style.transform = "translateY(70px) scale(0.96)";

        card.style.transition =
            "opacity 0.7s ease, transform 0.7s ease";

    });


    /* ==========================================
              INTERSECTION OBSERVER
    ========================================== */

    const observer = new IntersectionObserver(

        (entries) => {

            entries.forEach((entry) => {

                if (!entry.isIntersecting) return;

                const card = entry.target;

                const index =
                    Array.from(featureCards).indexOf(card);


                /* ==================================
                    STAGGERED ANIMATION
                ================================== */

                setTimeout(() => {

                    card.style.transition =
                        "opacity 0.7s ease, transform 0.8s cubic-bezier(0.34, 1.56, 0.64, 1)";

                    card.style.opacity = "1";

                    card.style.transform = "translateY(0) scale(1)";

                    setTimeout(() => {

    card.style.transform = "";
    card.style.transition = "";

    card.classList.add("feature-floating");

}, 900);

                }, index * 150);


                /* ==================================
                    RUN ONLY ONCE
                ================================== */

                observer.unobserve(card);

            });

        },

        {
            threshold: 0.15
        }

    );


    /* ==========================================
                OBSERVE CARDS
    ========================================== */

    featureCards.forEach((card) => {

        observer.observe(card);

    });

});