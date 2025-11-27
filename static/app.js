// ==========================================================
//                   CSV UPLOAD SECTION
// ==========================================================

const uploadArea = document.getElementById('upload-area');
const fileInput = document.getElementById('file-input');
const progressContainer = document.getElementById('progress-container');
const progressBar = document.getElementById('progress-bar');
const progressText = document.getElementById('progress-text');
const status = document.getElementById('status');
const retryBtn = document.getElementById('retry-btn');

let currentFile = null;

// Click → open file dialog
uploadArea.addEventListener('click', () => fileInput.click());

// Drag enter / over
['dragenter', 'dragover'].forEach(event => {
    uploadArea.addEventListener(event, e => {
        e.preventDefault();
        e.stopPropagation();
        uploadArea.classList.add('hover');
    });
});

// Drag leave / drop
['dragleave', 'drop'].forEach(event => {
    uploadArea.addEventListener(event, e => {
        e.preventDefault();
        e.stopPropagation();
        uploadArea.classList.remove('hover');
    });
});

// Drop file
uploadArea.addEventListener('drop', e => {
    const files = e.dataTransfer.files;
    if (files.length) handleFiles(files);
});

// File selected
fileInput.addEventListener('change', e => handleFiles(e.target.files));

// Retry
retryBtn.addEventListener('click', () => {
    if (currentFile) uploadCSV(currentFile);
});

// Handle file validation
function handleFiles(files) {
    const file = files[0];
    if (!file.name.endsWith('.csv')) {
        status.textContent = 'Please upload a valid CSV file.';
        return;
    }

    status.textContent = '';
    progressContainer.style.display = 'block';
    progressBar.style.width = '0%';
    progressText.textContent = '0%';
    retryBtn.style.display = 'none';
    currentFile = file;

    uploadCSV(file);
}

// Upload CSV to backend
function uploadCSV(file) {
    const formData = new FormData();
    formData.append('file', file);

    fetch('/upload', { method: 'POST', body: formData })
        .then(res => res.json())
        .then(data => {
            if (data.task_id) pollProgress(data.task_id);
            else throw new Error('Task ID not received');
        })
        .catch(() => {
            status.textContent = 'Upload failed. Please try again.';
            retryBtn.style.display = 'inline-block';
        });
}

// Poll Celery task progress
function pollProgress(taskId) {
    const interval = setInterval(() => {
        fetch(`/progress/${taskId}`)
            .then(res => res.json())
            .then(data => {
                const percent = data.progress || 0;

                progressBar.style.width = percent + '%';
                progressText.textContent = percent + '%';
                status.textContent = data.status || 'Processing...';

                if (data.state === 'SUCCESS') {
                    clearInterval(interval);
                    status.textContent = 'Import Complete!';
                    loadProducts();
                }

                if (data.state === 'FAILURE') {
                    clearInterval(interval);
                    status.textContent = `Failed: ${data.status || 'Error'}`;
                    retryBtn.style.display = 'inline-block';
                }
            })
            .catch(() => {
                clearInterval(interval);
                status.textContent = 'Error fetching progress.';
                retryBtn.style.display = 'inline-block';
            });
    }, 1000);
}



// ==========================================================
//                 PRODUCT MANAGEMENT SECTION
// ==========================================================

let currentPage = 1;
const perPage = 20;

// Init when page loads
document.addEventListener("DOMContentLoaded", () => {
    initEventListeners();
    loadProducts();
});

// Attach UI events
function initEventListeners() {
    document.getElementById("filterBtn").addEventListener("click", () => {
        currentPage = 1;
        loadProducts();
    });

    document.getElementById("prevPage").addEventListener("click", () => {
        if (currentPage > 1) {
            currentPage--;
            loadProducts();
        }
    });

    document.getElementById("nextPage").addEventListener("click", () => {
        currentPage++;
        loadProducts();
    });

    document.getElementById("createBtn").addEventListener("click", openCreateModal);

    document.querySelector(".close").addEventListener("click", closeModal);

    document.getElementById("productForm").addEventListener("submit", saveProduct);

    document.getElementById('bulk-delete-btn').addEventListener('click', bulkDeleteProducts);
}



// ==========================================================
//                       LOAD PRODUCTS
// ==========================================================

async function loadProducts() {
    const search = document.getElementById("search").value || '';
    const active = document.getElementById("activeFilter").value || '';

    try {
        const res = await fetch(`/api/products?page=${currentPage}&per_page=${perPage}&search=${search}&active=${active}`);
        const data = await res.json();

        renderProductsTable(data.products);

        document.getElementById("pageInfo").textContent =
            `Page ${data.page} of ${Math.ceil(data.total / perPage) || 1}`;
    } catch (err) {
        alert("Failed to load products.");
        console.error(err);
    }
}



// ==========================================================
//                    RENDER PRODUCT TABLE
// ==========================================================

function renderProductsTable(products) {
    const tbody = document.querySelector("#productsTable tbody");
    tbody.innerHTML = "";

    if (!products.length) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;">No products found.</td></tr>`;
        return;
    }

    products.forEach(p => {
        const tr = document.createElement("tr");

        tr.innerHTML = `
            <td>${p.sku}</td>
            <td>${p.name}</td>
            <td>${p.description}</td>
            <td>${p.active ? "Yes" : "No"}</td>
            <td>
                <button class="edit-btn" onclick="editProduct(${p.id}, '${p.sku}', '${p.name}', '${p.description}', ${p.active})">Edit</button>
                <button class="delete-btn" onclick="deleteProduct(${p.id})">Delete</button>
            </td>
        `;

        tbody.appendChild(tr);
    });
}



// ==========================================================
//                          MODAL
// ==========================================================

function openCreateModal() {
    openModal();
    document.getElementById("modalTitle").textContent = "Create Product";
    document.getElementById("productForm").reset();
    document.getElementById("productId").value = "";
}

function openModal() {
    document.getElementById("modal").style.display = "block";
}

function closeModal() {
    document.getElementById("modal").style.display = "none";
}

function editProduct(id, sku, name, description, active) {
    openModal();
    document.getElementById("modalTitle").textContent = "Edit Product";
    document.getElementById("productId").value = id;
    document.getElementById("sku").value = sku;
    document.getElementById("name").value = name;
    document.getElementById("description").value = description;
    document.getElementById("active").checked = active;
}



// ==========================================================
//                 CREATE / UPDATE PRODUCT
// ==========================================================

async function saveProduct(e) {
    e.preventDefault();

    const product = {
        id: document.getElementById("productId").value,
        sku: document.getElementById("sku").value,
        name: document.getElementById("name").value,
        description: document.getElementById("description").value,
        active: document.getElementById("active").checked
    };

    if (!product.sku || !product.name) {
        alert("SKU and Name are required.");
        return;
    }

    try {
        const res = await fetch("/api/products", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(product)
        });

        const data = await res.json();

        if (data.status === "success") {
            closeModal();
            loadProducts();
        } else {
            alert(`Error: ${data.message || 'Failed to save product'}`);
        }
    } catch (err) {
        console.error(err);
        alert("Failed to save product.");
    }
}



// ==========================================================
//                     DELETE PRODUCT
// ==========================================================

async function deleteProduct(id) {
    if (!confirm("Are you sure you want to delete this product?")) return;

    try {
        const res = await fetch(`/api/products/${id}`, { method: "DELETE" });
        const data = await res.json();

        if (data.status === "deleted") loadProducts();
        else alert("Failed to delete product.");
    } catch (err) {
        console.error(err);
        alert("Failed to delete product.");
    }
}



// ==========================================================
//                      BULK DELETE
// ==========================================================

async function bulkDeleteProducts() {
    if (!confirm("Are you sure? This cannot be undone.")) return;

    const btn = document.getElementById('bulk-delete-btn');
    btn.disabled = true;
    btn.textContent = 'Deleting...';

    try {
        const res = await fetch('/api/products/bulk_delete', { method: 'POST' });
        const data = await res.json();

        if (data.status === 'success') {
            alert(`All products deleted (${data.deleted_count})`);
            loadProducts();
        } else {
            alert('Failed: ' + data.message);
        }
    } catch (err) {
        console.error(err);
        alert('Error: ' + err);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Delete All Products';
    }
}
