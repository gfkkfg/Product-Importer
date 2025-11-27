import os
import requests
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename

from config import Config
from tasks import process_csv
from db import get_connection

# ============================================================
#                     APP SETUP
# ============================================================
app = Flask(__name__, template_folder="templates")
app.config.from_object(Config)
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

ALLOWED_EXTENSIONS = {"csv"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ============================================================
#                 DATABASE HELPER FUNCTIONS
# ============================================================

def fetch_all(query, params=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params or [])
        rows = cur.fetchall()
        return rows
    finally:
        cur.close()
        conn.close()

def execute_query(query, params=None, fetch_one=False, commit=True):
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(query, params or [])
        result = cur.fetchone() if fetch_one else None

        if commit:
            conn.commit()

        return result
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()


# ============================================================
#                      ROUTES (UI)
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/products")
def products_page():
    return render_template("products.html")


# ============================================================
#                  CSV UPLOAD + CELERY
# ============================================================

@app.route("/upload", methods=["POST"])
def upload_file():
    file = request.files.get("file")

    if not file:
        return jsonify({"error": "No file uploaded"}), 400
    if file.filename == "":
        return jsonify({"error": "Filename is empty."}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "Only CSV files allowed"}), 400

    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(file_path)

    task = process_csv.delay(file_path)
    return jsonify({"task_id": task.id}), 202


@app.route("/progress/<task_id>")
def task_progress(task_id):
    task = process_csv.AsyncResult(task_id)

    response = {
        "state": task.state,
        "progress": 0,
        "status": "Pending..."
    }

    if task.state == "PROGRESS":
        response.update({
            "progress": task.info.get("progress", 0),
            "status": task.info.get("status", "")
        })
    elif task.state == "SUCCESS":
        response.update({"progress": 100, "status": "Completed"})
    elif task.state == "FAILURE":
        response.update({"status": str(task.info)})

    return jsonify(response)


# ============================================================
#                  PRODUCTS API
# ============================================================

@app.route("/api/products", methods=["GET"])
def get_products():
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 10))

    search = request.args.get("search", "").strip()
    sku = request.args.get("sku", "").strip()
    active = request.args.get("active", "").strip().lower()

    offset = (page - 1) * per_page

    base_query = "FROM products WHERE 1=1"
    params = []

    if search:
        base_query += " AND (sku ILIKE %s OR name ILIKE %s OR description ILIKE %s)"
        params.extend([f"%{search}%"] * 3)

    if sku:
        base_query += " AND sku ILIKE %s"
        params.append(f"%{sku}%")

    if active in ["true", "false"]:
        base_query += " AND active=%s"
        params.append(active == "true")

    # fetch products
    rows = fetch_all(
        f"SELECT id, sku, name, description, active {base_query} ORDER BY id DESC LIMIT %s OFFSET %s",
        params + [per_page, offset]
    )

    # count total
    total = fetch_all(f"SELECT COUNT(*) {base_query}", params)[0][0]

    products = [{
        "id": r[0],
        "sku": r[1],
        "name": r[2],
        "description": r[3],
        "active": r[4]
    } for r in rows]

    return jsonify({
        "products": products,
        "total": total,
        "page": page,
        "per_page": per_page
    })


@app.route("/api/products", methods=["POST"])
def create_update_product():
    data = request.json

    product_id = data.get("id")
    sku = data.get("sku", "").strip()
    name = data.get("name", "").strip()
    description = data.get("description", "").strip()
    active = data.get("active", True)

    if not sku or not name:
        return jsonify({"status": "error", "message": "SKU and Name are required"}), 400

    try:
        if product_id:
            # update
            execute_query("""
                UPDATE products
                SET sku=%s, name=%s, description=%s, active=%s
                WHERE id=%s
            """, (sku, name, description, active, product_id))
        else:
            # insert (with conflict update)
            execute_query("""
                INSERT INTO products (sku, name, description, active)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (sku) DO UPDATE SET
                    name=EXCLUDED.name,
                    description=EXCLUDED.description,
                    active=EXCLUDED.active
            """, (sku, name, description, active))

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "success"})


@app.route("/api/products/<int:product_id>", methods=["DELETE"])
def delete_product(product_id):
    deleted = execute_query("DELETE FROM products WHERE id=%s RETURNING id", (product_id,), fetch_one=True)

    if not deleted:
        return jsonify({"status": "not found"}), 404

    return jsonify({"status": "deleted"})


@app.route("/api/products/bulk_delete", methods=["POST"])
def bulk_delete_products():
    try:
        # delete everything
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM products")
        deleted_count = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"status": "success", "deleted_count": deleted_count})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ============================================================
#                  WEBHOOK API
# ============================================================

@app.route("/api/webhooks", methods=["GET"])
def list_webhooks():
    rows = fetch_all("SELECT id, url, event_type, enabled, created_at, updated_at FROM webhooks ORDER BY id DESC")
    webhooks = [{
        "id": r[0],
        "url": r[1],
        "event_type": r[2],
        "enabled": r[3],
        "created_at": r[4].isoformat(),
        "updated_at": r[5].isoformat()
    } for r in rows]

    return jsonify({"webhooks": webhooks})


@app.route("/api/webhooks", methods=["POST"])
def create_webhook():
    data = request.json

    if not data.get("url") or not data.get("event_type"):
        return jsonify({"status": "error", "message": "url and event_type required"}), 400

    webhook_id = execute_query("""
        INSERT INTO webhooks (url, event_type, enabled)
        VALUES (%s, %s, %s)
        RETURNING id
    """, (data["url"], data["event_type"], data.get("enabled", True)), fetch_one=True)[0]

    return jsonify({"status": "success", "id": webhook_id})


@app.route("/api/webhooks/<int:webhook_id>", methods=["PUT"])
def update_webhook(webhook_id):
    data = request.json

    execute_query("""
        UPDATE webhooks
        SET url=%s, event_type=%s, enabled=%s, updated_at=%s
        WHERE id=%s
    """, (data.get("url"), data.get("event_type"), data.get("enabled"),
          datetime.utcnow(), webhook_id))

    return jsonify({"status": "success"})


@app.route("/api/webhooks/<int:webhook_id>", methods=["DELETE"])
def delete_webhook(webhook_id):
    deleted = execute_query("DELETE FROM webhooks WHERE id=%s RETURNING id",
                            (webhook_id,), fetch_one=True)
    if not deleted:
        return jsonify({"status": "not found"}), 404

    return jsonify({"status": "deleted"})


@app.route("/api/webhooks/<int:webhook_id>/test", methods=["POST"])
def test_webhook(webhook_id):
    row = fetch_all("SELECT url, event_type FROM webhooks WHERE id=%s", (webhook_id,))

    if not row:
        return jsonify({"status": "not found"}), 404

    url, event_type = row[0]

    try:
        response = requests.post(url, json={"event": event_type, "test": True}, timeout=5)
        return jsonify({
            "status": "success",
            "response_code": response.status_code,
            "response_text": response.text
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ============================================================
#                      RUN APP
# ============================================================
if __name__ == "__main__":
    app.run(debug=True)