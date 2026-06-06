FROM python:3.11-slim

WORKDIR /app

COPY demo_app/requirements.txt ./demo_app-requirements.txt
RUN pip install --no-cache-dir -r demo_app-requirements.txt

COPY . .

ENV PORT=8080
CMD ["uvicorn", "demo_app.main:app", "--host", "0.0.0.0", "--port", "8080"]
