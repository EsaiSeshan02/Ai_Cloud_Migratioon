document.addEventListener("DOMContentLoaded", () => {

    const counters = document.querySelectorAll(".stat-number");

    if (counters.length === 0) return;

    const observer = new IntersectionObserver((entries) => {

        entries.forEach(entry => {

            if (!entry.isIntersecting) return;

            const counter = entry.target;

            const target = parseInt(counter.dataset.target);

            const suffix = counter.dataset.suffix || "";

            let current = 0;

            const increment = Math.ceil(target / 80);

            const updateCounter = () => {

                current += increment;

                if (current >= target) {

                    counter.textContent = target + suffix;

                    return;

                }

                counter.textContent = current + suffix;

                requestAnimationFrame(updateCounter);

            };

            updateCounter();

            observer.unobserve(counter);

        });

    }, {

        threshold: 0.5

    });

    counters.forEach(counter => observer.observe(counter));

});