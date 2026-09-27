document.addEventListener("DOMContentLoaded", () => {
    const button = document.querySelector('.migration-select-btn[data-route="aws-azure"]');
    if (!button) return;
    button.addEventListener("click", () => {
        button.disabled = true;
        button.classList.add("selected");
        sessionStorage.setItem("migration_route", "aws-azure");
        sessionStorage.setItem("source_cloud", "AWS");
        sessionStorage.setItem("target_cloud", "Azure");
        window.location.assign("/migration/aws-source?target=azure");
    });
});
