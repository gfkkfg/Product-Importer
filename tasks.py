import csv
from celery import Celery
from config import Config
from db import bulk_upsert_products
import requests

# ---------------- Celery Setup ---------------- #
celery = Celery(
    "tasks",
    broker=Config.CELERY_BROKER_URL,
    backend=Config.CELERY_RESULT_BACKEND,
)


# ---------------- CSV Processing Task ---------------- #
@celery.task(bind=True)
def process_csv(self, file_path, chunk_size=5000):
    """
    Safely processes a CSV file and bulk upserts products.

    Features:
    - Deduplicates SKUs globally across the entire CSV to prevent Postgres conflicts.
    - Deduplicates SKUs within each chunk: last occurrence wins.
    - Skips rows missing required fields.
    - Normalizes headers and values.
    - Efficient for very large CSVs (500k+ rows).
    """

    # -------- Step 1: Count total rows for progress -------- #
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            total_lines = max(sum(1 for _ in f) - 1, 0)  # exclude header
    except Exception as e:
        return {"status": "error", "message": f"Failed to read CSV: {str(e)}"}

    # -------- Step 2: Process CSV in chunks -------- #
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            # Normalize headers
            reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]

            chunk_map = {}       # SKU -> product (deduplicate within chunk)
            processed_skus = set()  # Global set to skip duplicates across chunks

            for i, row in enumerate(reader, start=1):
                row = {k.strip().lower(): (v.strip() if v else "") for k, v in row.items()}
                sku = row.get("sku", "").lower()
                name = row.get("name", "").strip()

                # Skip invalid rows
                if not sku or not name:
                    continue

                # Skip SKU if already processed in previous chunks
                if sku in processed_skus:
                    continue

                # Deduplicate inside chunk: last occurrence wins
                chunk_map[sku] = {
                    "sku": sku,
                    "name": name,
                    "description": row.get("description", ""),
                    "active": True,
                }

                # -------- Bulk upsert when chunk full -------- #
                if len(chunk_map) >= chunk_size:
                    bulk_upsert_products(list(chunk_map.values()))
                    processed_skus.update(chunk_map.keys())
                    chunk_map.clear()

                    # Update progress
                    percent = int((i / max(total_lines, 1)) * 100)
                    self.update_state(
                        state="PROGRESS",
                        meta={"progress": percent, "status": f"Processed {i}/{total_lines}"}
                    )

            # -------- Step 3: Upsert remaining records -------- #
            if chunk_map:
                bulk_upsert_products(list(chunk_map.values()))
                processed_skus.update(chunk_map.keys())

            # -------- Step 4: Final progress -------- #
            self.update_state(
                state="PROGRESS",
                meta={"progress": 100, "status": "Completed"}
            )

    except Exception as e:
        return {"status": "error", "message": f"CSV processing failed: {str(e)}"}

    return {"status": "success", "total_rows": total_lines}


# ---------------- Webhook Trigger Task ---------------- #
@celery.task
def trigger_webhook(url, payload):
    """
    Sends a POST request to a webhook URL.
    """
    try:
        response = requests.post(url, json=payload, timeout=10)
        return {
            "status": "success",
            "response_code": response.status_code,
            "response_text": response.text,
        }
    except Exception as e:
        return {"status": "failure", "message": str(e)}
