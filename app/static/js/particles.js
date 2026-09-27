document.addEventListener("DOMContentLoaded", () => {

    const container = document.querySelector(".cloud-container");

    if (!container) return;

    function createParticle() {

        const particle = document.createElement("div");

        particle.classList.add("pixel-particle");

        particle.style.left = (Math.random() * 100) + "%";

        particle.style.top = (45 + Math.random() * 10) + "%";

        container.appendChild(particle);

        gsap.to(particle, {

            x: 350,

            opacity: 0,

            duration: 2.5,

            ease: "none",

            onComplete: () => {

                particle.remove();

            }

        });

    }

    setInterval(createParticle, 180);

});