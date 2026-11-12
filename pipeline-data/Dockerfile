# Image du "système de traitement" : la pipeline Python (S3 -> traitement -> PostgreSQL)
FROM python:3.12-slim

WORKDIR /app

# On installe d'abord les dépendances : cette couche est mise en cache tant que
# requirements.txt ne change pas (reconstruction beaucoup plus rapide).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY sql ./sql
COPY deploy/scheduler.sh ./scheduler.sh

CMD ["sh", "scheduler.sh"]
