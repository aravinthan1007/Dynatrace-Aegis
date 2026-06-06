FROM python:3.11-slim

WORKDIR /app

# Node is required so the dashboard can launch the Dynatrace MCP via `npx`.
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
COPY demo_app/requirements.txt ./demo_app-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r demo_app-requirements.txt

COPY . .

ENV PORT=8080
CMD ["uvicorn", "dashboard.server:app", "--host", "0.0.0.0", "--port", "8080"]
