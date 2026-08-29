# רשימת בדיקות QA ידניות — Mentora

מסמך קבלה ידני, המבוסס על הקוד הנוכחי. הריצו על בסיס נתונים מקומי נפרד, עם שני משתמשים: **A** (בעל המשאבים) ו־**B** (משתמש אחר). אין להכניס סיסמאות או מפתחות API למסמך או לראיות הבדיקה.

## סיכום הרצה

| תחום | בדיקות | עבר | נכשל | חסום | לא הורץ |
| --- | ---: | ---: | ---: | ---: | ---: |
| התחברות וניווט | 3 | | | | 3 |
| שיעורים ותרגול | 5 | | | | 5 |
| היסטוריה והתקדמות | 4 | | | | 4 |
| קבצים וחיפוש בחומרים | 4 | | | | 4 |
| שיעורי בית וסוכן | 8 | | | | 8 |
| סטרימינג, קול, אבטחה ותפעול | 7 | | | | 7 |
| **סה״כ** | **31** | | | | **31** |

## התקדמות QA

- סה״כ בדיקות: 31
- P0 קריטי: 15; P1 גבוה: 13; P2 רגיל: 3; P3: 0
- עברו / נכשלו / חסומות / לא הורצו:

# מפת יכולות שהתגלו

| מזהה | תחום | יכולת | כניסה בממשק | שמירה | בדיקה |
| --- | --- | --- | --- | --- | --- |
| AUTH-01 | זהות | הרשמה, התחברות, יציאה ותוקף סשן | Login/Register | students, אחסון דפדפן | ידנית |
| AUTH-02 | זהות | אימייל חסין רישיות/רווחים ומניעת כפילות | Login/Register | students | ידנית |
| NAV-01 | ניווט | מסלולים מוגנים, ניווט ראשי והפניה ממסלול שגוי | כל המסלולים | token זמני | ידנית |
| LES-01 | שיעורים | בחירת נושא/תת־נושא ויצירת שיעור עם הסבר ראשון | Home/Topic | sessions, messages | ידנית |
| LES-02 | שיעורים | צ׳אט לימודי, רמת קושי ועיצוב מתמטי | Lesson | messages, difficulty | ידנית |
| LES-03 | שיעורים | מחזור שלבי השיעור והגבלות שלב | Lesson/Practice | phase/status | ידנית |
| PRAC-01 | תרגול | סטים, תשובות, משוב, סט נוסף וסיום | Practice | questions, performance | ידנית |
| SUM-01 | סיכום | סיכום שיעור/תרגול ותרגול מחדש | Summary | performance | ידנית |
| HIST-01 | היסטוריה | כל היסטוריית השיעורים, כולל נתונים ישנים | Progress | sessions/messages | ידנית |
| PROG-01 | התקדמות | מדדים ומפת לימוד; ללא שיעורי בית | Progress | performance | ידנית |
| PROG-02 | התקדמות | ניקוד לפי רמה (1/3/5) על תשובות תרגול נכונות, עד 100% | Practice → Progress | assessment_questions.level | ידנית |
| MAT-01 | חומרים | העלאה, תיוג, סינון ומחיקה של חומר לימוד | Files | materials/chunks/bytes | ידנית |
| MAT-02 | חומרים | חילוץ TXT/PDF/DOCX/PPTX/תמונה, כשל וניסיון חוזר | Files | status/text/chunks | ידנית |
| MAT-03 | חיפוש | שימוש בחומר רלוונטי בשיעור רגיל | Files → Lesson | chunks | ידנית |
| MAT-04 | קבצים | פתיחת המקור, הרשאה וטיפול בקובץ חסר | Files | storage_key | ידנית |
| HW-01 | שיעורי בית | יצירה, רשימה, שינוי שם וחידוש | Files/Homework | homework sessions | ידנית |
| HW-02 | שיעורי בית | העלאה, ניתוח וצ׳אט מונחה | Homework | materials/messages/outline | ידנית |
| HW-03 | שיעורי בית | ספירת תרגילים והתקדמות מבודדת | Homework/Files | performance | ידנית |
| AGENT-01 | סוכן | נתיבי סוכן, כלים, פעילות ועקבות בטוחות | Homework | agent state/traces | ידנית |
| AGENT-02 | סוכן | בדיקה דטרמיניסטית של תשובות מתמטיות | Homework | state/mastery | ידנית |
| AGENT-03 | סוכן | רמזים, מטרות, כוונות שאינן תשובה ואידמפוטנטיות | Homework | state/mastery | ידנית |
| VOICE-01 | סטרימינג | טקסט, אירועי כלים, TTS ומצב השמעה | Chat | messages | ידנית |
| VOICE-02 | קול | הקלטה, STT, TTS ו־barge-in | Chat composer | messages | ידנית |
| SEC-01 | אבטחה | בידוד כל משאב לפי תלמיד | UI/API | foreign keys | ידנית |
| OPS-01 | תפעול | health, CORS, לוגים ושגיאות שירות | API/UI | logs | ידנית |
| OPS-02 | תפעול | מיגרציות Alembic ונתונים היסטוריים | סביבת פיתוח | schema/version | ידנית |
| DATA-01 | שמירה | refresh, restart, login מחדש והיסטוריה | כל המסכים | נתונים עמידים | ידנית |
| API-01 | API | endpoint הודעה מיושן, עדיין עם הרשאה | API | messages | ידנית |
| MATH-01 | בטיחות | חסימות ביטויים מסוכנים/ארוכים | פנימי | — | אוטומטית בלבד |
| AGENT-04 | בטיחות סוכן | הסתרת control tags ומטרות מודל לא חוקיות | פנימי | state/trace | אוטומטית בלבד |
| STREAM-01 | עקביות | ביטול stream לא שומר מצב חלקי | Chat | transaction rollback | ידנית |
| PERF-01 | גבולות | גודל העלאה, context, timeout וצעדי סוכן | Files/Homework | bounded state | ידנית |

## בדיקות הכנה

- משתמש A ומשתמש B חדשים.
- `fractions.txt`: שני תרגילים, למשל `1/3 + 1/3` עם תשובה `2/3` ו־`1/4 + 1/4` עם תשובה `1/2`.
- `algebra.txt`: הסבר קצר על `2x + 3 = 11`; `unrelated.txt`: חומר לא קשור; `unsupported.xyz`; וקובץ ריק.
- להרצת סוכן: להחליף מקומית את `AGENT_ENABLED_HOMEWORK` ולהפעיל מחדש את ה־backend. אין לחשוף ערכי סוד.

# רשימת הבדיקות

## התחברות וניווט

- [ ] **T-AUTH-01 — הרשמה, התחברות ושמירת סשן** · **P0** · AUTH-01
  - הירשמו כ־A, ודאו הגעה לדף הבית; רעננו, עברו לדפים מוגנים, התנתקו והתחברו שוב.
  - מצופה: המשתמש והדפים המוגנים זמינים אחרי refresh; יציאה מסירה גישה; החשבון נשמר.

- [ ] **T-AUTH-02 — אימייל מנורמל ושגיאות התחברות** · **P1** · AUTH-02
  - נסו להירשם שוב עם אותו אימייל ברישיות/רווחים אחרים; התחברו עם אותו פורמט; נסו סיסמה שגויה.
  - מצופה: אין משתמש כפול; ההתחברות התקינה מצליחה; סיסמה שגויה נדחית.

- [ ] **T-NAV-01 — מסלולים מוגנים והפניה** · **P1** · NAV-01
  - ללא התחברות פתחו `/progress`, `/files` ו־`/lesson/999999`; לאחר התחברות עברו בכל הניווט; פתחו מסלול לא קיים ומחקו token.
  - מצופה: הפניה ל־Login ללא דליפת מידע; מסלול שגוי חוזר לבית; 401 מחזיר ל־Login עם הודעת פקיעה.

## שיעורים, תרגול וסיכום

- [ ] **T-LES-01 — מסלול שיעור בסיסי** · **P0** · LES-01, LES-02
  - בחרו נושא ותת־נושא, פתחו שיעור, בחרו קושי, שלחו שאלה ונסו פעולות “הסבר שוב”/“דוגמה נוספת”. רעננו.
  - מצופה: הסבר פתיחה, הודעות מסודרות, נוסחאות תקינות ורמת קושי נשמרת.

- [ ] **T-LES-02 — שלבי שיעור והגבלות** · **P0** · LES-03
  - עברו Teaching → Pre-practice → Practice → Practice summary → Summary → Completed; נסו לשלוח צ׳אט בשלב שאינו צ׳אט ולהפעיל פעולה אחרי סיום.
  - מצופה: רק מעברים חוקיים; פעולות לא חוקיות נדחות; שיעור שהושלם נשאר קריא אך אינו משתנה.

- [ ] **T-PRAC-01 — סט תרגול ומשוב** · **P0** · PRAC-01
  - התחילו תרגול, ענו על שלוש שאלות (נכונה, שגויה/ריקה, נכונה), שלחו ורעננו.
  - מצופה: ציון ומשוב לכל תשובה; תוצאות נשמרות ואינן מוכפלות או סותרות בדיקה דטרמיניסטית.

- [ ] **T-PRAC-02 — סט נוסף, ביצועים וסיכום** · **P1** · PRAC-01, SUM-01, PROG-01
  - בחרו “תרגל עוד”, בדקו מספר סט/קושי, סיימו, פתחו פירוט סיכום ועברו לסיכום השיעור.
  - מצופה: סט חדש, סיכום כולל ומדדי ביצוע נכונים.

- [ ] **T-SUM-01 — תרגול מחדש** · **P2** · SUM-01
  - לחצו Practice Again, בדקו שנוצר מזהה שיעור חדש, וחזרו לסיכום הישן.
  - מצופה: שני שיעורים נפרדים; הישן לא משתנה.

## היסטוריה, התקדמות ושמירה

- [ ] **T-HIST-01 — היסטוריה מלאה ונתונים ישנים** · **P0** · HIST-01
  - צרו כמה שיעורים, כולל שיעור היסטורי אם זמין; עברו על רשימת My Lessons וגבולות `limit/offset`; פתחו ישן וחדש.
  - מצופה: אין מגבלת “רק אחרונים”; שיעור ישן ללא agent state נשאר גלוי וניתן לפתיחה; שיעורי בית אינם ברשימת השיעורים.

- [ ] **T-PROG-01 — מפת התקדמות מבודדת** · **P1** · PROG-01, HW-03
  - בדקו את Progress ואת קישורי השיעורים; צרו/פתרו שיעורי בית ורעננו את Progress.
  - מצופה: נתוני שיעורי הבית אינם משפיעים על מפת הלימוד או סטטיסטיקת השיעורים.

- [ ] **T-PROG-02 — ניקוד התקדמות לפי רמת קושי** · **P0** · PROG-02, LES-02, PRAC-01
  - פתחו שיעור, בחרו **easy**, פתחו Progress ורשמו את אחוז תת־הנושא. חזרו, תרגלו וענו נכון על שאלה אחת בלבד, ובדקו שוב את Progress.
  - חזרו לצ׳אט של שיעור חדש, לחצו **Increase difficulty** עד **hard**, תרגלו וענו נכון על שאלה אחת.
  - הגישו שוב את אותו סט (רענון עמוד התרגול) עם תשובות שגויות לשאלות שכבר נענו נכון.
  - עברו שיעור שלם בלי לתרגל כלל, ובדקו את Progress.
  - מצופה: `+1%` ל־easy ו־`+5%` ל־hard לכל תשובה נכונה; שאלה שנענתה נכון נשארת נכונה ואינה מזכה שוב; הוראה וצ׳אט בלבד אינם מזיזים את האחוז; האחוז נעצר ב־100% ואינו יורד לעולם; פס הנושא הוא ממוצע כל תתי־הנושאים בתכנית.

- [ ] **T-DATA-01 — refresh, restart ו־login מחדש** · **P1** · DATA-01
  - על שיעור, חומר ושיעורי בית בצעו refresh, restart ל־frontend ול־backend, logout/login ופתחו היסטוריה.
  - מצופה: sessions, messages, questions, materials, performance ו־agent state נשמרים; draft, הקלטה, תור אודיו ו־busy הם זמניים.

## חומרים וחיפוש

- [ ] **T-MAT-01 — ספריית חומרי לימוד** · **P1** · MAT-01
  - העלו `algebra.txt`, תייגו/שנו תיוג, סננו, רעננו ומחקו.
  - מצופה: כרטיס עם סטטוס/chunks; תיוג נשמר; מחיקה מסירה גם את הקובץ והחומר אינו נשלף עוד.

- [ ] **T-MAT-02 — חילוץ, כשל וניסיון חוזר** · **P1** · MAT-02, PERF-01
  - בדקו פורמטים נתמכים ומגבלת גודל; העלו TXT וקבצים נתמכים זמינים; העלו `unsupported.xyz`, ריק וקובץ גדול; הפעילו reprocess פעמיים.
  - מצופה: ready רק לקובץ שנקרא; שגיאות ברורות; reprocess אינו משכפל chunks.

- [ ] **T-MAT-03 — שימוש בטקסט רלוונטי בשיעור** · **P1** · MAT-03
  - העלו חומר Algebra וחומר לא קשור; פתחו שיעור Algebra ושאלו על `2x + 3 = 11`; נסו גם תוכן עם prompt injection.
  - מצופה: החומר הרלוונטי עוזר; הלא־רלוונטי ושיעורי בית אינם נכנסים לקונטקסט; הוראות זדוניות בקובץ אינן מבוצעות.

- [ ] **T-MAT-04 — קובץ מקור והרשאות** · **P1** · MAT-04
  - פתחו קובץ לימוד וקובץ שיעורי בית מקורי. בסביבת בדיקה בלבד הזיזו את קובץ ה־fixture הידוע, נסו reprocess והחזירו אותו.
  - מצופה: פתיחה/הורדה תקינה לבעלים בלבד; קובץ חסר מסומן ככשל בלי קריסת המערכת.

## שיעורי בית וסוכן

- [ ] **T-HW-01 — יצירה, נראות וחידוש** · **P1** · HW-01
  - צרו Homework, העלו `fractions.txt` בלי Analyze וחזרו ל־Files; שנו שם ופתחו אותו שוב. צרו גם Homework ריק לגמרי.
  - מצופה: session עם קובץ בלבד מוצג; שם נשמר; session ריק באמת לא מופיע ברשימת החידוש.

- [ ] **T-HW-02 — העלאה, ניתוח וצ׳אט** · **P0** · HW-02
  - העלו, נתחו, שאלו על תרגיל, הוסיפו קובץ ונתחו שוב. נסו upload/analyze על מזהה של שיעור רגיל ב־API.
  - מצופה: פתיחה מונחית; קובץ לא קריא לא נכנס לקונטקסט; פעולה על שיעור רגיל נדחית.

- [ ] **T-HW-03 — התקדמות שיעורי בית** · **P1** · HW-03
  - ודאו 0/2, טענו שוב ללא הודעה, פתרו תרגיל, רעננו והשלימו שני.
  - מצופה: total נקבע מהקובץ; ההתקדמות מתעדכנת רק אחרי הודעה חדשה ואינה משנה Progress של שיעורים.

- [ ] **T-FLAG-01 — סוכן כבוי** · **P0** · AGENT-01
  - הגדירו `AGENT_ENABLED_HOMEWORK=false` והפעילו מחדש backend; צרו, העלו, נתחו ושוחחו.
  - מצופה: הנתיב הישן עובד; לא נוצרים agent_session_state, mastery או agent_trace בגלל flow זה.

- [ ] **T-FLAG-02 — סוכן פעיל** · **P0** · AGENT-01, AGENT-02
  - הגדירו `AGENT_ENABLED_HOMEWORK=true`, הפעילו מחדש, נתחו Homework ושלחו תשובה תוך צפייה ב־Agent Activity וב־`agent-traces`.
  - מצופה: פעילות כלים מסודרת; תגובה סופית אחת; אין control tags או טקסט תלמיד/חומר גולמי בעקבה.

- [ ] **T-AGENT-01 — תשובות מתמטיות דטרמיניסטיות** · **P0** · AGENT-02
  - שלחו `2/3`, תשובה שקולה, `The intermediate value is 1/3, but the final answer is 2/3`, ואז תשובה שגויה.
  - מצופה: תשובה נכונה/שקולה מתקדמת; המספר הסופי בהסבר מזוהה נכון; תשובה שגויה אינה מקדמת.

- [ ] **T-AGENT-02 — לא־תשובה, רמזים ותת־שלב** · **P0** · AGENT-03
  - שלחו `I don't know`, `Give me a hint`, `Explain again`, `Thanks`; לאחר מכן ענו נכונה על תרגיל מלא בזמן שתת־שלב ממתין.
  - מצופה: כוונות שאינן תשובה לא משנות mastery; רמזים מוגבלים; פתרון מלא מתקדם ולא נתקע בתת־שלב שכבר נפתר.

- [ ] **T-AGENT-03 — retry, timeout ו־fallback** · **P0** · AGENT-01, AGENT-03, PERF-01
  - שחזרו אותה בקשה עם אותו `turn_id` אחרי רמז ואחרי תשובה נכונה; נסו ללא `turn_id`; בסביבת בדיקה הדמו tool timeout/step cap.
  - מצופה: אין כפל רמזים/mastery/התקדמות; בקשה חסרה נדחית; timeout/כשל כלי מסתיים בתגובה בטוחה ולא בתקיעה.

## סטרימינג, קול, אבטחה ותפעול

- [ ] **T-STREAM-01 — stream והחזרת transaction** · **P0** · VOICE-01, STREAM-01
  - עם קול כבוי שלחו הודעה ארוכה ובדקו delta-ים; רעננו בסוף. שלחו שוב ובטלו בקשה/צאו מהדף לפני הסוף.
  - מצופה: תשובה מלאה נשמרת פעם אחת; ביטול לא משאיר הודעת תלמיד/תשובת מורה חלקית או learning evidence יתום.

- [ ] **T-VOICE-01 — speech stream והשמעה** · **P1** · VOICE-01
  - הפעילו Voice playback, שלחו שאלה מרובת משפטים, בדקו סדר טקסט/אודיו/אווטאר; כבו את האפשרות ושלחו שוב; נסו autoplay חסום אם אפשר.
  - מצופה: טקסט נשאר זמין גם כש־TTS נכשל; chunks מושמעים לפי סדר; מצב קול כבוי משתמש ב־text stream.

- [ ] **T-VOICE-02 — מיקרופון ו־barge-in** · **P1** · VOICE-02
  - הקליטו שאלה, עצרו ובדקו transcript/תשובה; בזמן תשובה התחילו הודעה חדשה או צאו; נסו דחיית הרשאת מיקרופון.
  - מצופה: משאבי מיקרופון/אודיו משתחררים; הודעה חדשה עוצרת ישנה; כשל STT/TTS/הרשאה לא חוסם צ׳אט כתוב.

- [ ] **T-SEC-01 — בידוד בין שני משתמשים** · **P0** · SEC-01, API-01
  - כ־B נסו מזהים של A ב־sessions, messages, materials, file, reprocess/delete, homework upload/list/analyze/progress/rename, agent traces ו־`POST /messages/{id}`.
  - מצופה: 401 ללא התחברות או 404/חסימה למשתמש B; אין קריאה, הורדה, mutation או דליפת metadata של A. כל הצלחה כאן היא P0.

- [ ] **T-OPS-01 — זמינות, CORS, לוגים ושגיאות** · **P2** · OPS-01
  - פתחו `GET /`; בצעו login/upload/chat ובדקו לוגים ללא סודות; עצרו backend, נסו פעולה, הפעילו שוב ונסו retry.
  - מצופה: הודעות שגיאה ברורות; retry מצליח לאחר התאוששות; CORS מאפשר רק origin מוגדר; אין רשומות חלקיות או סודות בלוגים.

- [ ] **T-OPS-02 — Alembic ושדרוג נתונים ישנים** · **P0** · OPS-02
  - על DB ריק הריצו `alembic upgrade head` ו־`alembic current`. על עותק תואם של baseline: השוו ל־0001, `stamp 0001`, ואז upgrade. פתחו נתונים ישנים ב־UI.
  - מצופה: revision `0005`; startup אינו משנה schema; נתונים קיימים נשארים נגישים.

- [ ] **T-PERF-01 — גבולות והתדרדרות בטוחה** · **P2** · PERF-01
  - העלו מסמך גדול שמייצר chunks רבים, שאלו שאלה רלוונטית ולא רלוונטית, נסו קובץ מעל הגבול, וב־Agent mode גרמו לכשל כלי מבוקר.
  - מצופה: מגבלות נאכפות; retrieval ממוקד ומוגבל; אין לולאה/כפל נתונים בעת כשל.

# מטריצת Feature Flags

| הגדרה | נדרשת הפעלה מחדש | בדיקות | תוצאה צפויה |
| --- | --- | --- | --- |
| `AGENT_ENABLED_HOMEWORK=false` | backend | T-FLAG-01, T-HW-01–03 | Homework ישן עובד; אין נתוני סוכן חדשים. |
| `AGENT_ENABLED_HOMEWORK=true` | backend | T-FLAG-02, T-AGENT-01–03 | ריצה עם סוכן, evaluator/reducer, כלי עבודה ועקבות metadata. |
| מגבלות agent/upload/context/CORS | backend | T-MAT-02–03, T-AGENT-02–03, T-OPS-01, T-PERF-01 | גבולות, timeouts ו־CORS נשמרים. |

# אימות DB אופציונלי (קריאה בלבד)

הריצו רק מול מסד ה־QA המיועד. החליפו placeholders.

```sql
SELECT version_num FROM alembic_version;
SELECT id, email FROM students ORDER BY id;
SELECT id, student_id, mode, phase, status, topic, subtopic FROM lesson_sessions WHERE student_id = :student_id ORDER BY created_at;
SELECT id, session_id, role, content, created_at FROM messages WHERE session_id = :session_id ORDER BY id;
SELECT session_id, score, total_questions, practice_sets, success_level FROM performance WHERE session_id = :session_id;
SELECT id, student_id, session_id, kind, filename, topic, status, status_detail FROM study_materials WHERE student_id = :student_id ORDER BY id;
SELECT material_id, chunk_index, char_count FROM material_chunks WHERE material_id = :material_id ORDER BY chunk_index;
SELECT session_id, current_exercise_index, hint_level, solved_refs, applied_evaluation_keys FROM agent_session_state WHERE session_id = :session_id;
SELECT student_id, subject, topic, skill, mastery_estimate, attempts, correct FROM student_skill_mastery WHERE student_id = :student_id;
SELECT run_id, session_id, step, kind, tool_name, duration_ms, error FROM agent_trace WHERE session_id = :session_id ORDER BY id;
```

# ביקורת כיסוי

## כיסוי בדיקות אוטומטיות

| תחום אוטומטי | בדיקה ידנית מקבילה | הערה |
| --- | --- | --- |
| auth, identity normalization, ownership | T-AUTH-01–02, T-SEC-01 | כיסוי ידני מלא ברמת מוצר |
| lesson state, practice, summaries | T-LES-01–02, T-PRAC-01–02, T-SUM-01 | כיסוי ידני מלא |
| ניקוד התקדמות לפי רמה | T-PROG-02 | אוטומטי ב־test_practice_progress.py |
| history ונתונים ישנים | T-HIST-01, T-DATA-01 | כולל regression visibility |
| materials, extraction, RAG | T-MAT-01–04, T-PERF-01 | כולל כשל/גבולות |
| homework flow/progress | T-HW-01–03 | כולל file-only session |
| agent, grading, idempotency | T-FLAG-01–02, T-AGENT-01–03 | כולל retries וכוונות לא־תשובה |
| streaming/voice | T-STREAM-01, T-VOICE-01–02 | כולל ביטול/כשל |
| migrations | T-OPS-02 | מסד QA בלבד |
| parser guardrails, control tags ומטרות מודל זדוניות | אוטומטית בלבד | דורש fixtures פנימיים/מודל מתוסרט, לא UI רגיל |

## כיסוי מסלולי Frontend

| מסלול | בדיקות | מכוסה |
| --- | --- | --- |
| `/login`, `/register` | T-AUTH-01–02, T-NAV-01 | כן |
| `/`, `/new`, `/topic/:topicId` | T-NAV-01, T-LES-01 | כן |
| `/progress` | T-HIST-01, T-PROG-01–02 | כן |
| `/files` | T-MAT-01–04, T-HW-01 | כן |
| `/homework/:sessionId` | T-HW-01–03, T-FLAG-01–02, T-AGENT-01–03 | כן |
| `/lesson/:sessionId` וכל תתי־מסלולי practice/summary | T-LES-01–02, T-PRAC-01–02, T-SUM-01, T-STREAM-01, T-VOICE-01–02 | כן |

## כיסוי API

כל 39 ה־endpoints נסקרים דרך ה־UI או API ידני: auth (3), sessions (5), progress (2), materials כולל homework/file (9), message מיושן (1), tutor/chat/voice/homework/agent/practice (18), ו־health (1). פירוט התרחישים מופיע בבדיקות T-AUTH עד T-OPS לעיל.

# תבנית דיווח תקלה

### BUG-001

- Test ID / Feature ID / Severity:
- סביבה ומשתמש:
- Session ID / Run ID:
- תנאים ושלבים:
- צפוי / בפועל:
- Screenshot / Console / Network:
- לוגים או DB/Trace (אם נבדק):
- הערות:

# סיכום כיסוי סופי

- יכולות שהתגלו: 31
- יכולות עם כיסוי ידני: 29
- יכולות אוטומטיות בלבד: 2 (ועוד invariants פנימיים ברמת unit)
- בדיקות ידניות/חצי־ידניות: 30
- מסלולי Frontend: 13/13
- endpoints: 39/39
- ישויות DB: 10/10 (9 טבלאות אפליקציה + `alembic_version`)
- Feature flags/configuration: 7/7
- יכולות לא מכוסות: 0

# פסק דין QA ידני

- [ ] PASS — כל P0/P1 עברו
- [ ] CONDITIONAL PASS — אין P0, קיימות תקלות נמוכות מתועדות
- [ ] FAIL — נמצאה תקלה חוסמת

## תקלות חוסמות

אין עדיין.

## תקלות לא חוסמות

אין עדיין.

## אזורים חסומים / לא נבדקו

תעדו כאן היעדר שירותי OpenAI/vision/STT/TTS, הרשאת מיקרופון, Agent mode או fixture למיגרציה.
