---
paths:
  - "deploy.sh"
  - "Dockerfile"
  - ".gcloudignore"
---

# Google Cloud

- מעבירים `--project` במפורש. כל משאב של השירות מוגדר ב-`deploy.sh`.
- מגבילים גישה ל-Bucket ולמסד הייעודיים. לא מקצים הרשאה ציבורית ל-Bucket.
- שומרים סודות ב-Secret Manager ומעדכנים את מדריך התפעול כשנוסף משאב.
