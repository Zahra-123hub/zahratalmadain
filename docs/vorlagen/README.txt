Vorlagen / قوالب الجداول الورقية
================================

In diesen Ordner gehoeren (nicht in Git, siehe .gitignore - personenbezogene Daten!):
  beitraege.csv   كشف اشتراكات ورسوم الأطفال
  gehaelter.csv   كشف رواتب الموظفين والمدرسات
sowie auf Wunsch die Fotos der Papiertabellen.

Beide CSV-Dateien: UTF-8, erste Zeile = Spaltenueberschriften wie auf dem Papier.

beitraege.csv
  م, اسم الطفل, الصف/الشعبة, الرسم/القسط المطلوب, المبلغ المدفوع, المتبقي,
  تاريخ الدفع, رقم الإيصال, ملاحظات
gehaelter.csv
  م, اسم الموظف/المدرسة, المسمى الوظيفي, الراتب الأساسي, المكافآت/الإضافي, السلف,
  الخصومات, الصافي المستحق, تاريخ الاستلام
Optionale Zusatzspalten in beiden: الشهر, السنة, العملة (USD/SYP), المصدر (Fotodatei)
Ohne Spalten الشهر/السنة: beim Import --year 2026 --month 9 angeben. Zeilen ohne Zeitraum werden
abgelehnt und im Bericht genannt (es wird nichts geraten).

Beträge so abtippen, wie sie auf dem Papier stehen: 1500000, ١٥٠٠٠٠٠, مليون ونصف, مليونين,
٣ مليون, 500000 + 250 ألف, 100$.  Währung ist ل.س (SYP), ausser eine Zelle sagt etwas anderes.
Unleserliches: Zelle LEER lassen (nichts raten). Die Zeile wird dann als "يحتاج مراجعة" gespeichert.

Import (im Ordner backend, DATABASE_URL gesetzt, "alembic upgrade head" ausgefuehrt):
  python -m app.import_vorlagen --dry-run     nur lesen und berichten
  python -m app.import_vorlagen               importieren
  python -m app.import_vorlagen --only fees   nur Beitraege
Fehlt eine CSV-Datei, bricht der Import ab und legt nichts an. Der Import ist wiederholbar
(Zeilen werden ueber Quelle + Zeilennummer erkannt). Nach jedem Lauf kommt ein Bericht: Zeilen je
Tabelle, needs_review, Summen (gefordert/bezahlt/offen) je Klasse und gesamt.

Wann eine Zeile "يحتاج مراجعة" wird
  - Name, Betrag, Datum nicht lesbar oder leer; geforderter Betrag leer oder 0
  - Bezahlt > gefordert, oder gefordert - bezahlt = offen geht nicht auf; Netto stimmt nicht
  - Währungszeichen weicht vom Blatt ab; Belegnummer doppelt; Betrag in Worten mehrdeutig
"مدفوع" gibt es nur bei geforderter Betrag > 0 und offen = 0 (und nicht markiert).
