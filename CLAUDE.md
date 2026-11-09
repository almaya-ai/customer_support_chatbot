# customer_support_chatbot

שירות Flask ב-Cloud Run. הוא שומר מסמכים ב-Cloud Storage, וסוכן דרך OpenRouter מחפש בהזמנה ובמסמכים המורשים של החשבון בלולאה עם כלים, ובוחר את שורות התשובה.

## פקודות

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/flask --app main:create_app run
./deploy.sh
python3 .claude/skills/live-check/check.py
```

תפעול ופתרון תקלות ב-[docs/runbook.md](docs/runbook.md). תרשים המימוש ב-[docs/architecture.html](docs/architecture.html).

## סודות ותצורה

- הריפו ציבורי. לא מוסיפים סודות, מידע אישי או קובץ `.env`.
- הגישה ל-Google היא בזהות Service Account. אין קובץ מפתח לזהות השירות.
- מפתח session והסיסמה של נציגת השירות והאדמין ב-Secret Manager. הוראות המערכת ב-Firestore. משתני תצורה מתועדים ב-`.env.example`.
- מפתח OpenRouter שייך למבקר: הוא נשמר בלשונית של הדפדפן ונשלח עם כל שאלה. לא שומרים אותו בשרת ולא כותבים אותו ללוג.

## שפה

- עברית למסמכים ולממשק, עם RTL.
- אנגלית לשמות בקוד, ללוגים, להודעות commit ולשדות `description` של skills.

## שיטת פיתוח

1. מתכננים שינויים בממשק, באחסון ובהרשאות לפני המימוש.
2. בודקים את החשבון המחובר, חשבון אחר ומקרה שבו אין מקור.
3. בודקים מה נשלח למודל ומציגים רק מקורות שאושרו בצד השרת.
4. אחרי פריסה מריצים `/live-check` ואת מקרי הבדיקה ב-[artifacts/CHECKS.md](artifacts/CHECKS.md).
5. מתעדים לקח שנבדק ב-[docs/lessons.md](docs/lessons.md) ומעדכנים את התרשים כשהחיבורים משתנים.

## זיכרון הפרויקט

עובדות על השירות נשמרות ב-`.claude/memory/`. לא כותבים בו פרטים אישיים או הגדרות למחשב מסוים.

@docs/lessons.md
@.claude/memory/MEMORY.md
