document.addEventListener("DOMContentLoaded", () => {

    const form =
        document.getElementById(
            "gcp-connection-form"
        );

    if (!form) return;

    form.setAttribute("aria-disabled", "true");
    form.querySelectorAll("input, select, button").forEach((element) => {
        element.disabled = true;
    });


    form.addEventListener(
        "submit",
        (event) => {

            event.preventDefault();
            alert("Google Cloud discovery and migration are not implemented in this prototype. No credentials were sent.");

        }
    );

});
