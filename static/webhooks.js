let currentPage = 1;

document.addEventListener("DOMContentLoaded", () => {
    loadWebhooks();

    document.getElementById("createBtn").addEventListener("click", openModal);

    // Modal close
    document.querySelector(".close").addEventListener("click", closeModal);

    // Form submit
    document.getElementById("webhookForm").addEventListener("submit", saveWebhook);
});

function escapeHtml(text) {
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
    return text.replace(/[&<>"']/g, m => map[m]);
}

function loadWebhooks() {
    fetch("/api/webhooks")
        .then(res => res.json())
        .then(data => {
            const tbody = document.querySelector("#webhooksTable tbody");
            tbody.innerHTML = "";

            if (data.webhooks.length === 0) {
                tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; padding:20px;">No webhooks found</td></tr>`;
                return;
            }

            data.webhooks.forEach(w => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>${escapeHtml(w.url)}</td>
                    <td>${escapeHtml(w.event_type)}</td>
                    <td>${w.enabled ? "Yes" : "No"}</td>
                    <td>
                        <button class="action-btn edit-btn" onclick="editWebhook(${w.id}, '${escapeHtml(w.url)}', '${escapeHtml(w.event_type)}', ${w.enabled})">Edit</button>
                        <button class="action-btn delete-btn" onclick="deleteWebhook(${w.id})">Delete</button>
                        <button class="action-btn test-btn" onclick="testWebhook(${w.id}, this)">Test</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        })
        .catch(err => {
            alert("Failed to load webhooks: " + err);
        });
}

function openModal() {
    const modal = document.getElementById("modal");
    modal.style.display = "flex";
    modal.classList.add("fade-in");
    document.getElementById("modalTitle").textContent = "Create Webhook";
    document.getElementById("webhookForm").reset();
    document.getElementById("webhookId").value = "";
}

function closeModal() {
    const modal = document.getElementById("modal");
    modal.classList.remove("fade-in");
    modal.style.display = "none";
}

function editWebhook(id, url, event_type, enabled) {
    openModal();
    document.getElementById("modalTitle").textContent = "Edit Webhook";
    document.getElementById("webhookId").value = id;
    document.getElementById("url").value = url;
    document.getElementById("event_type").value = event_type;
    document.getElementById("enabled").checked = enabled;
}

function saveWebhook(e) {
    e.preventDefault();
    const id = document.getElementById("webhookId").value;
    const url = document.getElementById("url").value;
    const event_type = document.getElementById("event_type").value;
    const enabled = document.getElementById("enabled").checked;

    const method = id ? "PUT" : "POST";
    const apiUrl = id ? `/api/webhooks/${id}` : "/api/webhooks";

    const btn = document.querySelector("#webhookForm button[type='submit']");
    btn.disabled = true;
    btn.textContent = "Saving...";

    fetch(apiUrl, {
        method: method,
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({url, event_type, enabled})
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === "success") {
            closeModal();
            loadWebhooks();
        } else {
            alert("Failed: " + data.message);
        }
    })
    .catch(err => alert("Error: " + err))
    .finally(() => {
        btn.disabled = false;
        btn.textContent = "Save";
    });
}

function deleteWebhook(id) {
    if (!confirm("Are you sure you want to delete this webhook?")) return;

    fetch(`/api/webhooks/${id}`, {method: "DELETE"})
        .then(res => res.json())
        .then(data => {
            if (data.status === "success") {
                loadWebhooks();
            } else {
                alert("Failed: " + data.message);
            }
        })
        .catch(err => alert("Error: " + err));
}

function testWebhook(id, btn) {
    btn.disabled = true;
    btn.textContent = "Testing...";

    fetch(`/api/webhooks/${id}/test`, {method: "POST"})
        .then(res => res.json())
        .then(data => {
            if (data.status === "success") {
                alert(`Webhook test successful! Response code: ${data.response_code}, Time: ${data.response_time}ms`);
            } else {
                alert(`Webhook test failed: ${data.message}`);
            }
        })
        .catch(err => alert("Error testing webhook: " + err))
        .finally(() => {
            btn.disabled = false;
            btn.textContent = "Test";
        });
}