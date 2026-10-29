/* ===== إعدادات الروضة: عدّل هذه القيم فقط ===== */
var CONFIG = {
  apiBase: "https://zahra-123hub-almadain-api.onrender.com",
  whatsapp: "963985122704",
  phoneDisplay: "+963 985 122 704",
  mapUrl: "https://www.google.com/maps/search/?api=1&query=33.4815114%2C36.3742841",
  minAge: 2, maxAge: 6,
  hours: {ar: "", en: "", de: ""},   // مثال: {ar:"من الأحد إلى الخميس، 8:00 إلى 13:00", en:"Sunday to Thursday, 8:00 to 13:00", de:"Sonntag bis Donnerstag, 8:00 bis 13:00"}
  facebook: "https://www.facebook.com/profile.php?id=61593288236023",
  instagram: "https://www.instagram.com/zhrtalmdayn2026/",
  email: "",
  news: [
    {tag: {ar:"إعلان", en:"Announcement", de:"Ankündigung"},
     title: {ar:"الافتتاح الكبير لروضة زهرة المدائن", en:"Grand opening of Zahrat Al-Madayn", de:"Große Eröffnung von Zahrat Al-Madayn"},
     text: {ar:"إلى سكان دمشق: بشرى سارة من روضة زهرة المدائن الخاصة، الروضة المثالية. يسعدنا استقبالكم وزيارتكم.", en:"To the families of Damascus: good news from Zahrat Al-Madayn Private Kindergarten, the ideal kindergarten. We would be glad to welcome you.", de:"An die Familien von Damaskus: gute Nachrichten vom Privatkindergarten Zahrat Al-Madayn, dem idealen Kindergarten. Wir freuen uns auf Ihren Besuch."},
     img: "POSTER",
     cta: {ar:"سجّل طفلك", en:"Register your child", de:"Kind anmelden"}}
  ]
};
var ASSETS = {LOGO: "images/logo.png?v=2", POSTER: "images/poster.jpg"};

var DYN = {settings:{}, gallery:[], news:[]};
var API_BASE = (window.ZM_API_BASE || CONFIG.apiBase).replace(/\/+$/, "");
var L = "ar";
function tr(ar, en, de){ return L === "ar" ? ar : (L === "de" ? de : en); }
function T(o){ return o[L] || o.en || o.ar; }
var $ = function(id){ return document.getElementById(id); };
function store(k, v){ try{ if(v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); }catch(e){ return null; } }
document.querySelectorAll("img[data-a]").forEach(function(i){ i.src = ASSETS[i.dataset.a]; });

/* ---------- content data ---------- */
var AREAS = [
  {n:{ar:"اللعب", en:"Play", de:"Spielen"}, d:{ar:"اللعب الحر والموجّه ينمّي الحركة والخيال والصداقة، ويجعل التعلّم متعة كل يوم.", en:"Free and guided play builds movement, imagination and friendship, and makes learning a joy every day.", de:"Freies und angeleitetes Spielen fördert Bewegung, Fantasie und Freundschaft und macht das Lernen jeden Tag zur Freude."}, c:"#FDB913", dk:true,
   a:[{ar:"ألعاب حركية في الساحة", en:"Movement games outdoors", de:"Bewegungsspiele draußen"},
      {ar:"بناء بالمكعبات", en:"Building with blocks", de:"Bauen mit Bausteinen"},
      {ar:"لعب الأدوار", en:"Role play", de:"Rollenspiele"},
      {ar:"مسرح الدمى", en:"Puppet theatre", de:"Puppentheater"},
      {ar:"ألعاب جماعية تعلّم التعاون والصداقة", en:"Group games that teach cooperation and friendship", de:"Gruppenspiele, die Zusammenarbeit und Freundschaft lehren"},
      {ar:"أركان تعليمية للعب في الصف", en:"Learning corners for play in the classroom", de:"Lernecken zum Spielen im Gruppenraum"}]},
  {n:{ar:"العربية", en:"Arabic", de:"Arabisch"}, d:{ar:"نحرص في روضة زهرة المدائن على تأسيس أطفالنا لغوياً من خلال منهاج عربي متكامل ينمّي مهارات الاستماع والتحدث والقراءة والكتابة بأساليب ممتعة وتفاعلية، مع إثرائهم بتدريس الجزء الرشيدي لتعليم الحروف وأصواتها ومخارجها بطريقة صحيحة، لبناء أساس لغوي متين يرافق أطفالنا في مسيرتهم التعليمية.", en:"At Zahrat Al-Madayn Kindergarten we give our children a firm start in language through a complete Arabic curriculum that develops listening, speaking, reading and writing in fun, interactive ways. It is enriched by teaching the Rashidi part to learn the letters, their sounds and where they are pronounced, correctly. This builds a solid foundation in language that stays with our children throughout their learning journey.", de:"Im Kindergarten Zahrat Al-Madayn legen wir den sprachlichen Grundstein unserer Kinder mit einem vollständigen arabischen Lehrplan, der Zuhören, Sprechen, Lesen und Schreiben auf unterhaltsame, interaktive Weise fördert. Ergänzt wird er durch den Unterricht des Raschidi-Teils, in dem die Buchstaben, ihre Laute und ihre Artikulationsstellen richtig gelernt werden. So entsteht ein solides sprachliches Fundament, das unsere Kinder auf ihrem ganzen Bildungsweg begleitet."}, c:"#E0403D",
   a:[{ar:"الاستماع والتحدث", en:"Listening and speaking", de:"Zuhören und Sprechen"},
      {ar:"القراءة والكتابة", en:"Reading and writing", de:"Lesen und Schreiben"},
      {ar:"الحروف وأصواتها ومخارجها بطريقة صحيحة", en:"Letters, their sounds and where they are pronounced, correctly", de:"Buchstaben, ihre Laute und Artikulationsstellen, richtig gelernt"},
      {ar:"أساليب ممتعة وتفاعلية: قصص وأناشيد وألعاب", en:"Fun, interactive methods: stories, songs and games", de:"Unterhaltsame, interaktive Methoden: Geschichten, Lieder und Spiele"}]},
  {n:{ar:"الفنون", en:"Arts", de:"Kreatives"}, d:{ar:"رسم وتلوين وأشغال يدوية للتعبير عن المشاعر والأفكار، وتنمية الذوق والدقّة في اليدين.", en:"Drawing, coloring and crafts help children express feelings and ideas, and build taste and fine motor skills.", de:"Malen, Ausmalen und Basteln helfen, Gefühle und Ideen auszudrücken, und fördern Geschmack und Fingerfertigkeit."}, c:"#2F8FCB",
   a:[{ar:"رسم وتلوين", en:"Drawing and coloring", de:"Malen und Ausmalen"},
      {ar:"أشغال يدوية", en:"Handicrafts", de:"Basteln"},
      {ar:"تشكيل بالصلصال", en:"Modeling with clay", de:"Formen mit Knete"},
      {ar:"قصّ ولصق وتركيب", en:"Cutting, pasting and assembling", de:"Schneiden, Kleben und Zusammenbauen"},
      {ar:"التعبير عن المشاعر بالألوان", en:"Expressing feelings with colors", de:"Gefühle mit Farben ausdrücken"}]},
  {n:{ar:"الأرقام والعلوم", en:"Numbers and science", de:"Zahlen und Natur"}, d:{ar:"عدّ وتصنيف وتجارب بسيطة تفتح باب الاكتشاف، بأنشطة مونتيسوري ووسائل تعليمية حديثة.", en:"Counting, sorting and simple experiments open the door to discovery, with Montessori activities and modern teaching aids.", de:"Zählen, Sortieren und einfache Experimente öffnen die Tür zum Entdecken, mit Montessori-Aktivitäten und modernen Lernmitteln."}, c:"#17408F",
   a:[{ar:"العدّ والتصنيف", en:"Counting and sorting", de:"Zählen und Sortieren"},
      {ar:"الأرقام والمقارنة والترتيب", en:"Numbers, comparing and ordering", de:"Zahlen, Vergleichen und Ordnen"},
      {ar:"الأشكال والألوان", en:"Shapes and colors", de:"Formen und Farben"},
      {ar:"تجارب علمية بسيطة", en:"Simple science experiments", de:"Einfache Experimente"},
      {ar:"أنشطة مونتيسوري", en:"Montessori activities", de:"Montessori-Aktivitäten"},
      {ar:"وسائل تعليمية وشاشات عرض", en:"Teaching aids and display screens", de:"Lernmittel und Bildschirme"}]},
  {n:{ar:"القيم", en:"Values", de:"Werte"}, d:{ar:"قيم وأخلاق إسلامية تُغرس بالمحبة: المشاركة والاحترام والصدق والنظافة، عادات جميلة تكبر مع الطفل.", en:"Islamic values and good manners, taught with love: sharing, respect, honesty and cleanliness, good habits that grow with the child.", de:"Islamische Werte und gute Umgangsformen, mit Liebe vermittelt: Teilen, Respekt, Ehrlichkeit und Sauberkeit, gute Gewohnheiten, die mit dem Kind wachsen."}, c:"#4C8C1C",
   a:[{ar:"المشاركة والتعاون", en:"Sharing and cooperation", de:"Teilen und Zusammenarbeit"},
      {ar:"احترام الآخرين والكبار", en:"Respect for others and elders", de:"Respekt vor anderen und Älteren"},
      {ar:"الصدق والأخلاق الحسنة", en:"Honesty and good manners", de:"Ehrlichkeit und gute Umgangsformen"},
      {ar:"النظافة الشخصية وغسل اليدين", en:"Personal hygiene and hand washing", de:"Persönliche Hygiene und Händewaschen"}]},
  {n:{ar:"القرآن", en:"Qur'an", de:"Koran"}, d:{ar:"يبدأ يومنا بأذكار الصباح، ويتعلم الطفل القرآن الكريم حفظاً وتلاوة بالتجويد الميسّر بما يناسب عمره.", en:"Our day begins with the morning azkar, and the child learns the Qur'an, memorizing and reciting with simplified tajweed suited to their age.", de:"Unser Tag beginnt mit den Morgen-Azkar, und das Kind lernt den Koran: Auswendiglernen und Rezitieren mit vereinfachtem Tajwid, passend zum Alter."}, c:"#0F8F7A",
   a:[{ar:"أذكار الصباح", en:"Morning azkar", de:"Morgen-Azkar"},
      {ar:"الأذكار اليومية والدعاء", en:"Daily Azkar and supplications", de:"Tägliche Azkar (Gebete) und Bittgebete"},
      {ar:"حفظ القرآن الكريم", en:"Memorizing the Qur'an", de:"Den Koran auswendig lernen"},
      {ar:"التلاوة بالتجويد الميسّر بما يناسب عمر الطفل", en:"Recitation with simplified tajweed suited to the child's age", de:"Rezitation mit vereinfachtem Tajwid, passend zum Alter"}]}
];
var DOCS = [
  {ar:"وثيقة ميلاد الطفل أو صورة عن دفتر العائلة", en:"Child's birth certificate or a copy of the family book", de:"Geburtsurkunde des Kindes oder Kopie des Familienbuchs"},
  {ar:"صورة عن هوية ولي الأمر", en:"A copy of the parent's ID", de:"Kopie des Ausweises der Eltern"},
  {ar:"بطاقة اللقاحات", en:"Vaccination card", de:"Impfpass"},
  {ar:"صور شخصية للطفل", en:"Passport-size photos of the child", de:"Passfotos des Kindes"},
  {ar:"أرقام هاتف للطوارئ", en:"Emergency phone numbers", de:"Notfallnummern"}
];
var BAG = [
  {ar:"ملابس بديلة", en:"A change of clothes", de:"Wechselkleidung"},
  {ar:"قنينة ماء", en:"A water bottle", de:"Trinkflasche"},
  {ar:"وجبة خفيفة صحية", en:"A healthy snack", de:"Ein gesunder Snack"},
  {ar:"مناديل ورقية", en:"Tissues", de:"Taschentücher"},
  {ar:"حقيبة ظهر عليها اسم الطفل", en:"A backpack with the child's name", de:"Rucksack mit dem Namen des Kindes"}
];
var FAQ = [
  {q:{ar:"كيف أسجّل طفلي؟", en:"How do I register my child?", de:"Wie melde ich mein Kind an?"}, a:{ar:"املأ النموذج في هذه الصفحة، أو راسلنا على واتساب، أو تفضّل بزيارة الروضة.", en:"Fill in the form on this page, write to us on WhatsApp, or visit the kindergarten.", de:"Füllen Sie das Formular auf dieser Seite aus, schreiben Sie uns auf WhatsApp oder besuchen Sie den Kindergarten."}},
  {q:{ar:"هل يمكنني الزيارة قبل التسجيل؟", en:"Can I visit before registering?", de:"Kann ich vor der Anmeldung vorbeikommen?"}, a:{ar:"نعم. اختر «حجز زيارة» في النموذج وحدد يوماً، وسنؤكد معك الموعد.", en:"Yes. Choose “Book a visit” in the form and pick a day. We will confirm the time with you.", de:"Ja. Wählen Sie im Formular «Besuch buchen» und einen Tag, wir bestätigen Ihnen die Uhrzeit."}},
  {q:{ar:"ما الأعمار التي تستقبلها الروضة؟", en:"Which ages do you accept?", de:"Welche Altersgruppen nehmen Sie auf?"}, a:{ar:"الأطفال من 2 إلى 6 سنوات. يمكنك التحقق من عمر طفلك في ركن الأهل.", en:"Children aged 2 to 6 are welcome. Check your child's age in the parents' corner.", de:"Kinder von 2 bis 6 Jahren. Das Alter Ihres Kindes können Sie im Elternbereich prüfen."}},
  {q:{ar:"ما هي الرسوم وأوقات الدوام؟", en:"What are the fees and opening hours?", de:"Was kostet der Kindergarten und wann ist geöffnet?"}, a:{ar:"نعطيك كل التفاصيل عند التواصل أو الزيارة. راسلنا على واتساب.", en:"We give you all the details when you contact or visit us. Write to us on WhatsApp.", de:"Alle Einzelheiten nennen wir Ihnen beim Kontakt oder Besuch. Schreiben Sie uns auf WhatsApp."}},
  {q:{ar:"أين تقع الروضة؟", en:"Where is the kindergarten?", de:"Wo befindet sich der Kindergarten?"}, a:{ar:"المليحة، آخر شارع الـ16، دوار البلاط الجديد، مواجه مدرسة البلاط.", en:"Al-Maliha, end of 16th Street, New Balat Roundabout, opposite Al-Balat School.", de:"Al-Maliha, Ende der 16. Straße, Neuer Balat-Kreisverkehr, gegenüber der Balat-Schule."}},
  {q:{ar:"ماذا يتعلم الطفل في الروضة؟", en:"What does a child learn here?", de:"Was lernt ein Kind bei Ihnen?"}, a:{ar:"لعب وعربية وفنون وأرقام وعلوم وقيم، بأنشطة قصيرة ومتنوعة تناسب هذا العمر.", en:"Play, Arabic, arts, numbers, science and values, through short, varied activities suited to this age.", de:"Spielen, Arabisch, Kreatives, Zahlen, Natur und Werte, in kurzen, abwechslungsreichen Aktivitäten, passend zum Alter."}},
  {q:{ar:"هل يتعلم طفلي الحروف والأرقام؟", en:"Will my child learn letters and numbers?", de:"Lernt mein Kind Buchstaben und Zahlen?"}, a:{ar:"نعم، لكن باللعب والقصص والأناشيد وبخطوات هادئة تناسب كل طفل.", en:"Yes, but through play, stories and songs, in calm steps that suit each child.", de:"Ja, aber spielerisch, mit Geschichten und Liedern, in ruhigen Schritten, die zu jedem Kind passen."}},
  {q:{ar:"ماذا يحتاج طفلي في اليوم الأول؟", en:"What does my child need on the first day?", de:"Was braucht mein Kind am ersten Tag?"}, a:{ar:"انظر قائمة «حقيبة اليوم الأول» في ركن الأهل، واسألنا عن أي شيء آخر.", en:"See the “First-day bag” list in the parents' corner and ask us about anything else.", de:"Siehe die Liste «Tasche für den ersten Tag» im Elternbereich. Fragen Sie uns gern nach allem Weiteren."}},
  {q:{ar:"كيف أتابع تطور طفلي؟", en:"How do I follow my child's progress?", de:"Wie erfahre ich, wie sich mein Kind entwickelt?"}, a:{ar:"نبقيك على اطلاع بما يتعلمه طفلك، ونلتقي بالأهل دورياً لمناقشة تقدمه.", en:"We keep you informed about what your child learns and meet parents regularly to discuss progress.", de:"Wir halten Sie über das Lernen Ihres Kindes auf dem Laufenden und sprechen regelmäßig mit den Eltern über die Fortschritte."}},
  {q:{ar:"كيف أتواصل مع الروضة؟", en:"How can I reach the kindergarten?", de:"Wie erreiche ich den Kindergarten?"}, a:{ar:"عبر واتساب أو الهاتف أو بزيارة الروضة، وتجد الأرقام في قسم التواصل.", en:"By WhatsApp, phone or in person. You find the numbers in the contact section.", de:"Per WhatsApp, Telefon oder persönlich. Die Nummern finden Sie im Kontaktbereich."}}
];

/* ---------- language ---------- */
function applyLang(l){
  L = l;
  document.documentElement.lang = l;
  document.documentElement.dir = l === "ar" ? "rtl" : "ltr";
  document.body.classList.toggle("lat", l !== "ar");
  document.querySelectorAll("[data-en]").forEach(function(el){
    if(el.dataset.ar === undefined) el.dataset.ar = el.innerHTML;
    el.innerHTML = l === "ar" ? el.dataset.ar : (l === "de" ? (el.dataset.de || el.dataset.en) : el.dataset.en);
  });
  document.querySelectorAll("[data-en-aria]").forEach(function(el){
    var attr = el.tagName === "IMG" ? "alt" : "aria-label";
    if(el.dataset.arAria === undefined) el.dataset.arAria = el.getAttribute(attr) || "";
    el.setAttribute(attr, l === "ar" ? el.dataset.arAria : (l === "de" ? (el.dataset.deAria || el.dataset.enAria) : el.dataset.enAria));
  });
  var q = $("faqQ");
  if(q.dataset.arPh === undefined) q.dataset.arPh = q.placeholder;
  q.placeholder = l === "ar" ? q.dataset.arPh : (l === "de" ? q.dataset.dePh : q.dataset.enPh);
  document.querySelectorAll(".lang button").forEach(function(b){ b.setAttribute("aria-pressed", b.dataset.l === l ? "true" : "false"); });
  document.title = tr("روضة زهرة المدائن", "Zahrat Al-Madayn Kindergarten", "Kindergarten Zahrat Al-Madayn");
  $("h1").innerHTML = tr("روضة <em>زهرة</em> المدائن الخاصة", "Zahrat <em>Al-Madayn</em> Kindergarten", "Kindergarten <em>Zahrat</em> Al-Madayn");
  renderAll();
  store("zm-lang", l);
}
document.querySelectorAll(".lang button").forEach(function(b){ b.addEventListener("click", function(){ applyLang(b.dataset.l); }); });

/* ---------- theme, size, menu, scroll ---------- */
$("themeBtn").addEventListener("click", function(){
  var cur = document.documentElement.getAttribute("data-theme");
  if(!cur) cur = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  var next = cur === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next); store("zm-theme", next);
});
var SIZES = [1, 1.12, 1.25], sizeIdx = 0;
function setSize(i){ sizeIdx = i; document.documentElement.style.setProperty("--fs", SIZES[i]); store("zm-size", String(i)); }
$("sizeBtn").addEventListener("click", function(){ setSize((sizeIdx + 1) % SIZES.length); });
var nav = $("nav"), menuBtn = $("menuBtn");
menuBtn.addEventListener("click", function(){ var o = nav.classList.toggle("open"); menuBtn.setAttribute("aria-expanded", o ? "true" : "false"); });
nav.addEventListener("click", function(e){ if(e.target.tagName === "A"){ nav.classList.remove("open"); menuBtn.setAttribute("aria-expanded", "false"); } });
var toTop = $("toTop");
function onScroll(){
  var de = document.documentElement, max = de.scrollHeight - de.clientHeight, y = window.pageYOffset || de.scrollTop || 0;
  $("progBar").style.transform = "scaleX(" + (max > 0 ? Math.min(1, y / max) : 0) + ")";
  toTop.hidden = y < 700;
}
window.addEventListener("scroll", onScroll, {passive:true});
toTop.addEventListener("click", function(){ window.scrollTo({top:0, behavior:"smooth"}); });

/* ---------- links ---------- */
var waBase = "https://wa.me/" + CONFIG.whatsapp;
var mapUrl = CONFIG.mapUrl;
["waLink","mWa"].forEach(function(i){ $(i).href = waBase; });
["mapLink","mMap"].forEach(function(i){ $(i).href = mapUrl; });
$("phoneNum").textContent = CONFIG.phoneDisplay; $("footPhone").textContent = CONFIG.phoneDisplay;
function applySocial(){ [["fbLink","fbFoot","fbRow",CONFIG.facebook],["igLink","igFoot","igRow",CONFIG.instagram]].forEach(function(x){ $(x[0]).href = x[3]; $(x[1]).href = x[3]; $(x[1]).hidden = $(x[2]).hidden = !x[3]; }); document.querySelectorAll(".js-fb").forEach(function(a){ a.href = CONFIG.facebook || "#"; a.hidden = !CONFIG.facebook; }); document.querySelectorAll(".js-ig").forEach(function(a){ a.href = CONFIG.instagram || "#"; a.hidden = !CONFIG.instagram; }); $("follow").hidden = !(CONFIG.facebook || CONFIG.instagram); }
applySocial();
if(CONFIG.email){ $("mailTxt").textContent = CONFIG.email; $("mailRow").hidden = false; }
function renderHours(){ var h = CONFIG.hours && (CONFIG.hours[L] || CONFIG.hours.en || CONFIG.hours.ar); $("hoursRow").hidden = !h; if(h) $("hoursTxt").textContent = h; }
function copyText(text, done){
  function fallback(){
    var ta = document.createElement("textarea"); ta.value = text; ta.setAttribute("readonly", "");
    ta.style.position = "fixed"; ta.style.opacity = "0"; document.body.appendChild(ta); ta.select();
    var ok = false; try{ ok = document.execCommand("copy"); }catch(e){}
    document.body.removeChild(ta); done(ok);
  }
  if(navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(function(){ done(true); }, fallback); else fallback();
}
$("copyPhone").addEventListener("click", function(){
  var b = this;
  copyText(CONFIG.phoneDisplay.replace(/\s/g, ""), function(ok){
    b.textContent = ok ? tr("تم النسخ", "Copied", "Kopiert") : tr("انسخ الرقم يدوياً", "Copy it manually", "Bitte manuell kopieren");
    setTimeout(function(){ b.textContent = tr("انسخ الرقم", "Copy number", "Nummer kopieren"); }, 2000);
  });
});

/* ---------- flower ---------- */
var NS = "http://www.w3.org/2000/svg", pg = $("petals"), info = $("petalInfo"), areaButtons = $("areaButtons"), curPetal = -1, petalEls = [], petalTx = [], petalControls = [];
function renderPetals(){
  petalTx.forEach(function(tx, i){
    var label = T(AREAS[i].n);
    petalEls[i].setAttribute("aria-label", AREAS[i].n.ar + " / " + AREAS[i].n.en);
    petalEls[i].setAttribute("aria-pressed", String(curPetal === i));
    petalEls[i].classList.toggle("on", curPetal === i);
    petalControls[i].setAttribute("aria-pressed", String(curPetal === i));
    tx.textContent = label;
    tx.style.fontSize = label.length > 9 ? "11px" : "15px";
  });
  info.innerHTML = "";
  if(curPetal < 0){
    info.className = "petal-info is-intro";
    var intro = document.createElement("p");
    intro.className = "petal-intro";
    intro.lang = "ar"; intro.dir = "rtl";
    intro.textContent = "ستة مجالات تنمو معاً مثل بتلات الزهرة.";
    var introEn = document.createElement("p");
    introEn.className = "petal-intro learn-en";
    introEn.lang = "en";
    introEn.dir = "ltr";
    introEn.textContent = "Six areas grow together, like the petals of a flower.";
    info.append(intro, introEn);
    return;
  }
  info.className = "petal-info is-detail";
  var a = AREAS[curPetal];
  var heading = document.createElement("b");
  heading.className = "petal-title";
  var arName = document.createElement("span");
  arName.lang = "ar"; arName.dir = "rtl"; arName.textContent = a.n.ar;
  var enName = document.createElement("span");
  enName.className = "learn-en"; enName.lang = "en"; enName.dir = "ltr"; enName.textContent = a.n.en;
  heading.append(arName, enName);
  var descriptions = document.createElement("div");
  descriptions.className = "petal-descriptions";
  var arDescription = document.createElement("p");
  arDescription.lang = "ar"; arDescription.dir = "rtl"; arDescription.textContent = a.d.ar;
  var enDescription = document.createElement("p");
  enDescription.className = "learn-en"; enDescription.lang = "en"; enDescription.dir = "ltr"; enDescription.textContent = a.d.en;
  var ul = document.createElement("ul");
  a.a.forEach(function(item){
    var li = document.createElement("li");
    var arItem = document.createElement("span"); arItem.lang = "ar"; arItem.dir = "rtl"; arItem.textContent = item.ar;
    var enItem = document.createElement("span"); enItem.className = "learn-en"; enItem.lang = "en"; enItem.dir = "ltr"; enItem.textContent = item.en;
    li.append(arItem, enItem);
    ul.appendChild(li);
  });
  descriptions.append(arDescription, enDescription);
  info.append(heading, descriptions, ul);
}
function selectPetal(index){
  curPetal = index;
  renderPetals();
}
AREAS.forEach(function(a, i){
  var rot = i * 360 / AREAS.length, grp = document.createElementNS(NS, "g");
  grp.setAttribute("class", "petal" + (a.dk ? " dk" : "")); grp.setAttribute("tabindex", "0"); grp.setAttribute("role", "button"); grp.setAttribute("aria-pressed", "false"); grp.setAttribute("aria-label", a.n.ar + " / " + a.n.en);
  var e = document.createElementNS(NS, "ellipse");
  e.setAttribute("cx", 200); e.setAttribute("cy", 92); e.setAttribute("rx", 46); e.setAttribute("ry", 72); e.setAttribute("fill", a.c);
  e.setAttribute("transform", "rotate(" + rot + " 200 170)");
  var rad = rot * Math.PI / 180, tx = document.createElementNS(NS, "text");
  tx.setAttribute("x", 200 + 92 * Math.sin(rad)); tx.setAttribute("y", 170 - 92 * Math.cos(rad) + 5); tx.setAttribute("text-anchor", "middle");
  grp.append(e, tx); petalTx.push(tx); petalEls.push(grp);
  grp.addEventListener("keydown", function(ev){ if(ev.key === "Enter" || ev.key === " "){ ev.preventDefault(); selectPetal(i); } });
  pg.appendChild(grp);
  var control = document.createElement("button");
  control.type = "button";
  control.className = "area-button";
  control.setAttribute("aria-pressed", "false");
  control.style.setProperty("--area-color", a.c);
  var arLabel = document.createElement("span");
  arLabel.lang = "ar"; arLabel.dir = "rtl"; arLabel.textContent = a.n.ar;
  var enLabel = document.createElement("span");
  enLabel.lang = "en"; enLabel.dir = "ltr"; enLabel.textContent = a.n.en;
  control.append(arLabel, enLabel);
  control.addEventListener("click", function(){ selectPetal(i); });
  areaButtons.appendChild(control);
  petalControls.push(control);
});
pg.ownerSVGElement.addEventListener("click", function(ev){
  var svg = pg.ownerSVGElement, point = svg.createSVGPoint();
  point.x = ev.clientX; point.y = ev.clientY;
  var local = point.matrixTransform(svg.getScreenCTM().inverse());
  var dx = local.x - 200, dy = 170 - local.y, distance = Math.hypot(dx, dy);
  if(distance < 50 || distance > 140) return;
  var angle = Math.atan2(dx, dy) * 180 / Math.PI;
  var index = Math.round(((angle % 360) + 360) % 360 / (360 / AREAS.length)) % AREAS.length;
  selectPetal(index);
});
renderPetals();

/* ---------- news ---------- */
function newsItems(){
  var arr = DYN.settings.hideDefaultNews ? [] : CONFIG.news.slice();
  DYN.news.slice().sort(byNew).forEach(function(n){
    arr.unshift({tag: dyn(sOf(n.tag, 30) || "خبر"), title: dyn(sOf(n.title, 120)), text: dyn(sOf(n.text, 1500)), url: blobUrl(n.asset), cta: CONFIG.news[0].cta});
  });
  return arr;
}
function renderNews(){
  var box = $("newsList"); box.innerHTML = "";
  newsItems().forEach(function(n){
    var c = document.createElement("article"); c.className = "ncard";
    var src = n.url || (n.img ? ASSETS[n.img] : "");
    if(src){
      var pic = document.createElement("button"); pic.type = "button"; pic.className = "pic";
      var im = document.createElement("img"); im.src = src; im.alt = T(n.title); im.loading = "lazy"; pic.appendChild(im);
      pic.addEventListener("click", function(){ openLb(src, T(n.title), pic); });
      c.appendChild(pic);
    } else c.style.gridTemplateColumns = "1fr";
    var tx = document.createElement("div"); tx.className = "tx";
    var tg = document.createElement("span"); tg.className = "tag"; tg.textContent = T(n.tag);
    var h = document.createElement("h3"); h.textContent = T(n.title);
    var p = document.createElement("p"); p.textContent = T(n.text);
    var a = document.createElement("a"); a.className = "btn sun small"; a.href = "#register"; a.textContent = T(n.cta);
    tx.append(tg, h, p, a); c.appendChild(tx); box.appendChild(c);
  });
}

/* ---------- lightbox ---------- */
var lb = $("lb"), lbImg = $("lbImg"), lastFocus = null;
function openLb(key, alt, from){ lastFocus = from; lbImg.src = ASSETS[key] || key; lbImg.alt = alt || ""; lb.hidden = false; $("lbX").focus(); }
function closeLb(){ lb.hidden = true; lbImg.removeAttribute("src"); if(lastFocus) lastFocus.focus(); }
document.querySelectorAll(".gal button").forEach(function(b){ b.addEventListener("click", function(){ openLb(b.dataset.full, b.dataset.alt, b); }); });
$("lbX").addEventListener("click", closeLb);
lb.addEventListener("click", function(e){ if(e.target === lb) closeLb(); });
document.addEventListener("keydown", function(e){ if(e.key === "Escape" && !lb.hidden) closeLb(); });

/* ---------- checklists ---------- */
var CK = {Docs: {items: DOCS, key: "zm-ck-docs"}, Bag: {items: BAG, key: "zm-ck-bag"}};
Object.keys(CK).forEach(function(k){
  var raw = store(CK[k].key), arr = [];
  try{ arr = JSON.parse(raw) || []; }catch(e){ arr = []; }
  CK[k].on = arr;
});
function renderCk(k){
  var c = CK[k], ul = $("ck" + k); ul.innerHTML = "";
  c.items.forEach(function(it, i){
    var li = document.createElement("li"), lab = document.createElement("label"), inp = document.createElement("input");
    inp.type = "checkbox"; inp.id = "ck" + k + i; inp.checked = c.on.indexOf(i) >= 0;
    var bx = document.createElement("span"); bx.className = "bx"; bx.setAttribute("aria-hidden", "true");
    var tx = document.createElement("span"); tx.className = "tx"; tx.textContent = T(it);
    inp.addEventListener("change", function(){
      c.on = c.on.filter(function(x){ return x !== i; }); if(inp.checked) c.on.push(i);
      store(c.key, JSON.stringify(c.on)); meter(k);
    });
    lab.append(inp, bx, tx); li.appendChild(lab); ul.appendChild(li);
  });
  meter(k);
}
function meter(k){
  var c = CK[k], n = c.on.length, t = c.items.length;
  $("m" + k).textContent = tr(n + " من " + t + " جاهزة", n + " of " + t + " ready", n + " von " + t + " bereit");
  $("b" + k).style.width = (100 * n / t) + "%";
}

/* ---------- faq ---------- */
function renderFaq(){
  var q = $("faqQ").value.trim().toLowerCase(), list = $("faqList"); list.innerHTML = ""; var shown = 0;
  FAQ.forEach(function(f){
    var qq = T(f.q), aa = T(f.a);
    if(q && (qq + " " + aa).toLowerCase().indexOf(q) < 0) return;
    var d = document.createElement("details"), s = document.createElement("summary"), a = document.createElement("div");
    s.textContent = qq; a.className = "a"; a.textContent = aa; d.append(s, a); list.appendChild(d); shown++;
  });
  var em = $("faqEmpty"); em.hidden = shown > 0;
  if(!shown){ em.innerHTML = ""; em.append(tr("لم نجد سؤالاً مطابقاً. ", "No matching question. ", "Keine passende Frage gefunden. ")); var a = document.createElement("a"); a.href = waBase; a.target = "_blank"; a.rel = "noopener"; a.textContent = tr("اسألنا مباشرة على واتساب.", "Ask us directly on WhatsApp.", "Fragen Sie uns direkt auf WhatsApp."); em.appendChild(a); }
}
$("faqQ").addEventListener("input", renderFaq);

/* ---------- age ---------- */
function parseD(s){ var p = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || ""); return p ? new Date(+p[1], +p[2] - 1, +p[3]) : null; }
function pad(n){ return ("0" + n).slice(-2); }
function fmtD(d){ return pad(d.getDate()) + "." + pad(d.getMonth() + 1) + "." + d.getFullYear(); }
function arUnit(n, one, two, few, many){ return n === 1 ? one : (n === 2 ? two : (n <= 10 ? few : (many || one))); }
function ageStr(y, m){
  var p = [];
  if(L === "ar"){
    if(y > 0) p.push(y + " " + arUnit(y, "سنة", "سنتان", "سنوات"));
    if(m > 0) p.push(m + " " + arUnit(m, "شهر", "شهران", "أشهر", "شهراً"));
    return p.join(" و") || "0";
  }
  if(L === "de"){ if(y > 0) p.push(y + (y === 1 ? " Jahr" : " Jahre")); if(m > 0) p.push(m + (m === 1 ? " Monat" : " Monate")); return p.join(" und ") || "0"; }
  if(y > 0) p.push(y + (y === 1 ? " year" : " years")); if(m > 0) p.push(m + (m === 1 ? " month" : " months")); return p.join(" and ") || "0";
}
function ageInfo(str){
  var b = parseD(str); if(!b) return null;
  var now = new Date(), t = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  if(b > t) return {cls:"no", short:tr("هذا التاريخ في المستقبل.", "This date is in the future.", "Dieses Datum liegt in der Zukunft."), full:tr("هذا التاريخ في المستقبل.", "This date is in the future.", "Dieses Datum liegt in der Zukunft."), ok:false, bad:true};
  var y = t.getFullYear() - b.getFullYear(), m = t.getMonth() - b.getMonth();
  if(t.getDate() < b.getDate()) m--; if(m < 0){ y--; m += 12; }
  if(y > 12) return {cls:"no", short:tr("يرجى التأكد من التاريخ.", "Please check the date.", "Bitte Datum prüfen."), full:tr("يرجى التأكد من التاريخ.", "Please check the date.", "Bitte Datum prüfen."), ok:false, bad:true};
  var a = ageStr(y, m), min = CONFIG.minAge, max = CONFIG.maxAge;
  if(y >= min && y <= max){
    return {cls:"ok", ok:true, short:tr("العمر: " + a, "Age: " + a, "Alter: " + a),
      full:tr("عمر طفلك: " + a + ". هذا العمر ضمن الفئة التي نستقبلها (" + min + " إلى " + max + " سنوات).", "Your child is " + a + " old. That is within the ages we accept (" + min + " to " + max + ").", "Ihr Kind ist " + a + " alt. Das liegt im Aufnahmealter (" + min + " bis " + max + " Jahre).")};
  }
  if(y < min){
    var s = fmtD(new Date(b.getFullYear() + min, b.getMonth(), b.getDate()));
    return {cls:"wait", ok:false, short:tr("العمر: " + a + ". يبلغ " + min + " سنوات بتاريخ " + s + ".", "Age: " + a + ". Turns " + min + " on " + s + ".", "Alter: " + a + ". Wird am " + s + " " + min + " Jahre alt."),
      full:tr("عمر طفلك: " + a + ". يبلغ " + min + " سنوات بتاريخ " + s + ". تواصل معنا لنخبرك بالموعد المناسب.", "Your child is " + a + " old and turns " + min + " on " + s + ". Contact us and we will tell you the right time.", "Ihr Kind ist " + a + " alt und wird am " + s + " " + min + " Jahre alt. Melden Sie sich, wir nennen Ihnen den passenden Zeitpunkt.")};
  }
  return {cls:"no", ok:false, short:tr("العمر: " + a + ". أعلى من الفئة المعتادة.", "Age: " + a + ". Above our usual range.", "Alter: " + a + ". Über unserem üblichen Alter."),
    full:tr("عمر طفلك: " + a + ". هذا أعلى من الفئة المعتادة. تواصل معنا لنرى الخيارات.", "Your child is " + a + " old. This is above our usual age range. Contact us and we will look at the options.", "Ihr Kind ist " + a + " alt. Das liegt über unserem üblichen Alter. Melden Sie sich, wir prüfen die Möglichkeiten.")};
}
function renderAge(){
  var r = ageInfo($("toolBirth").value), box = $("toolRes");
  box.className = "ares" + (r ? " " + r.cls : ""); box.textContent = r ? r.full : ""; $("toolGo").hidden = !(r && r.ok);
  var h = ageInfo($("fBirth").value), hn = $("ageHint");
  hn.className = "hint" + (h ? " " + h.cls : ""); hn.textContent = h ? h.short : "";
}
$("toolBirth").addEventListener("input", renderAge);
$("fBirth").addEventListener("input", renderAge);
$("toolGo").addEventListener("click", function(){ $("fBirth").value = $("toolBirth").value; renderAge(); });
(function(){
  var d = new Date(), today = d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
  $("fBirth").max = today; $("toolBirth").max = today; $("fDate").min = today;
})();

/* ---------- form ---------- */
var form = $("regForm");
function kind(){ return $("kVisit").checked ? "visit" : "reg"; }
function syncKind(){ $("dateFld").hidden = kind() !== "visit"; }
Array.prototype.forEach.call(form.elements["kind"], function(r){ r.addEventListener("change", syncKind); });
function pickVisit(){ $("kVisit").checked = true; syncKind(); }
document.querySelectorAll("[data-kind=visit]").forEach(function(a){ a.addEventListener("click", pickVisit); });
$("visitCta").addEventListener("click", pickVisit);
var ERR = [["eParent","fParent"],["eChild","fChild"],["eBirth","fBirth"],["ePhone","fPhone"],["eDate","fDate"]];
function setErr(id, field, msg){ $(id).textContent = msg || ""; if(msg) $(field).setAttribute("aria-invalid", "true"); else $(field).removeAttribute("aria-invalid"); return !msg; }
function clearErrors(){ ERR.forEach(function(p){ setErr(p[0], p[1], ""); }); }
form.addEventListener("submit", function(e){
  e.preventDefault();
  var v = {parent:$("fParent").value.trim(), child:$("fChild").value.trim(), birth:$("fBirth").value, phone:$("fPhone").value.trim(), date:$("fDate").value, how:$("fHow").value, note:$("fNote").value.trim()};
  var req = tr("هذا الحقل مطلوب.", "This field is required.", "Dieses Feld ist erforderlich."), ok = true, ai = ageInfo(v.birth);
  ok = setErr("eParent", "fParent", v.parent ? "" : req) && ok;
  ok = setErr("eChild", "fChild", v.child ? "" : req) && ok;
  var birthErr = !v.birth ? req : ((ai && ai.bad) ? ai.short : "");
  ok = setErr("eBirth", "fBirth", birthErr) && ok;
  ok = setErr("ePhone", "fPhone", /^\+?[0-9\s\-]{7,16}$/.test(v.phone) ? "" : tr("أدخل رقم هاتف صحيحاً.", "Enter a valid phone number.", "Bitte eine gültige Telefonnummer eingeben.")) && ok;
  var visit = kind() === "visit";
  ok = setErr("eDate", "fDate", (!visit || v.date) ? "" : tr("اختر يوم الزيارة.", "Choose a visit day.", "Bitte einen Besuchstag wählen.")) && ok;
  if(!ok){ var bad = form.querySelector("[aria-invalid=true]"); if(bad) bad.focus(); return; }
  var b = parseD(v.birth), now = new Date(), yy = now.getFullYear() - b.getFullYear(), mm = now.getMonth() - b.getMonth();
  if(now.getDate() < b.getDate()) mm--; if(mm < 0){ yy--; mm += 12; }
  var lines = ["السلام عليكم، أرغب في " + (visit ? "حجز زيارة إلى" : "تسجيل طفلي في") + " روضة زهرة المدائن.",
    "ولي الأمر: " + v.parent, "اسم الطفل: " + v.child, "تاريخ الميلاد: " + fmtD(b) + " (" + yy + " سنوات و" + mm + " أشهر)", "الهاتف: " + v.phone];
  if(visit) lines.push("يوم الزيارة المفضل: " + fmtD(parseD(v.date)));
  if(v.how) lines.push("سمعت عنكم عبر: " + v.how);
  if(v.note) lines.push("ملاحظات: " + v.note);
  var text = lines.join("\n");
  $("msg").textContent = text; $("waSend").href = waBase + "?text=" + encodeURIComponent(text);
  $("copied").textContent = ""; $("res").hidden = false; $("res").scrollIntoView({behavior:"smooth", block:"nearest"});
});
$("copyMsg").addEventListener("click", function(){
  copyText($("msg").textContent, function(ok){ $("copied").textContent = ok ? tr("تم نسخ الرسالة.", "Message copied.", "Nachricht kopiert.") : tr("تعذّر النسخ. حدّد النص وانسخه يدوياً.", "Could not copy. Select the text and copy it manually.", "Kopieren fehlgeschlagen. Bitte Text markieren und manuell kopieren."); });
});

/* ---------- render all and start ---------- */
function renderAll(){ renderPetals(); renderNews(); renderCk("Docs"); renderCk("Bag"); renderFaq(); renderAge(); renderHours(); clearErrors(); onScroll(); }
var st = store("zm-theme"); if(st === "dark" || st === "light") document.documentElement.setAttribute("data-theme", st);
var ss = parseInt(store("zm-size"), 10); if(ss >= 0 && ss < SIZES.length) setSize(ss);
syncKind();
var sl = store("zm-lang"); applyLang(sl === "en" || sl === "de" ? sl : "ar");

/* ===== المحتوى الديناميكي ولوحة التحكم ===== */
var DEF = {fb: CONFIG.facebook, ig: CONFIG.instagram, phone: CONFIG.phoneDisplay, wa: CONFIG.whatsapp, hours: CONFIG.hours};
var FILE_RE = /^[0-9a-f]{32}\.(jpg|png|webp|gif|mp4|webm)$/;
function blobUrl(f){ return (typeof f === "string" && FILE_RE.test(f)) ? API_BASE + "/api/assets/" + f : ""; }
function sOf(v, n){ return typeof v === "string" ? v.slice(0, n) : ""; }
function byNew(a, b){ return (b.ts || 0) - (a.ts || 0); }
function dyn(s){ return {ar: s}; }

function applyContact(){
  var s = DYN.settings;
  var wa = String(s.whatsapp || "").replace(/\D/g, ""); if(wa.length < 8 || wa.length > 15) wa = DEF.wa;
  waBase = "https://wa.me/" + wa; ["waLink","mWa"].forEach(function(i){ $(i).href = waBase; });
  CONFIG.phoneDisplay = sOf(s.phone, 30) || DEF.phone; $("phoneNum").textContent = CONFIG.phoneDisplay; $("footPhone").textContent = CONFIG.phoneDisplay;
  var fb = sOf(s.facebook, 300), ig = sOf(s.instagram, 300); CONFIG.facebook = /^https:\/\//.test(fb) ? fb : DEF.fb; CONFIG.instagram = /^https:\/\//.test(ig) ? ig : DEF.ig; applySocial();
  CONFIG.email = sOf(s.email, 120); $("mailRow").hidden = !CONFIG.email; if(CONFIG.email) $("mailTxt").textContent = CONFIG.email;
  var hh = sOf(s.hours, 200); CONFIG.hours = hh ? {ar: hh, en: hh, de: hh} : DEF.hours;
  var an = sOf(s.announce, 200); $("annc").hidden = !an; $("annc").textContent = an;
}

function renderGallery(){
  var box = $("galBox"), s = DYN.settings;
  box.querySelectorAll(".dyn").forEach(function(n){ n.remove(); });
  box.querySelectorAll(".def").forEach(function(n){ n.hidden = !!s.hideDefaultGallery; });
  var imgs = DYN.gallery.filter(function(g){ return g.kind !== "video" && blobUrl(g.asset); }).sort(byNew);
  imgs.forEach(function(g){
    var cap = sOf(g.caption, 120), url = blobUrl(g.asset);
    var b = document.createElement("button"); b.type = "button"; b.className = "dyn";
    var im = document.createElement("img"); im.src = url; im.alt = cap; im.loading = "lazy"; b.appendChild(im);
    if(cap){ var sp = document.createElement("span"); sp.className = "cap"; sp.textContent = cap; b.appendChild(sp); }
    b.addEventListener("click", function(){ openLb(url, cap, b); });
    box.insertBefore(b, box.firstChild);
  });
  /* الترتيب: الأحدث أولاً، لذلك نعيد الإدراج بترتيب معكوس */
  var dn = Array.prototype.slice.call(box.querySelectorAll(".dyn")); dn.reverse().forEach(function(n){ box.insertBefore(n, box.firstChild); });
  var vids = DYN.gallery.filter(function(g){ return g.kind === "video" && blobUrl(g.asset); }).sort(byNew);
  var vb = $("vidBox"); vb.innerHTML = "";
  vids.forEach(function(g){
    var f = document.createElement("figure"), v = document.createElement("video");
    v.controls = true; v.preload = "metadata"; v.playsInline = true; v.src = blobUrl(g.asset); f.appendChild(v);
    var cap = sOf(g.caption, 120); if(cap){ var c = document.createElement("figcaption"); c.textContent = cap; f.appendChild(c); }
    vb.appendChild(f);
  });
  $("videos").hidden = !vids.length;
}

async function startDyn(){
  try{
    var r = await fetch(API_BASE + "/api/content", {cache: "no-store"});
    if(!r.ok) throw new Error("Dynamic content request failed: HTTP " + r.status);
    var d = await r.json();
    DYN.settings = d.settings || {}; DYN.gallery = d.gallery || []; DYN.news = d.news || [];
    applyContact(); renderHours(); renderNews(); renderGallery();
  }catch(e){ console.error("Could not load dynamic kindergarten content.", e); }
}


/* ---------- follow us ---------- */
(function(){
  var ft = $("followToast");
  function showToast(){ if(!store("zm-follow") && (CONFIG.facebook || CONFIG.instagram)) ft.hidden = false; }
  setTimeout(showToast, 8000);
  function dismiss(){ ft.hidden = true; store("zm-follow", "1"); }
  $("followX").addEventListener("click", dismiss);
  ft.querySelectorAll("a").forEach(function(a){ a.addEventListener("click", dismiss); });
})();
startDyn();
