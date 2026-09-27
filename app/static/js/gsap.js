document.addEventListener("DOMContentLoaded", () => {

    if (typeof gsap === "undefined") {

        console.error("GSAP is not loaded.");

        return;

    }

    // ============================
    // Navbar
    // ============================

    gsap.from(".navbar",{

        y:-80,

        opacity:0,

        duration:1,

        ease:"power3.out"

    });


    // ============================
    // Hero Badge
    // ============================

    gsap.from(".hero-tag",{

        y:25,

        opacity:0,

        duration:.8,

        delay:.3

    });


    // ============================
    // Hero Title
    // ============================

    gsap.from(".hero-title",{

        y:40,

        opacity:0,

        duration:1,

        delay:.5,

        ease:"power3.out"

    });


    // ============================
    // Hero Description
    // ============================

    gsap.from(".hero-description",{

        y:30,

        opacity:0,

        duration:.8,

        delay:.8

    });


    // ============================
    // Hero Buttons
    // ============================

    gsap.from(".hero-buttons .btn",{

        y:25,

        opacity:0,

        stagger:.15,

        duration:.8,

        delay:1

    });


    // ============================
    // Statistics
    // ============================

    gsap.from(".stat-card",{

        y:40,

        opacity:0,

        stagger:.15,

        duration:.8,

        delay:1.3

    });


    // ============================
    // AWS Card
    // ============================

    gsap.from(".aws-card",{

        x:-80,

        opacity:0,

        duration:1.2,

        delay:1

    });


    // ============================
    // AI Card
    // ============================

    gsap.from(".ai-card",{

        scale:.5,

        opacity:0,

        duration:1,

        delay:1.4,

        ease:"back.out(1.7)"

    });


    // ============================
    // Azure Card
    // ============================

    gsap.from(".azure-card",{

        x:80,

        opacity:0,

        duration:1.2,

        delay:1.8

    });


    // ============================
    // Arrows
    // ============================

    gsap.from(".arrow",{

        scale:0,

        opacity:0,

        stagger:.3,

        duration:.6,

        delay:2

    });

});