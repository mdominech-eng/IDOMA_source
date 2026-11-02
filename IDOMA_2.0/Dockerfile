FROM python:3.12-slim
WORKDIR /app
COPY requirements-v2.txt ./requirements-v2.txt
RUN pip install --no-cache-dir -r requirements-v2.txt
COPY idoma_v2 ./idoma_v2
ENV IDOMA_ENV=production
ENV IDOMA_DB_PATH=/data/personal_ai.db
EXPOSE 8000
CMD ["uvicorn", "idoma_v2.server.main:app", "--host", "0.0.0.0", "--port", "8000"]
