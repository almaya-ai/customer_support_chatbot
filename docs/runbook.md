# תפעול

## סודות וזהויות

`gcloud` משתמש בחשבון שמבצע את הפריסה. Cloud Run ניגש ל-GCS ול-Firestore דרך ה-Service Account שלו. מפתח ה-session וסיסמת נציגת השירות נשמרים ב-Secret Manager, ולא שומרים ערכים ב-git. מפתח OpenRouter לא נשמר בענן: כל מבקר מזין מפתח משלו בהגדרות שבראש הדף.

צרו סוד בשם `support-app-settings` עם JSON בשורה אחת. מפתח ה-session צריך להיות אקראי, באורך 32 תווים לפחות.

```json
{"session_key":"<random>","service_password":"<password>"}
```

קלט מוסתר ב-Bash מאפשר להעביר את הערך ישירות ל-Secret Manager:

```bash
source .env
gcloud services enable secretmanager.googleapis.com --project "$PROJECT"
read -rs -p "support-app-settings: " value
printf '\n'
printf '%s' "$value" | gcloud secrets create support-app-settings --project "$PROJECT" --replication-policy=automatic --data-file=-
unset value
```

אם הסוד כבר קיים ורוצים להחליף את הערך, השתמשו ב-`gcloud secrets versions add support-app-settings --project "$PROJECT" --data-file=-`.

## פריסה

הריצו `./deploy.sh`. הסקריפט מקים Bucket פרטי, מסד Firestore ייעודי וזהות שירות. הוא יוצר רק רשומות הזמנה חסרות ופורס את השירות עם גישה ציבורית.

**מה גישה ציבורית אומרת כאן:** כל מי שיש לו את הכתובת יכול להיכנס כלקוח, לקרוא את המסמכים של אותו לקוח ולהעלות קבצים. מי שמכיר את סיסמת הנציגה יכול להעלות מסמך שכל החשבונות רואים. בממשק אין מחיקת קבצים. לכן השירות מיועד לנתונים מדומים בלבד. ה-Bucket נשאר פרטי.

פתחו את כתובת השירות שהסקריפט מדפיס, הזינו מפתח OpenRouter בהגדרות והיכנסו. עברו על מקרי הבדיקה ב-[בדיקות השירות](../artifacts/CHECKS.md).

## פתרון תקלות

| מה רואים | מה בודקים |
|---|---|
| פריסה נעצרת לפני יצירת משאבים | האם לסוד `support-app-settings` יש גרסה פעילה |
| פתיחת כתובת Cloud Run מחזירה 403 | האם הפריסה הסתיימה עם `--allow-unauthenticated`, ואם מדיניות הארגון מאפשרת גישה ציבורית |
| השאלה נדחית ומבקשת מפתח | האם הוזן מפתח בהגדרות בלשונית הזו. לשונית חדשה מתחילה בלי מפתח |
| מפתח OpenRouter נדחה | האם המפתח פעיל ויש בו יתרה |
| PDF נדחה | האם אפשר לסמן טקסט בקובץ. אין OCR |
| הצ׳אט לא מחזיר פרטים על הזמנה אחרת | השרת מסנן לפי החשבון המחובר. זו התנהגות צפויה |
| החיבור למודל לא זמין | בדקו ש-`OPENROUTER_MODEL` זמין. בדקו את לוג השירות |
