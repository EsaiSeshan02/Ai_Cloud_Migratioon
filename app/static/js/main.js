document.addEventListener("DOMContentLoaded", () => {

    console.log("🚀 AI Cloud Migration Loaded Successfully");

    // ==========================================
    // Smooth Scroll Navigation
    // ==========================================

    document.querySelectorAll('a[href^="#"]').forEach(anchor => {

        anchor.addEventListener("click", function (e) {

            e.preventDefault();

            const target = document.querySelector(this.getAttribute("href"));

            if(target){

                target.scrollIntoView({

                    behavior:"smooth",

                    block:"start"

                });

            }

        });

    });


    // ==========================================
    // Navbar Shadow on Scroll
    // ==========================================

    const navbar = document.querySelector(".navbar");

    window.addEventListener("scroll", () => {

        if(window.scrollY > 30){

            navbar?.classList.add("scrolled");

        }

        else{

            navbar?.classList.remove("scrolled");

        }

    });


    // ==========================================
    // Active Navigation Link
    // ==========================================

    const sections = document.querySelectorAll("section");

    const navLinks = document.querySelectorAll(".nav-menu a");

    window.addEventListener("scroll", ()=>{

        let current = "";

        sections.forEach(section=>{

            const sectionTop = section.offsetTop - 120;

            if(window.scrollY >= sectionTop){

                current = section.getAttribute("id");

            }

        });

        navLinks.forEach(link=>{

            link.classList.remove("active");

            if(link.getAttribute("href") === "#" + current){

                link.classList.add("active");

            }

        });

    });
});