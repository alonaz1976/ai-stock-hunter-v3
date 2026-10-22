"""Hebrew UX guidance only. V6.4.3.20: native HTML RTL renderer with synchronized loading; no trading calculations or DB mutations.

Kept separate from strategy/feedback code so its text may be improved without
changing predictions, entry gates, or SQLite persistence.
"""
import streamlit as st
import html
import re

HELP_VERSION = "6.4.3.20"

PAGES = {
    'Scanner': (
        'סריקת מניות והזדמנויות',
        'כאן המערכת מחפשת מניות, מחשבת מדדים ובוחרת מועמדות להמשך מעקב. לא כל מניה עם דירוג גבוה היא אישור קנייה.',
        [
            ('לפני שמריצים', 'בחר שווקים והיקף כיסוי. SMART בוחר מועמדות מובילות לניתוח עמוק; FULL מריץ ניתוח עמוק על כל המועמדות ששלב הגילוי בחר. FULL אינו בהכרח כל המניות בבורסה.'),
            ('▶ Start Scan', 'מפעיל סריקה חדשה. התוצאות המלאות נשמרות בסיום מוצלח; סריקת Reanalyze היא בדיקה חוזרת למועמדות בלבד ולא מחליפה את הצורך בסריקה מלאה.'),
            ('לקרוא את התוצאה', 'ENTRY NOW הוא אישור רק אם כל שערי מחיר, סשן, נזילות ותוכנית מסחר עברו. WAIT פירושו להמתין; DO NOT ENTER פירושו שאין כעת אישור להיכנס.'),
            ('להוריד Excel', 'שמור את האקסל לאחר סריקה מלאה, לפני שמריצים סריקת מועמדות חוזרת. הדוח כולל מידע מפורט על סיבות לחסימה.'),
        ],
    ),
    'Analyze': (
        'ניתוח מניה אחת',
        'כאן בודקים מניה שבחרת: מחיר, סשן, מגמה, רמות כניסה/ביטול, יעד, נזילות וסיכון. ניתוח אינו ביצוע עסקה.',
        [
            ('Ticker', 'סמל המניה, למשל NVDA בארה״ב או 1196.HK בהונג קונג.'),
            ('Forecast days / Target %', 'מסגרת הזמן ואחוז התנועה שאותם מבקשים לבדוק. אלה יעדי בדיקה, לא הבטחה לתשואה.'),
            ('▶ Start Analyze', 'מביא מידע מחדש ומחשב מצב עדכני. נתוני מחיר או שוק לא מאומתים עלולים לחסום אישור כניסה.'),
            ('Entry Zone / Stop / Targets', 'טווח כניסה אפשרי, רמת ביטול התרחיש והיעדים המחושבים. תוכנית לא תקפה לא מקבלת אישור מסחר.'),
        ],
    ),
    'Favorites': (
        'רשימת מעקב אישית',
        'כאן שומרים מניות שרוצים לחזור אליהן ומשווים מחיר שנשמר למחיר עדכני. בחירה כמועדפת אינה אות קנייה.',
        [
            ('כוכב מועדפים', 'מוסיף או מסיר מניה מרשימת המעקב.'),
            ('Frozen Price', 'מחיר שנשמר בעת ההוספה. הוא משמש להשוואה בלבד, ולא מחיר קנייה שבוצעה בפועל.'),
            ('מחיר עדכני', 'עשוי להיות מושהה או חסר בזמן שהבורסה סגורה; יש לבדוק זמן ציטוט לפני שימוש במסחר.'),
            ('Excel', 'מאפשר לשמור גיבוי של רשימת המעקב וההשוואות.'),
        ],
    ),
    'Valuation': (
        'מחקר שווי החברה',
        'כאן בוחנים האם מחיר השוק נראה גבוה או נמוך מהערכת שווי המבוססת על נתונים פיננסיים. לא מדובר בשער יעד מובטח.',
        [
            ('Fair Value', 'טווח שווי מוערך לפי מודל מתאים לענף, כאשר יש מספיק נתונים. לחברות בנייה/נדל״ן ולבנקים אין תמיד מודל DCF תקף. האומדן אינו מחיר מסחר בזמן אמת.'),
            ('Margin of Safety', 'מרווח הביטחון מחושב מול קצהו הנמוך של טווח השווי, ולא מול הערכת האמצע. חיובי פירושו שהמחיר נמוך מהקצה השמרני; אינו מבטיח הגנה מהפסד.'),
            ('Coverage Audit', 'מפריד בין כל המניות בשלב הגילוי, אלו שהגיעו לניתוח עמוק, אלו שיש להן אומדן שווי ואלו שחסרים להן נתונים. לא כל מניית גילוי נבדקת לשווי.'),
            ('Model Type / Confidence', 'מציג איזה סוג שווי חושב ולמה רמת הביטחון מוגבלת. HIGH אינו דיוק מוכח והנתונים הפיננסיים עשויים להיות ישנים.'),
            ('Undervalued', 'הערכת שווי גבוהה ממחיר השוק. מניה יכולה להישאר זולה או להמשיך לרדת.'),
            ('Possible Value Trap', 'ייתכן שהמניה זולה מסיבה עסקית או פיננסית בעייתית; חובה לבדוק דגלים אדומים.'),
            ('Evidence / Coverage', 'כמה מהנתונים הנדרשים זמינים ומה מידת האמון באומדן. NO DATA איננו ציון שלילי.'),
            ('Economic Moat', 'מדד חפיר כלכלי שנמצא בתכנון. NOT ASSESSED אומר שעדיין לא בוצעה בדיקה — לא שאין לחברה יתרון.'),
        ],
    ),
    'Optimizer': (
        'מחקר ושיפור מודל',
        'זהו אזור ניסויים. הוא בודק האם שינויים במודל עומדים במבחן נתונים שלא נחשפו בזמן הלמידה. אין כאן שינוי אוטומטי של אסטרטגיית המסחר.',
        [
            ('▶ Run Entry Optimization', 'מריץ ניסוי היסטורי לפי טווח, יעד ומניות שבחרת. התהליך יכול לקחת זמן.'),
            ('OOS / Holdout', 'תוצאות על נתונים שנשמרו מחוץ לשלב פיתוח המודל. מדגם קטן או תקופה אחת אינם הוכחת הצלחה.'),
            ('SHADOW ELIGIBLE', 'מודל שיכול להיבחן במקביל למודל הפעיל; אינו מקודם אוטומטית למסחר.'),
            ('Winner DNA', 'מחקר תנועות עבר: מחפש מה קרה לפני עליות ומה הופיע גם במניות שלא הצליחו. דוח מחקר אינו אות ENTRY NOW.'),
        ],
    ),
    'Feedback': (
        'בדיקת ביצועים ושמירת ההיסטוריה',
        'זה האזור שבו לומדים מה קרה אחרי האותות, מגבים את ההיסטוריה ומשחזרים אותה. ה־Feedback לא נחשב אחוז הצלחה עד שהחלונות הסתיימו ויש תוצאות נקיות.',
        [
            ('מצב וצעדים הבאים', 'מסך הבית מציג כמה אירועים ותוצאות נשמרו, האם קיים גיבוי ענן ומה הפעולה המומלצת עכשיו.'),
            ('גיבוי ושחזור', 'מורידים עותק SQLite, ממזגים גיבוי או מייבאים קובצי סריקות קודמים. לפני שחזור יש להוריד גיבוי מקומי.'),
            ('תוצאות בקצרה', 'מציג כמה חלונות כבר הבשילו, ומה אחוז ההצלחה לפי תוכנית שנשמרה בסריקה. לא בהכרח עסקאות שבוצעו.'),
            ('תוצאות לעומק', 'כאן מריצים Refresh due outcomes, בודקים מה קרה למניה בכל חלון ומורידים דוח מפורט. הבדיקה אינה סריקה חדשה.'),
            ('בדיקות אמינות', 'הפרדה בין רווח של עסקת נייר לפי כללי כניסה לבין תנועה תיאורטית אחרי אות. יש צורך במדגם משמעותי.'),
            ('מעבדות מחקר', 'Replay, Regular Signature ו־Explosive הם מחקר היסטורי, לא הוראת מסחר.'),
            ('דוחות', 'מורידים Excel מפורט או פשוט; דוח Excel אינו מחליף גיבוי SQLite שמכיל את ההיסטוריה.'),
        ],
    ),
}

GLOSSARY = {
    'Overall Score / Top Score': 'דירוג יחסי של איכות המועמדת לפי כלל האינדיקטורים. 80/100 אינו אומר סיכוי של 80% לעלייה.',
    'Opportunity Score': 'ציון שמעריך עד כמה תנאי ההזדמנות נראים מעניינים. לא אישור לכניסה.',
    'Entry Score': 'ציון מוכנות התזמון של כניסה, יחד עם תנאי אישור נוספים.',
    'ENTRY NOW': 'אישור המערכת לכניסה ברגע ההערכה, ורק אם כל שערי המחיר, הנזילות, הסשן ותוכנית המסחר עברו. אינו מבטיח רווח.',
    'WAIT / DO NOT ENTER': 'WAIT = תנאי הכניסה עדיין לא מתקיימים; DO NOT ENTER = קיימת חסימה או שהסיכון לא מתאים כרגע.',
    'BUILDING SETUP / ARMED': 'BUILDING SETUP = מצב טכני בהתהוות; ARMED = מתקיימים חלק ניכר מהתנאים אך נדרש טריגר תקף. לא הוראת קנייה.',
    'Quote Fresh / Verified': 'האם המחיר מעודכן מספיק והמקור/חותמת הזמן עומדים בכללי האימות. מחיר טרי לבדו אינו הופך כניסה למאושרת.',
    'Final Quote Recheck': 'בדיקה חוזרת של ציטוט המחיר למועמדות המובילות בסוף הסריקה.',
    'Quote Gate Diagnostics': 'דוח הסבר למה מחיר אושר או נחסם, כולל גיל הציטוט. PASS אינו אישור קנייה בפני עצמו.',
    'Entry Zone Audit': 'השוואה בין מחיר המניה לטווח הכניסה הפעיל. פערים מזעריים בעיגול נבדקים לפי אותה סבילות שבה משתמש המנוע. לא משנים את רמות הסיכון.',
    'Research Signal vs Trade Action': 'אות מחקרי יכול להראות ENTRY NOW אבל החלטת המסחר הסופית היא הקובעת. אם יש חסימה, האות מסומן כמחקר בלבד.',
    'Winner DNA 24h / 48h / 72h': 'מצב הנתונים מההיסטוריה שנשמרה 24, 48 ו־72 שעות לפני הסריקה; עדיין לא הוכח שהרשומות נוצרו לפני תחילת הזינוק. מחקר בלבד.',
    'Last Full Scan / Finalists': 'סריקה מלאה נשמרת בנפרד מהניתוח החוזר של מספר מניות מובילות. ניתן לעבור ביניהן מבלי לאבד את תצוגת הסריקה הרחבה.',

    'Full Deep Reanalyze Verified Finalists': 'סריקה חוזרת של מועמדות מאומתות — אינה סריקה רחבה של כל השווקים.',
    'RVOL': 'נפח המסחר יחסית למקובל, עם התאמה לשעה בשוק פתוח ככל שהמידע מאפשר.',
    'Liquidity': 'מידת האפשרות לקנות ולמכור בכמות סבירה בלי להשפיע מאוד על המחיר; שונה מ־RVOL.',
    'VWAP / EMA': 'מחיר ממוצע משוקלל בנפח / ממוצע נע. משמשים להבנת מיקום המחיר והמגמה.',
    'RSI / MACD': 'אינדיקטורים טכניים למומנטום ושינוי מגמה. אף אחד מהם לא מספיק בפני עצמו.',
    'Chase / Extension Risk': 'האם העלייה כבר התקדמה מדי והמניה רחוקה מנקודת כניסה סבירה. גבוה = סיכון לרדיפה.',
    'Target 1 / Target 2': 'יעדים אפשריים למהלך על פי התוכנית, לא מחירים מובטחים.',
    'Invalidation / Stop': 'רמה שבחצייתה הנחת העבודה של התרחיש נפסלת או מתוכננת עצירת הפסד.',
    'R:R': 'יחס הסיכוי לרווח מול הסיכון לפי רמות היעד והעצירה. תלוי באיכות ובזמינות מחירי הכניסה.',
    'Feedback Snapshot': 'תיעוד של החלטת המערכת בזמן הסריקה. לא הוכחה שהעסקה בוצעה.',
    'Pending / Matured Outcome': 'Pending = טרם הסתיימו מספיק ימי מסחר או שטרם נשלפו נתונים מלאים; Matured = נקלטו תוצאות לחלון שנבחר.',
    '1D / 2D / 3D / 5D': 'מספר ימי מסחר שהושלמו, לא מספר ימים קלנדריים. שבתות וחגים אינם בהכרח נספרים.',
    'MFE / MAE': 'התנועה המיטבית / הגרועה ביותר בכיוון העסקה בזמן הבדיקה. אינן תשואות ממכירה אמיתית.',
    'Target1 Before Invalidation': 'האם המחיר הגיע ליעד הראשון לפני רמת ביטול התרחיש, לפי הנתונים וכללי הספירה.',
    'Forward Paper Outcome': 'סימולציה אחרי אות שנשמר בזמן אמת עם כללי כניסה, עצירה ויציאה; לא עסקה שבוצעה בברוקר.',
    'OOS / Shadow': 'Out of Sample = מבחן על מידע מחוץ לאימון; Shadow = בדיקה מקבילה ללא החלפת המודל הפעיל.',
    'EventID / ORIGIN / TRACKING': 'מזהה אירוע ייחודי; ORIGIN היא התצפית הראשונה לצורכי למידה; TRACKING הוא מעקב שלא אמור להיספר כאירוע עצמאי נוסף.',
    'SQLite / Cloud Backup': 'SQLite הוא מסד ההיסטוריה המלא. ייצוא Excel אינו גיבוי מלא. גיבוי ענן מצריך הגדרה ואימות סנכרון נפרדים.',
}

LABS = {
    '🧬 Historical Replay': 'ניסוי היסטורי שמשחזר אותות ותקופות. עשוי למצוא דפוסים, אך אינו מוכיח הצלחה במסחר חי.',
    '🔎 Regular Signature': 'מחפש שילובי אינדיקטורים שחזרו לפני מהלכים רגילים של 2%–8%. נדרש אישור מחוץ למדגם.',
    '🚀 Explosive Benchmark': 'מחקר של מניה אחת בחיפוש תבניות לפני זינוקים של כ־15%. לא מנבא בוודאות זינוק נוסף.',
    '🌐 Explosive Universe': 'מדרג תבניות מוקדמות במניות רבות למחקר בלבד. ציון 100 אינו הסתברות של 100%.',
}


# Streamlit's st.markdown(..., unsafe_allow_html=True) still processes the
# text through its Markdown element. On Android Chrome the inherited LTR
# Markdown layout can override our preferred Hebrew paragraph presentation.
# Render the assistance itself with Streamlit's native HTML element (st.html),
# not the Markdown pipeline. This leaves trading cards and dataframes untouched.
# Mixed Latin terms are Bidi-isolated so Hebrew terminal punctuation stays LEFT.
_LTR_TOKEN = re.compile(
    r"(?<![\\w])(?:[0-9]+(?:[./][0-9]+)*[A-Za-z][A-Za-z0-9_./:%+\\-]*|"
    r"[A-Za-z][A-Za-z0-9_./:%+\\-]*)"
    r"(?: +(?:[A-Za-z][A-Za-z0-9_./:%+\\-]*|[0-9]+[A-Za-z][A-Za-z0-9_./:%+\\-]*))*"
)


def _bidi_text(value):
    raw = str(value)
    parts, prev = [], 0
    for match in _LTR_TOKEN.finditer(raw):
        parts.append(html.escape(raw[prev:match.start()]))
        parts.append('<bdi class="ash-help-ltr" dir="ltr">'
                     + html.escape(match.group()) + '</bdi>')
        prev = match.end()
    parts.append(html.escape(raw[prev:]))
    return ''.join(parts)


_RTL_CSS = '''<style>
.ash-help-rtl, .ash-help-rtl .ash-help-title, .ash-help-rtl .ash-help-paragraph,
.ash-help-rtl .ash-help-topic, .ash-help-rtl .ash-help-topic-name,
.ash-help-rtl .ash-help-topic-desc {
  direction: rtl !important;
  text-align: right !important;
  unicode-bidi: isolate;
  box-sizing: border-box;
  width: 100%;
  max-width: 100%;
  white-space: normal !important;
  word-break: normal !important;
  overflow-wrap: break-word !important;
}
.ash-help-rtl {
  display: block !important;
  margin: 0 !important;
  padding: 0 !important;
  line-height: 1.75 !important;
  font-family: Arial, "Noto Sans Hebrew", system-ui, sans-serif !important;
}
.ash-help-rtl .ash-help-title {
  display: block !important;
  font-size: 1.08rem !important;
  font-weight: 750 !important;
  margin: 0 0 .55rem 0 !important;
}
.ash-help-rtl .ash-help-paragraph {display:block!important;margin:0 0 .8rem 0!important;}
.ash-help-rtl .ash-help-topic {display:block!important;margin:.8rem 0!important;padding:0!important;}
.ash-help-rtl .ash-help-topic-name {
  display:block!important;font-weight:750!important;margin:0 0 .05rem 0!important;
}
.ash-help-rtl .ash-help-topic-desc {display:block!important;margin:0!important;padding:0!important;}
.ash-help-rtl .ash-help-ltr {
  direction:ltr!important;unicode-bidi:isolate!important;
  display:inline!important;white-space:normal!important;
}
.ash-help-rtl.ash-help-small {font-size:.88rem!important;color:#becadb!important;}
</style>'''


def _rtl_document(title=None, intro=None, topics=(), small=False):
    '''Build one real HTML RTL document, not a Markdown fragment.'''
    cls = 'ash-help-rtl ash-help-small' if small else 'ash-help-rtl'
    parts = [_RTL_CSS, f'<div class="{cls}" dir="rtl" lang="he" '
             'style="direction:rtl!important;text-align:right!important;'
             'display:block!important;width:100%!important;unicode-bidi:isolate!important;">']
    if title:
        parts.append('<div class="ash-help-title" dir="rtl">' + _bidi_text(title) + '</div>')
    if intro:
        parts.append('<p class="ash-help-paragraph" dir="rtl">' + _bidi_text(intro) + '</p>')
    for name, description in topics:
        parts.append('<div class="ash-help-topic" dir="rtl">'
                     '<div class="ash-help-topic-name" dir="rtl">' + _bidi_text(name) + '</div>'
                     '<p class="ash-help-topic-desc" dir="rtl">' + _bidi_text(description) + '</p>'
                     '</div>')
    parts.append('</div>')
    return ''.join(parts)


def _rtl_render(title=None, intro=None, topics=(), small=False):
    # st.html is supported by our Streamlit minimum version. Unlike
    # st.markdown, it does not re-parse RTL HTML as Markdown.
    st.html(_rtl_document(title, intro, topics, small=small))


def hebrew_heading(title):
    '''Right-align the visible Hebrew workspace headings without affecting data cards.'''
    st.html(_RTL_CSS + '<div class="ash-help-rtl" dir="rtl" lang="he" '
            'style="direction:rtl!important;text-align:right!important;width:100%!important;">'
            '<div class="section ash-help-title" dir="rtl" '
            'style="direction:rtl!important;text-align:right!important;">'
            + _bidi_text(title) + '</div></div>')


def hebrew_label(label):
    '''A real RTL label above a Streamlit widget whose control stays native.'''
    st.html(_RTL_CSS + '<div class="ash-help-rtl ash-help-small" dir="rtl" lang="he" '
            'style="direction:rtl!important;text-align:right!important;width:100%!important;">'
            '<div class="ash-help-topic-name" dir="rtl">'
            + _bidi_text(label) + '</div></div>')

def page_help(page):
    title, intro, topics = PAGES[page]
    with st.popover('ⓘ הסבר בעברית על המסך', use_container_width=False):
        _rtl_render(title, intro, topics)
    with st.popover('ⓘ מילון מונחים ומדדים', use_container_width=False):
        _rtl_render('מילון מונחים ומדדים', 'בחר מונח לקבלת הסבר בעברית פשוטה.')
        term = st.selectbox('איזה מונח להסביר?', list(GLOSSARY), key=f'glossary_{page}_v64314')
        _rtl_render(term, GLOSSARY[term])


def run_help(kind):
    topics = {
        'scanner': ('סריקה מלאה', 'Start Scan מפעיל סריקה לפי השווקים והכיסוי שנבחרו. Stop מבקש לעצור. מומלץ להוריד Excel מלא בסיום, לפני Reanalyze.'),
        'analyze': ('ניתוח מניה', 'Start Analyze בודק שוב נתונים ואותות למניה אחת. הוא אינו קונה מניה, ואינו משנה את משקלי המודל.'),
        'optimizer': ('אופטימיזציה', 'Run Entry Optimization בודק היסטורית משקלים ואופקים שונים; ניסוי חיוני אך אינו מבטיח הצלחה. Stop עוצר את הניסוי.'),
        'feedback': ('בדיקת תוצאות', 'Refresh due outcomes בודק האם הסתיימו ימי המסחר הנדרשים מאז האותות ומעדכן תוצאות שקיימים עבורן נתונים מלאים. הוא לא מריץ סריקה חדשה.'),
        'recovery': ('גיבוי ושחזור', 'Download מוריד מסד SQLite מלא; Merge משלב מידע משני מסדים בלי לאפס את החדש. Import Scanner XLSX מחזיר תצפיות מתיקיות Excel, אך לא תמיד את כל ההיסטוריה המקורית.'),
    }
    title, desc = topics[kind]
    with st.popover('ⓘ מה עושה ההרצה / הפעולה?', use_container_width=False):
        _rtl_render(title, desc)


def lab_help(lab):
    with st.popover('ⓘ הסבר על המחקר הזה', use_container_width=False):
        _rtl_render('על המחקר הזה', LABS.get(lab, 'כלי מחקר; לא אישור מסחר.'))


FEEDBACK_VIEWS = {
    '🏠 מצב המערכת': (
        'מסך הבית: כאן תראה כמה תצפיות יש במאגר, כמה חלונות תוצאה הושלמו ומה מצב הגיבוי. אלה לא עסקאות שבוצעו בפועל.',
        'אם הגיבוי בענן אינו מאומת, בחר בתפריט ״גיבוי ושחזור״ והורד עותק SQLite לפני כל התקנה.'
    ),
    '💾 גיבוי ושחזור': (
        'שומר ומחזיר את מסד הנתונים של הפרויקט. Download Feedback DB backup מוריד גיבוי מלא. Merge uploaded DB משלב מסד ישן בחדש. Import Scanner Excel משחזר תצפיות מסריקות ישנות.',
        'לפני שחזור: הורד גיבוי של המצב הנוכחי. Sync DB now יעבוד רק לאחר חיבור יעד גיבוי פרטי ואימות הסנכרון; התקנת גרסה לבדה לא מספיקה.'
    ),
    '📊 תוצאות בקצרה': (
        'מראה כמה תוצאות כבר הבשילו אחרי 1, 2, 3 או 5 ימי מסחר, וכמה הצלחות או כישלונות נמדדו. התוצאה מבוססת על תוכנית שנשמרה, לא על הוראות שבוצעו בברוקר.',
        'אל תסיק אחוז הצלחה ממדגם קטן או מחלונות שלא הסתיימו. לרענון נתונים יש לעבור ל״תוצאות לעומק״.'
    ),
    '🔬 תוצאות לעומק': (
        'כאן לוחצים Refresh due outcomes כדי לעדכן תוצאות לאירועים ישנים, לראות דוחות מפורטים ולהפיק Excel. זאת לא סריקת מניות חדשה.',
        'אם שום דבר לא הבשיל, בדוק שיש אירועי עבר ושחלפו ימי המסחר הדרושים. תוצאות לא קיימות אינן ניצחון ואינן הפסד.'
    ),
    '🛡️ בדיקות אמינות': (
        'השוואת סימולציות, תצפיות ותוצאות מסחר תיאורטי. המקום לבדוק אם האותות אמינים ולא רק נראים טוב על הגרף.',
        'Forward Paper אינו כסף אמיתי, ו־Replay היסטורי אינו שקול למבחן חי. צריך מדגם עצמאי ומבחן מחוץ למדגם.'
    ),
    '🧪 מעבדות מחקר': (
        'בחר אחת מארבע המעבדות כדי לבדוק תבניות היסטוריות: Historical Replay, Regular Signature, Explosive Benchmark או Explosive Universe.',
        'אלה ניסויים לצורכי מחקר. הם אינם מעניקים אישור ENTRY NOW ואינם מחליפים את משקלי המודל הפעיל.'
    ),
    '📤 דוחות להורדה': (
        'מכין קובצי Excel לניתוח, השוואה ושיתוף תוצאות. כל קובץ מציג צילום מצב בהתאם לנתונים הזמינים בו.',
        'Excel אינו תחליף לגיבוי SQLite של היסטוריית ה־Feedback. לגיבוי מלא עבור ל״גיבוי ושחזור״.'
    ),
}

def feedback_view_help(view):
    summary, tip = FEEDBACK_VIEWS[view]
    # The always-visible summary uses RTL too; st.caption() inherits LTR
    # from Streamlit on many mobile deployments.
    _rtl_render(intro=summary, small=True)
    with st.popover('ⓘ הסבר מפורט למסך הנבחר'):
        _rtl_render('על המסך הזה', summary, [('מה חשוב לזכור?', tip)])


def subsection_help(name):
    entries = {
        'optimizer': ('⚙️ אופטימיזציה', 'ניסוי משקלים וספים על נתוני עבר עם אימות מחוץ למדגם. התוצאה אינה משנה את המודל הפעיל ללא בחירה מפורשת ואישור. אין צורך להריץ אחרי כל סריקה.'),
        'winner_dna': ('🧬 מחקר Winner DNA', 'מחפש תבניות לפני עליות קודמות ומשווה אותן למניות שלא עלו. הרצה כבדה לצורך למידה — לא אות למסחר עכשיו.'),
        'validator': ('🔍 Cross-Stock Validator', 'בודק את אותם תנאים על קבוצת מניות כדי לצמצם תוצאות מקריות. זו בדיקת מחקר בלבד.'),
        'pre_move': ('📈 Pre-Move Discovery', 'מחפש סימני הצטברות ותנועה מוקדמים בהיסטוריה. הממצאים אינם אישור קנייה, והם דורשים אימות נפרד.'),
        'valuation': ('💎 סינון שווי', 'מציג מחקר שווי מהסריקה האחרונה שהסתיימה. FILTER משנה אילו מניות רואים, לא מחשב מחיר חדש ולא מפעיל עסקה.'),
        'chart': ('📉 רענון הגרף', 'מוריד נתוני מחיר לתצוגת הגרף בלבד. שינוי טווח זמן או שכבות לא משנה את אות הכניסה של Analyze.'),
    }
    title, explanation = entries[name]
    with st.popover('ⓘ מה עושים כאן?'):
        _rtl_render(title, explanation)
