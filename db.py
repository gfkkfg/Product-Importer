import psycopg2
from psycopg2.extras import execute_values
from config import Config

# ---------------- Connection Helper ---------------- #
def get_connection():
    """
    Returns a new PostgreSQL connection using Config environment variables.
    """
    return psycopg2.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        dbname=Config.DB_NAME,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD
    )

# ---------------- Bulk UPSERT with Duplicate-SKU Protection ---------------- #
def bulk_upsert_products(products, page_size=2000):
    """
    Bulk upsert products safely with no duplicate SKU conflicts.

    Features:
    - Deduplicates SKUs within input list.
    - Normalizes SKUs to lowercase.
    - Skips invalid rows (missing SKU or name).
    - Uses page_size for execute_values batching.
    """
    if not products:
        return

    seen_skus = set()
    cleaned = []

    for p in products:
        sku = (p.get("sku") or "").strip().lower()
        name = (p.get("name") or "").strip()

        # Skip invalid rows
        if not sku or not name:
            continue

        # Skip duplicates inside this batch
        if sku in seen_skus:
            continue
        seen_skus.add(sku)

        cleaned.append((
            sku,
            name,
            (p.get("description") or "").strip(),
            bool(p.get("active", True))
        ))

    if not cleaned:
        return

    sql = """
        INSERT INTO products (sku, name, description, active)
        VALUES %s
        ON CONFLICT (sku)
        DO UPDATE SET
            name = EXCLUDED.name,
            description = EXCLUDED.description,
            active = EXCLUDED.active
    """

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            execute_values(cur, sql, cleaned, page_size=page_size)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


# ---------------- Get Products with Filters + Pagination ---------------- #
def get_products(filters=None, page=1, per_page=20):
    """
    Returns filtered products with pagination.
    """
    filters = filters or {}
    offset = (page - 1) * per_page
    conditions = []
    values = []

    # Build dynamic filters
    if filters.get("sku"):
        conditions.append("LOWER(sku) LIKE %s")
        values.append(f"%{filters['sku'].lower()}%")
    if filters.get("name"):
        conditions.append("LOWER(name) LIKE %s")
        values.append(f"%{filters['name'].lower()}%")
    if filters.get("description"):
        conditions.append("LOWER(description) LIKE %s")
        values.append(f"%{filters['description'].lower()}%")
    if filters.get("active") is not None:
        conditions.append("active = %s")
        values.append(filters["active"])

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    sql = f"""
        SELECT id, sku, name, description, active
        FROM products
        {where_clause}
        ORDER BY id DESC
        LIMIT %s OFFSET %s
    """
    values.extend([per_page, offset])

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(values))
            rows = cur.fetchall()
    finally:
        conn.close()

    return [
        {"id": r[0], "sku": r[1], "name": r[2], "description": r[3], "active": r[4]}
        for r in rows
    ]


# ---------------- Count Products for Pagination ---------------- #
def count_products(filters=None):
    """
    Returns the total number of products matching filters.
    """
    filters = filters or {}
    conditions = []
    values = []

    if filters.get("sku"):
        conditions.append("LOWER(sku) LIKE %s")
        values.append(f"%{filters['sku'].lower()}%")
    if filters.get("name"):
        conditions.append("LOWER(name) LIKE %s")
        values.append(f"%{filters['name'].lower()}%")
    if filters.get("description"):
        conditions.append("LOWER(description) LIKE %s")
        values.append(f"%{filters['description'].lower()}%")
    if filters.get("active") is not None:
        conditions.append("active = %s")
        values.append(filters["active"])

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT COUNT(*) FROM products {where_clause}"

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(values))
            return cur.fetchone()[0]
    finally:
        conn.close()
