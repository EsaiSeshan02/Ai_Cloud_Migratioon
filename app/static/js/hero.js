/* ==========================================================
                AI CLOUD MIGRATION
                    HERO MODULE
========================================================== */

class HeroAnimation {

    constructor() {

        this.init();

    }

    init() {

        this.initTyping();

        this.initCounters();

        this.initFloatingLogos();

        this.initParallax();

        this.initReveal();

    }

    /* ==========================================
                TERMINAL TYPING
    ========================================== */

    initTyping() {

    const terminal = document.getElementById("terminal-output");

    if (!terminal) return;

    const commands = [

        "> Initializing AI...",

        "✔ Loading Cloud Profiles...",

        "✔ Terraform Configuration Detected...",

        "✔ AWS Infrastructure Scanned...",

        "✔ AI Mapping Resources...",

        "✔ Security Analysis Running...",

        "✔ Migration Ready."

    ];

    let commandIndex = 0;

    const typeCommand = () => {

        if (commandIndex >= commands.length) return;

        const line = document.createElement("p");

        terminal.appendChild(line);

        const text = commands[commandIndex];

        let charIndex = 0;

        const typing = setInterval(() => {

            line.textContent += text.charAt(charIndex);

            charIndex++;

            terminal.scrollTop = terminal.scrollHeight;

            if (charIndex >= text.length) {

                clearInterval(typing);

                commandIndex++;

                setTimeout(typeCommand, 400);

            }

        }, 35);

    };

    terminal.innerHTML = "";

    typeCommand();

}

    /* ==========================================
                COUNTERS
    ========================================== */

    initCounters() {

    const counters = document.querySelectorAll(".counter");

    if (!counters.length) return;

    const observer = new IntersectionObserver((entries) => {

        entries.forEach(entry => {

            if (!entry.isIntersecting) return;

            const counter = entry.target;

            const target = parseFloat(counter.dataset.target);

            const suffix = counter.dataset.suffix || "";

            const decimals = parseInt(
                counter.dataset.decimals || "0"
            );

            let current = 0;

            const increment = target / 80;

            const updateCounter = () => {

                current += increment;

                if (current >= target) {
                    current = target;
                }

                counter.textContent =
                    current.toFixed(decimals) + suffix;

                if (current < target) {

                    requestAnimationFrame(updateCounter);

                }

            };

            updateCounter();

            observer.unobserve(counter);

        });

    }, {
        threshold: 0.5
    });

    counters.forEach(counter => {

        observer.observe(counter);

    });

}

    /* ==========================================
                FLOATING LOGOS
    ========================================== */

    initFloatingLogos() {

    const logos = document.querySelectorAll(".logo-float");

    if (!logos.length) return;

    logos.forEach((logo, index) => {

        const amplitude = 8 + index * 4;

        const speed = 0.001 + (index * 0.00025);

        const start = Math.random() * 1000;

        const animate = (time) => {

            const y = Math.sin((time + start) * speed) * amplitude;

            const x = Math.cos((time + start) * speed) * (amplitude / 2);

            logo.style.transform = `translate(${x}px, ${y}px)`;

            requestAnimationFrame(animate);

        };

        requestAnimationFrame(animate);

    });

}

    /* ==========================================
                PARALLAX
    ========================================== */

    initParallax() {

    const hero = document.querySelector(".hero");

    if (!hero) return;

    if (window.innerWidth <= 992) return;

    const terminal = document.querySelector(".hero-terminal");

    const glow = document.querySelector(".hero-glow");

    hero.addEventListener("mousemove", (e) => {

        const x = (e.clientX / window.innerWidth - 0.5);

        const y = (e.clientY / window.innerHeight - 0.5);

        terminal.style.transform = `translate(${x * 12}px, ${y * 12}px)`;

        glow.style.transform = `translate(${x * 30}px, ${y * 30}px)`;

    });

}

    /* ==========================================
                SCROLL REVEAL
    ========================================== */

    initReveal() {

    const elements = document.querySelectorAll(

        ".fade-left, .fade-right"

    );

    elements.forEach((element, index) => {

        element.style.opacity = "0";

        element.style.transform = "translateY(40px)";

        setTimeout(() => {

            element.style.transition =

                "all .8s ease";

            element.style.opacity = "1";

            element.style.transform =

                "translateY(0)";

        }, index * 250);

    });

}

}

/* ==========================================================
                    INITIALIZE
========================================================== */

document.addEventListener("DOMContentLoaded", () => {

    new HeroAnimation();

});