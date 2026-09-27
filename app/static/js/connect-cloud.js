document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("target-connection-form");
    const button = document.getElementById("validate-clouds-btn");
    const status = document.getElementById("target-connection-status");
    const results = document.getElementById("validation-results");
    const sourceSessionId = document.getElementById("source-session-id")?.value?.trim();
    const csrfToken = () => document.querySelector('meta[name="csrf-token"]')?.content || "";
    const show = (element, text, state) => {
        if (!element) return;
        element.textContent = text;
        element.className = `${element.id === "validation-results" ? "validation-results" : "connection-status"} ${state || ""}`;
    };
    form?.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (!sourceSessionId) return show(status, "The AWS source session is missing.", "error");
        const payload = {
            source: "aws", target: "azure", source_session_id: sourceSessionId,
            tenant_id: document.getElementById("azure-tenant-id")?.value.trim(),
            client_id: document.getElementById("azure-client-id")?.value.trim(),
            client_secret: document.getElementById("azure-client-secret")?.value.trim(),
            subscription_id: document.getElementById("azure-subscription-id")?.value.trim(),
        };
        if (!payload.tenant_id || !payload.client_id || !payload.client_secret || !payload.subscription_id) return show(status, "Complete all Azure target fields.", "error");
        button.disabled = true;
        show(status, "Validating Azure target…", "loading");
        try {
            const response = await fetch("/api/migration/target/validate", {method: "POST", headers: {"Content-Type": "application/json", "X-CSRFToken": csrfToken()}, body: JSON.stringify(payload)});
            const result = await response.json();
            const targetSessionId = result.target_session_id || result.session_id;
            if (!response.ok || !result.success || !targetSessionId) throw new Error(result.message || "Azure target validation failed.");
            show(status, "Azure target verified.", "success");
            show(results, "Azure target verified. Opening the AWS to Azure workspace…", "success");
            window.location.assign(`/migration/dashboard?source=aws&target=azure&source_session_id=${encodeURIComponent(sourceSessionId)}&target_session_id=${encodeURIComponent(targetSessionId)}`);
        } catch (error) {
            show(status, error.message || "Azure target validation failed.", "error");
            show(results, "The Azure target was not connected. Review the safe error above and try again.", "error");
        } finally {
            button.disabled = false;
            if (window.lucide) window.lucide.createIcons();
        }
    });
    if (window.lucide) window.lucide.createIcons();
});
