document.addEventListener("DOMContentLoaded", () => {

    const dashboard = document.querySelector(".dashboard-preview");

    if (!dashboard) return;

    const observer = new IntersectionObserver((entries) => {

        entries.forEach(entry => {

            if (entry.isIntersecting) {

                dashboard.classList.add("dashboard-visible");

                observer.unobserve(dashboard);

            }

        });

    }, {

        threshold: 0.3

    });

    observer.observe(dashboard);

});