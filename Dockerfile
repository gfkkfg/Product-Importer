# ---------------- Base Image ----------------
FROM python:3.11-slim

# ---------------- Set Working Directory ----------------
WORKDIR /app

# ---------------- Install Dependencies ----------------
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# ---------------- Copy Application Code ----------------
COPY . .

# ---------------- Create Upload Folder ----------------
RUN mkdir -p /tmp/uploads

# ---------------- Expose Web Port ----------------
EXPOSE 5000

# ---------------- Default Command ----------------
# This will be overridden in Render Start Command
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5000"]