/* ==========================================================
                    AI CLOUD MIGRATION
                    NAVBAR
========================================================== */

document.addEventListener("DOMContentLoaded", () => {

    /* ==========================================
                    ELEMENTS
    ========================================== */

    const navbar = document.querySelector(".navbar");

    const themeToggle = document.getElementById("theme-toggle");

    const menuToggle = document.getElementById("menu-toggle");

    const mobileMenu = document.getElementById("mobile-menu");

    const mobileLinks = document.querySelectorAll(".mobile-menu a");


    /* ==========================================
                STICKY NAVBAR
    ========================================== */

    if (navbar) {

        window.addEventListener("scroll", () => {

            navbar.classList.toggle(

                "scrolled",

                window.scrollY > 40

            );

        });

    }


    /* ==========================================
                MOBILE MENU
    ========================================== */

    if (menuToggle && mobileMenu) {

        menuToggle.addEventListener("click", () => {

            mobileMenu.classList.toggle("active");

        });

    }


    /* ==========================================
            CLOSE MENU WHEN LINK CLICKED
    ========================================== */

    mobileLinks.forEach(link => {

        link.addEventListener("click", () => {

            mobileMenu.classList.remove("active");

        });

    });


    /* ==========================================
            CLOSE MENU WHEN CLICKING OUTSIDE
    ========================================== */

    document.addEventListener("click", (event) => {

        if (

            mobileMenu &&

            menuToggle &&

            !mobileMenu.contains(event.target) &&

            !menuToggle.contains(event.target)

        ) {

            mobileMenu.classList.remove("active");

        }

    });


    /* ==========================================
                    DARK MODE
    ========================================== */

    function updateThemeIcon(theme) {

        if (!themeToggle) return;

        themeToggle.textContent =

            theme === "dark"

                ? "☀"

                : "🌙";

    }


    const savedTheme =

        localStorage.getItem("theme") || "light";

    document.documentElement.setAttribute(

        "data-theme",

        savedTheme

    );

    updateThemeIcon(savedTheme);


    if (themeToggle) {

        themeToggle.addEventListener("click", () => {

            const currentTheme =

                document.documentElement.getAttribute(

                    "data-theme"

                );

            const newTheme =

                currentTheme === "dark"

                    ? "light"

                    : "dark";

            document.documentElement.setAttribute(

                "data-theme",

                newTheme

            );

            localStorage.setItem(

                "theme",

                newTheme

            );

            updateThemeIcon(newTheme);

        });

    }


    /* ==========================================
                SMOOTH SCROLL
    ========================================== */

    document

        .querySelectorAll('a[href^="#"]')

        .forEach(anchor => {

            anchor.addEventListener("click", function (e) {

                const target = document.querySelector(

                    this.getAttribute("href")

                );

                if (!target) return;

                e.preventDefault();

                target.scrollIntoView({

                    behavior: "smooth"

                });

            });

        });

});