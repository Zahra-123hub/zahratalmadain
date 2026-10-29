ZAHRAT AL-MADAYN: Website mit Python-Backend

Projektstruktur
  index.html, style.css, script.js       öffentliche Website
  images\                                feste Website-Bilder (Logo, Plakat, Icon)
  admin\index.html                      Admin-Seite
  admin\admin.css, admin\admin.js       Admin-Oberfläche
  parents\index.html                    Elternportal
  teachers\index.html                   Lehrkräfteportal
  portal.css, portal.js                 Gemeinsame Portal-Oberflächen
  backend\app\main.py                   FastAPI-Backend
  backend\requirements.txt               Python-Abhängigkeiten
  render.yaml                           Render-Blueprint
  content.json                          Inhalte und Metadaten

Vom Admin hochgeladene Galerie- und News-Bilder bleiben als verwaltete Dateien im
GitHub-Repository-Hauptverzeichnis; sie werden nicht in images\ abgelegt.
Diese öffentlichen Endpunkte und Dateien sind ausschließlich für öffentliche
Website-Inhalte gedacht. Private Kinderprofile, Berichte oder Fotos dürfen dort
nicht gespeichert oder veröffentlicht werden.

Die Website bleibt auf GitHub Pages. Die Admin-Oberfläche sendet keine GitHub-
Zugangsdaten mehr an den Browser. Das Python-Backend liest und ändert content.json
und Mediendateien über die GitHub-API. Ein Fine-grained GitHub-Token wird nur als
geheime Umgebungsvariable auf Render gespeichert.

Sprachen
- Öffentliche Website: Arabisch als Standardsprache, zusätzlich Englisch und Deutsch.
- Admin-Oberfläche: Arabisch als Standardsprache und Englisch über den Sprachschalter.
  Die Admin-Sprachauswahl wird im Browser gespeichert.

Einrichtung und Veröffentlichung
1. Den Projektstand nach main auf GitHub pushen.
2. Bei render.com anmelden und "New" > "Blueprint" wählen. Das Repository
   Zahra-123hub/Zahra-Almadain verbinden und den Blueprint render.yaml anwenden.
3. Beim Einrichten die abgefragten geheimen Werte setzen:
   - GITHUB_TOKEN: neuer Fine-grained Token für Zahra-Almadain,
     Repository permission Contents: Read and write
   - ADMIN_PASSWORD: ein neues, starkes Passwort für die Admin-Seite
   SESSION_SECRET wird von Render erzeugt. Den Token niemals in den Quellcode,
   in die Website oder in den Chat eintragen.
4. Render veröffentlicht die API unter
   https://zahra-123hub-almadain-api.onrender.com. Falls Render eine andere URL vergibt,
   muss apiBase in script.js und API_BASE in admin/admin.js auf diese URL zeigen.
5. GitHub Pages weiter für main und den Root-Ordner /(root) aktivieren.
6. Website: https://zahra-123hub.github.io/Zahra-Almadain/
   Admin:   https://zahra-123hub.github.io/Zahra-Almadain/admin/
   Admin-Anmeldung: Benutzername admin und das auf Render gesetzte Passwort.

Lokaler Backend-Test
  cd backend
  python -m pip install -r requirements.txt
  $env:GITHUB_TOKEN="DEIN_TOKEN"
  $env:ADMIN_PASSWORD="LOKALES_PASSWORT"
  $env:SESSION_SECRET="EIN_LANGER_ZUFAELLIGER_WERT"
  python -m uvicorn app.main:app --reload --port 8001

Vor dem lokalen Browser-Test API_BASE in script.js und admin/admin.js auf
http://127.0.0.1:8001 setzen. ALLOWED_ORIGINS muss den Ursprung der lokalen
Website enthalten.

Sicherheit
- Den zuvor im Chat offengelegten GitHub-Token widerrufen und einen neuen
  Token direkt als Render-Secret speichern.
- Das Admin-Passwort ist derzeit ein gemeinsames Passwort. Nicht mit anderen
  Personen teilen; individuelle Admin-Konten können später ergänzt werden.
- GitHub-Token und SESSION_SECRET nie veröffentlichen oder committen.

Plattform-Grundlage (erste Umsetzungsphase)
- Das Backend enthält jetzt ein versioniertes PostgreSQL-Schema für Konten,
  Rollen, Berechtigungen, minimale Kinderprofile, Elternzuordnungen,
  Lehrkraftzuordnungen, Tagesberichte, Einladungen, Sitzungen und
  fehlgeschlagene Anmeldungen.
- Für die Migrationen muss DATABASE_URL auf eine verwaltete PostgreSQL-Datenbank
  zeigen. Diese Datenbank muss vor dem Deployment bereitgestellt und als
  Render-Umgebungsvariable konfiguriert werden. „Naher Osten“ ist noch keine
  konkrete Anbieter-/Länderwahl; die Datenbank wurde deshalb nicht provisioniert.
- Lokal aus dem Ordner backend ausführen:
    python -m pip install -r requirements.txt
    $env:DATABASE_URL="postgresql://BENUTZER:PASSWORT@HOST/DATENBANK"
    alembic upgrade head
    python -m app.manage create-account --username ADMINNAME --role admin
- Das Konto-Werkzeug fragt das Passwort verdeckt ab und speichert nur einen
  Argon2-Hash. Zugangsdaten nicht in Dateien oder Chats ablegen.
- Das neue Plattform-Login liegt unter /api/platform/auth/login und verwendet
  widerrufbare Datenbanksitzungen. Das bisherige Admin-Login bleibt unverändert.
- Oberflächen lokal: http://127.0.0.1:8000/parents/ für Eltern und
  http://127.0.0.1:8000/teachers/ für Lehrkräfte. Nach GitHub-Pages-Deployment
  sind sie unter /Zahra-Almadain/parents/ und /Zahra-Almadain/teachers/
  erreichbar. Die öffentliche Website verlinkt beide Portale im Footer.
  Arabisch ist die Standardsprache; Englisch kann über den Sprachschalter
  gewählt werden.
- Eltern benötigen ein vom Kita-Team ausgestelltes Einladungstoken; eine freie
  Registrierung ist nicht möglich. Das Einlösen des Einladungstokens erstellt
  zunächst ein Konto mit Status „pending“; ein Administrator muss es im Admin-
  Bereich unter „حسابات المنصة“ freischalten. Vorher ist kein Login möglich.
  Lehrkraftkonten werden durch Administratoren dort erstellt, starten ebenfalls
  im Status „pending“ und müssen vor dem ersten Login freigeschaltet werden.
  Administratoren können aktive Eltern- und Lehrkraftkonten außerdem sperren;
  dadurch werden bestehende Plattform-Sitzungen widerrufen.
- Das bisherige Admin-Login authentifiziert den Kontoverwaltungsbereich. Dafür
  muss die bestehende Admin-Anmeldung funktionieren; Konten und Freigaben werden
  in der Plattformdatenbank gespeichert.
- Administratoren können Lehrkräfte über /api/platform/children/{id}/teachers
  zuweisen. Lehrkräfte erhalten nur zugewiesene Kinder; Eltern erhalten nur
  freigegebene Berichte zu ihren eingelösten Kind-Zuordnungen. Lehrkräfte
  speichern Berichte als Entwurf und senden sie zur Prüfung. Manager und
  Administratoren können eingereichte Berichte unter
  /api/platform/review/reports veröffentlichen oder zur Überarbeitung
  zurückgeben. Lehrkräfte können zurückgegebene Berichte bearbeiten und erneut
  einreichen.
- Die Eltern- und Lehrkräfteoberflächen und APIs arbeiten nur, wenn DATABASE_URL
  gesetzt ist und `alembic upgrade head` ausgeführt wurde. Render fragt DATABASE_URL
  jetzt als Secret ab; dort ist noch keine Datenbank provisioniert.
- Nur Admin-Konten können derzeit Kinderprofile anlegen und Einladungscodes
  ausstellen. Codes sind einmalig, laufen standardmäßig nach 24 Stunden ab und
  werden in der Datenbank nur gehasht gespeichert. Elternkonten entstehen erst
  beim Einlösen eines solchen Codes; deren API sieht ausschließlich zugeordnete
  Kinder mit minimalem Anzeigenamen.
- Lehrkräfte können nach Anmeldung im Lehrkräfteportal eigene PDF-, Bild- und
  Videodateien hochladen sowie bis zu fünf private Anhänge an einen Bericht im
  Entwurfsstatus anfügen. Dateien werden in der Plattformdatenbank gespeichert,
  sind nur für die hochladende Lehrkraft und Admin-Konten abrufbar und werden
  nicht mit veröffentlichten Elternberichten ausgeliefert. Admin-Konten sehen
  die Uploads im Lehrkräfteportal unter /teachers/. Erlaubt sind PDF
  bis 20 MB, Bilder bis 10 MB und MP4/WebM-Videos bis 25 MB pro Datei; das
  Speicherkontingent beträgt 250 MB pro Lehrkraftkonto.
- Für die Upload-Funktion muss die Migration 0004 mit `alembic upgrade head`
  angewandt werden. Die Dateidaten erhöhen den Speicherbedarf der PostgreSQL-
  Datenbank und ihrer Backups; das Speicherlimit des Datenbankanbieters ist vor
  dem produktiven Einsatz zu berücksichtigen.
- Die Migration 0005 ergänzt den Freigabestatus bestehender Konten. Bereits
  vorhandene Konten werden bei der Migration als aktiv übernommen; bei einer
  neuen Datenbank müssen alle Migrationen bis `head` angewandt werden.
- Portal-APIs benötigen DATABASE_URL. Ohne Konfiguration antworten sie mit
  „Service Unavailable“; es gibt keinen stillen Speicher-Fallback.
- Die Eltern- und Lehrkräfteoberflächen sowie private Lehrkraft-Uploads sind
  vorhanden. Es gibt noch keine Verwaltungsoberfläche für Plattformkonten und
  Zuordnungen und keine produktive Datenbank.
- Vor dem produktiven Speichern von Kinderdaten müssen konkreter Anbieter,
  Land/Region, Zugriffs- und Backupregeln sowie die erforderliche rechtliche
  Prüfung geklärt sein. Die aktuelle Entwicklungsumgebung nutzt für Tests nur
  eine temporäre SQLite-Datenbank.
