#!/bin/sh
# Planificateur : relance la pipeline à intervalle régulier pour traiter les
# nouveaux fichiers déposés dans le S3. Les fichiers déjà traités sont ignorés
# (anti-doublons par hash SHA-256), donc relancer ne coûte rien.
INTERVAL="${INTERVAL_SECONDS:-60}"
echo "[scheduler] démarrage, intervalle de ${INTERVAL}s"

# Laisse PostgreSQL et le S3 finir de démarrer
sleep 10

# Premier lancement : génère des CSV de démonstration, les envoie au S3 et les traite
python src/pipeline.py --generate || echo "[scheduler] premier lancement terminé avec le code $?"

while true; do
  sleep "$INTERVAL"
  echo "[scheduler] $(date -u +%Y-%m-%dT%H:%M:%SZ) lancement de la pipeline"
  python src/pipeline.py || echo "[scheduler] pipeline terminée avec le code $?"
done
