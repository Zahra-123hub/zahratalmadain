/* Buchhaltung (المحاسبة): overview, fees, payroll, monthly and weekly sheets.
   Loaded before admin.js; uses its helpers (h, request, setMsg, errText, twoStep, money, esc, MONTHS_AR). */

var ACC_CURRENCIES = ["SYP", "USD"];  // the Syrian pound is the main currency
var ACC_CURRENCY_NAME = {USD:"الدولار الأمريكي (USD)", SYP:"الليرة السورية (SYP)"};
var ACC_VIEWER = {name:"", role:""};

/* Names typed before are offered as suggestions (<datalist>), so nobody has to retype them. */
function accEnsureLists(){
  ["acc-persons", "acc-payers", "acc-staff"].forEach(function(id){
    if(!document.getElementById(id)){ var list = document.createElement("datalist"); list.id = id; document.body.appendChild(list); }
  });
}
function accFill(id, names){
  var list = document.getElementById(id);
  if(!list) return;
  list.innerHTML = "";
  (names || []).forEach(function(name){ var option = document.createElement("option"); option.value = name; list.appendChild(option); });
}
async function accLoadNames(){
  accEnsureLists();
  try{
    var names = await request("/api/admin/accounting/names");
    accFill("acc-persons", names.persons); accFill("acc-payers", names.payers); accFill("acc-staff", names.staff);
  }catch(e){ /* suggestions are optional */ }
}
function accField(label, input){ return h("label", {class:"a-field"}, [h("span", {text:label}), input]); }
function accSelect(options, value){
  var el = h("select", {});
  options.forEach(function(o){ el.appendChild(new Option(o[1], o[0])); });
  el.value = value;
  return el;
}
/* Exact money sums: amounts from the server are texts with two decimals; they are compared and added as whole cents (no floating point). */
function accCents(text){
  var s = String(text == null || text === "" ? "0" : text), neg = s.charAt(0) === "-";
  var parts = s.replace(/^[-+]/, "").split(".");
  var cents = BigInt(parts[0] || "0") * 100n + BigInt(((parts[1] || "") + "00").slice(0, 2));
  return neg ? -cents : cents;
}
/* Asks for today's exchange rate (pounds for one dollar) and saves it; used the first time a conversion needs it. */
async function accAskRate(current){
  var text = window.prompt(current ? "سعر الصرف الحالي: 1 دولار = " + current + " ليرة. اكتب السعر الجديد:" : "لا يوجد سعر صرف محفوظ. اكتب كم ليرة سورية تساوي 1 دولار اليوم (مثال: 13000):", current || "");
  if(text === null) throw fail("لم يُحدَّد سعر الصرف.");
  text = text.trim().replace(/[٠-٩]/g, function(d){ return String(d.charCodeAt(0) - 1632); }).replace(",", ".");
  return request("/api/admin/accounting/rates", {method:"PUT", body:JSON.stringify({effective_date:localToday(), syp_per_usd:text})});
}
/* The server converts the typed amounts exactly (decimal arithmetic, half a cent up) with the current rate. */
async function accConvertMany(values, source, target){
  var send = function(){ return request("/api/admin/accounting/convert", {method:"POST", body:JSON.stringify({amounts:values, source:source, target:target})}); };
  try{ return await send(); }
  catch(error){
    if(String(error.message).indexOf("سعر صرف") === -1) throw error;
    await accAskRate("");
    return send();
  }
}
/* Switching the currency of a form converts the amounts already typed in it. Switching back restores exactly what
   was typed (an amount that was not touched meanwhile is never converted twice), so nothing drifts. */
function accLinkCurrency(select, inputs, notice){
  var current = select.value;
  var origin = new Map();  // input -> {cur: currency it was typed in, text: what was typed, shown: what the conversion put there}
  function fire(input){ input.dispatchEvent(new Event("input", {bubbles:true})); }
  select.addEventListener("change", async function(){
    var target = select.value, source = current;
    if(target === source) return;
    try{
      var filled = inputs.filter(function(i){ return i.value !== ""; });
      var restore = [], change = [];
      filled.forEach(function(i){ var o = origin.get(i); if(o && o.shown === i.value && o.cur === target) restore.push(i); else change.push(i); });
      var done = change.length ? await accConvertMany(change.map(function(i){ return i.value; }), source, target) : null;
      restore.forEach(function(i){ i.value = origin.get(i).text; origin.delete(i); fire(i); });
      change.forEach(function(i, k){ origin.set(i, {cur:source, text:i.value, shown:done.amounts[k]}); i.value = done.amounts[k]; fire(i); });
      current = target;
      if(notice && done){
        setMsg(notice, "حُوِّلت المبالغ من " + source + " إلى " + target + " بسعر 1 دولار = " + done.rate + " ليرة (" + (done.source === "auto" ? "سعر اليوم تلقائياً من الإنترنت" : "السعر المحفوظ") + ")." +
          (done.stale ? " تنبيه: تعذّر جلب سعر اليوم فاستُعمل آخر سعر محفوظ بتاريخ " + done.rate_date + "." : "") + " ", done.stale ? "err" : "ok");
        notice.appendChild(h("button", {type:"button", class:"a-btn ghost", text:"استعمال سعر آخر", onclick:async function(){
          try{ var saved = await accAskRate(done.rate); setMsg(notice, "السعر الجديد: 1 دولار = " + saved.current.rate + " ليرة (يُستعمل في التحويلات القادمة).", "ok"); }
          catch(error){ setMsg(notice, errText(error), "err"); }
        }}));
      }
    }catch(error){
      select.value = current;  // the conversion did not happen: the form stays as it was
      if(notice) setMsg(notice, errText(error), "err");
    }
  });
  select._accSync = function(){ current = select.value; origin.clear(); };  // after a program sets the currency itself
}
function accNumber(value, extra){ return h("input", Object.assign({type:"number", min:"0", step:"0.01", inputmode:"decimal", value:value === undefined || value === null ? "" : value}, extra || {})); }
function accMonths(withAll){ return (withAll ? [["", "كل الأشهر"]] : []).concat(MONTHS_AR.map(function(n, i){ return [String(i + 1), n]; })); }
function accCurrencyOptions(withAll){ return (withAll ? [["", "كل العملات"]] : []).concat([["SYP", "ليرة سورية (SYP)"], ["USD", "دولار أمريكي (USD)"]]); }

/* Printable A4 landscape RTL page: header with logo, even columns, tall rows to write in,
   highlighted totals and the two signature fields. `parts` = [{html, cols?, ...}]. */
function accPrint(title, subtitle, parts, msgEl){
  /* Black and white on purpose: no filled areas, no colours, thin lines, so a print uses very little ink. */
  var css = "@page{size:A4 landscape;margin:8mm}*{box-sizing:border-box}html{-webkit-print-color-adjust:economy;print-color-adjust:economy}" +
    "body{font-family:Almarai,'Segoe UI',Tahoma,sans-serif;color:#000;background:#fff;margin:0;font-size:12pt;line-height:1.35}" +
    "section{page-break-after:always;padding:0}section:last-child{page-break-after:auto}" +
    ".top{display:flex;align-items:center;gap:14px;border-bottom:1.5px solid #000;padding-bottom:5px;margin-bottom:6px}" +
    ".top img{width:50px;height:50px;object-fit:contain;filter:grayscale(1) contrast(1.2)}.top .t{flex:1;text-align:center}.top h1{margin:0;font-size:19pt;color:#000}.top h2{margin:2px 0 0;font-size:15pt}" +
    ".top .spacer{width:50px}.meta{display:flex;justify-content:center;gap:10px;flex-wrap:wrap;margin:0 0 6px}" +
    ".meta span{border:1px solid #000;border-radius:999px;padding:2px 14px;font-weight:700;font-size:11pt}" +
    "table{width:100%;border-collapse:collapse;table-layout:fixed}thead{display:table-header-group}tr{page-break-inside:avoid}" +
    "th,td{border:1px solid #000;padding:4px 7px;text-align:center;vertical-align:middle;overflow-wrap:break-word}td.n{white-space:nowrap}" +
    "th{font-weight:800;font-size:11pt;padding:6px 5px;border-bottom:2px solid #000}td{height:7mm;font-size:11.5pt}" +
    "td.l{text-align:right}td.l:first-child{font-weight:700}" +
    "tfoot{display:table-row-group}tfoot td{font-weight:800;border-top:2px solid #000;height:7mm;font-size:12pt;white-space:nowrap}" +
    ".due{font-weight:800;text-decoration:underline}" +
    ".sign{display:flex;gap:70px;margin-top:10px;page-break-inside:avoid}.sign>div{flex:1;text-align:center}.sign b{display:block;font-size:12pt;margin-bottom:12px}" +
    ".sign span{display:block;border-top:1px solid #000;padding-top:3px;min-height:20px;font-weight:700}.sign i{display:block;margin-top:6px;font-style:normal}" +
    "footer{margin-top:3px;font-size:8.5pt;color:#000;text-align:left}";
  var sign = "<div class='sign'><div><b>توقيع المحاسب</b><span>" + esc(ACC_VIEWER.role === "accountant" ? ACC_VIEWER.name : "") + "</span><i>التاريخ: ____ / ____ / ________</i></div>" +
    "<div><b>توقيع الإدارة</b><span></span><i>التاريخ: ____ / ____ / ________</i></div></div>";
  var today = new Date().toLocaleDateString("ar-SY");
  var logo = new URL("../images/logo.png?v=2", window.location.href).href;
  var html = "<!doctype html><html lang='ar' dir='rtl'><head><meta charset='utf-8'><title>" + esc(title) + "</title>" +
    "<link href='https://fonts.googleapis.com/css2?family=Almarai:wght@400;700;800&display=swap' rel='stylesheet'><style>" + css + "</style></head><body>" +
    parts.map(function(part){
      var table = part.html;
      if(part.cols) table = table.replace("<table>", "<table><colgroup>" + part.cols.map(function(w){ return "<col style='width:" + w + "%'>"; }).join("") + "</colgroup>");
      return "<section><div class='top'><img src='" + esc(logo) + "' alt=''><div class='t'><h1>روضة زهرة المدائن</h1><h2>" + esc(title) + "</h2></div><div class='spacer'></div></div>" +
        "<div class='meta'>" + subtitle(part).split("|").map(function(chunk){ return "<span>" + chunk.replace(/&nbsp;/g, " ").trim() + "</span>"; }).join("") + "</div>" +
        table + sign + "<footer>طُبع بتاريخ " + esc(today) + "</footer></section>";
    }).join("") +
    "</body></html>";
  var w = window.open("", "_blank");
  if(!w){ if(msgEl) setMsg(msgEl, "اسمح بالنوافذ المنبثقة لتصدير PDF.", "err"); return; }
  w.document.write(html);
  w.document.close();
  function printWhenReady(){
    (w.document.fonts ? w.document.fonts.ready : Promise.resolve()).then(function(){ setTimeout(function(){ w.focus(); w.print(); }, 300); });
  }
  if(w.document.readyState === "complete") printWhenReady(); else w.addEventListener("load", printWhenReady);
}
/* Before a payroll or monthly sheet is exported, every employee with a saved salary gets this month's row automatically. */
async function accFillSavedSalaries(year, month, codes, msgEl){
  if(!month) return 0;
  var created = 0;
  for(var i = 0; i < codes.length; i++){
    var res = await request("/api/admin/accounting/salaries/generate", {method:"POST", body:JSON.stringify({year:Number(year), month:Number(month), currency:codes[i]})});
    created += res.created;
  }
  if(created && msgEl) setMsg(msgEl, "أُضيفت تلقائياً رواتب " + created + " موظف من الرواتب المحفوظة.", "ok");
  return created;
}
function accTh(list){ return "<tr>" + list.map(function(t){ return "<th>" + t + "</th>"; }).join("") + "</tr>"; }

/* ---------------------------------------------------------------- shell */
function tabAccounting(){
  var sub = ACC_SUB || "overview";
  var panel = h("div", {});
  var nav = h("div", {class:"a-subnav", role:"tablist"});
  var SUBS = [["overview","نظرة عامة"], ["fees","اشتراكات الأطفال"], ["salaries","الرواتب"], ["staff","الموظفون"], ["day","الجدول اليومي"], ["week","الجدول الأسبوعي"], ["month","الجدول الشهري"]];
  function draw(){
    nav.innerHTML = "";
    SUBS.forEach(function(entry){
      nav.appendChild(h("button", {type:"button", role:"tab", "aria-selected":String(sub === entry[0]), text:entry[1], onclick:function(){ sub = ACC_SUB = entry[0]; draw(); }}));
    });
    panel.innerHTML = "";
    panel.appendChild(sub === "fees" ? tabFees() : sub === "salaries" ? tabSalaries() : sub === "staff" ? tabEmployees() : sub === "month" ? tabSheet("month") : sub === "week" ? tabSheet("week") : sub === "day" ? tabSheet("day") : tabOverview());
  }
  request("/api/admin/fees/me").then(function(me){ ACC_VIEWER = me; }, function(){});
  accLoadNames();
  draw();
  fill = null;
  return h("section", {}, [nav, panel]);
}
var ACC_SUB = "";

/* ------------------------------------------------------------- overview */
function tabOverview(){
  var now = new Date();
  var year = h("input", {type:"number", min:"2000", max:"2100", value:String(now.getFullYear())});
  var currencySel = accSelect(accCurrencyOptions(false), "SYP");  // the Syrian pound first; switch to see the other currency
  var body = h("div", {});
  var msg = h("div", {class:"a-msg", role:"status"});
  year.addEventListener("change", load);
  currencySel.addEventListener("change", load);

  function chart(series){
    var max = Math.max.apply(null, series.map(function(s){ return Math.max(Number(s.income), Number(s.expense)); }).concat([1]));
    var W = 720, H = 220, base = H - 30, band = (W - 20) / 12, bar = Math.max(6, band / 2 - 4);
    var svg = ['<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="الواردات والمصروفات الشهرية" style="width:100%;height:auto;direction:ltr">'];
    series.forEach(function(s, i){
      var x = 10 + i * band;
      var hi = Math.round((Number(s.income) / max) * (base - 14)), he = Math.round((Number(s.expense) / max) * (base - 14));
      svg.push('<rect x="' + (x + 2) + '" y="' + (base - hi) + '" width="' + bar + '" height="' + hi + '" rx="3" fill="#7DC243"><title>' + esc(MONTHS_AR[i]) + " – واردات: " + money(s.income) + '</title></rect>');
      svg.push('<rect x="' + (x + 4 + bar) + '" y="' + (base - he) + '" width="' + bar + '" height="' + he + '" rx="3" fill="#E0403D"><title>' + esc(MONTHS_AR[i]) + " – مصروفات: " + money(s.expense) + '</title></rect>');
      svg.push('<text x="' + (x + band / 2) + '" y="' + (H - 12) + '" font-size="11" text-anchor="middle" fill="currentColor">' + (i + 1) + '</text>');
    });
    svg.push('<line x1="6" y1="' + base + '" x2="' + (W - 6) + '" y2="' + base + '" stroke="currentColor" opacity=".35"/></svg>');
    var box = document.createElement("div");
    box.className = "a-chart";
    box.innerHTML = svg.join("");
    return box;
  }

  async function load(){
    body.innerHTML = "";
    try{
      var data = await request("/api/admin/accounting/overview?year=" + encodeURIComponent(year.value));
      var review = data.review || {fees:0, salaries:0};
      var cash = {};
      try{ cash = await request("/api/admin/accounting/cash"); }catch(e){ /* the rest of the overview still works */ }
      if(review.fees || review.salaries){
        body.appendChild(h("div", {class:"a-card a-review-note"}, [h("strong", {text:"يوجد " + review.fees + " سطر اشتراكات و" + review.salaries + " سطر رواتب يحتاج إلى مراجعة."}),
          h("p", {class:"hint", text:"الأسطر المميّزة بالأصفر مستوردة من الأوراق وفيها خانة غير واضحة. افتحها وصحّحها ثم اضغط «تمت المراجعة»."})]));
      }
      [currencySel.value].forEach(function(code){
        var info = data[code];
        if(cash[code]) body.appendChild(cashCard(code, cash[code]));
        var rows = [], tot = {required:0, paid:0, remaining:0};
        Object.keys(info.classes).forEach(function(cls){
          info.classes[cls].forEach(function(cell){
            tot.required += Number(cell.required); tot.paid += Number(cell.paid); tot.remaining += Number(cell.remaining);
            rows.push(h("tr", {}, [h("td", {text:cls}), h("td", {text:MONTHS_AR[cell.month - 1]}), h("td", {class:"num", text:money(cell.required)}), h("td", {class:"num", text:money(cell.paid)}),
              h("td", {class:"num" + (Number(cell.remaining) > 0 ? " due" : ""), text:money(cell.remaining)}), h("td", {class:"num", text:String(cell.children_open)})]));
          });
        });
        if(!rows.length) rows.push(h("tr", {}, [h("td", {colspan:"6", class:"a-empty", text:"لا توجد اشتراكات بهذه العملة في هذه السنة."})]));
        var yIncome = info.series.reduce(function(a, s){ return a + Number(s.income); }, 0);
        var yExpense = info.series.reduce(function(a, s){ return a + Number(s.expense); }, 0);
        body.appendChild(h("div", {class:"a-card"}, [
          h("h3", {text:"بـ" + ACC_CURRENCY_NAME[code]}),
          h("div", {class:"a-kpis"}, [
            kpi("المطلوب", money(tot.required)), kpi("المدفوع", money(tot.paid)), kpi("المتبقي", money(tot.remaining), tot.remaining > 0 ? "due" : ""),
            kpi("أطفال عليهم متبقي", String(info.children_open)), kpi("الواردات (الجدول الشهري)", money(yIncome)), kpi("المصروفات (الجدول الشهري)", money(yExpense))
          ]),
          h("h4", {text:"الاشتراكات حسب الصف والشهر"}),
          h("div", {class:"a-table-wrap"}, [h("table", {class:"a-table"}, [
            h("thead", {}, [h("tr", {}, ["الصف","الشهر","المطلوب","المدفوع","المتبقي","أطفال عليهم متبقي"].map(function(t){ return h("th", {text:t}); }))]),
            h("tbody", {}, rows)])]),
          h("h4", {text:"الواردات والمصروفات لكل شهر"}),
          h("p", {class:"hint", text:"أخضر: واردات · أحمر: مصروفات (من الجدول الشهري، الأرقام 1–12 هي الأشهر)"}),
          chart(info.series)
        ]));
      });
    }catch(error){ body.appendChild(h("p", {class:"a-msg err", text:errText(error)})); }
  }
  /* How much money the kindergarten has: opening balance + all income - all expense, month by month. */
  function cashCard(code, cash){
    var amount = accNumber(cash.opening, {"aria-label":"رصيد البداية", required:"required"});
    var monthSel = accSelect(accMonths(false), String(cash.start_month));
    var yearInput = h("input", {type:"number", min:"2000", max:"2100", value:String(cash.start_year)});
    var cashMsg = h("div", {class:"a-msg", role:"status"});
    var form = h("form", {class:"a-form-grid", hidden:"hidden"}, [accField("المبلغ في الصندوق عند البداية (" + code + ")", amount), accField("بداية الحساب من شهر", monthSel), accField("السنة", yearInput),
      h("div", {class:"a-row"}, [h("button", {type:"submit", class:"a-btn sun", text:"حفظ رصيد البداية"})])]);
    form.addEventListener("submit", async function(event){
      event.preventDefault();
      try{
        await request("/api/admin/accounting/cash", {method:"PUT", body:JSON.stringify({currency:code, opening:amount.value || "0", start_year:Number(yearInput.value), start_month:Number(monthSel.value)})});
        setMsg(cashMsg, "تم حفظ رصيد البداية.", "ok"); await load();
      }catch(error){ setMsg(cashMsg, errText(error), "err"); }
    });
    var recent = cash.months.slice(-24).reverse();
    var trail = h("div", {class:"a-table-wrap"}, [labelCells(h("table", {class:"a-table compact"}, [
      h("thead", {}, [h("tr", {}, ["الشهر", "رصيد أول الشهر", "الوارد", "الصادر", "رصيد آخر الشهر"].map(function(t){ return h("th", {text:t}); }))]),
      h("tbody", {}, recent.map(function(m){
        return h("tr", {}, [h("td", {class:"name", text:MONTHS_AR[m.month - 1] + " " + m.year}), h("td", {class:"num", text:money(m.opening)}), h("td", {class:"num", text:money(m.income)}),
          h("td", {class:"num", text:money(m.expense)}), h("td", {class:"num strong" + (Number(m.closing) < 0 ? " due" : ""), text:money(m.closing)})]);
      }))]))]);
    return h("div", {class:"a-card a-cash"}, [
      h("h3", {text:"رصيد الكيتا بـ" + ACC_CURRENCY_NAME[code]}),
      h("div", {class:"a-kpis"}, [kpi("الرصيد الحالي", money(cash.balance), Number(cash.balance) < 0 ? "due" : "good"), kpi("إجمالي الوارد", money(cash.income)), kpi("إجمالي الصادر", money(cash.expense)), kpi("رصيد البداية", money(cash.opening))]),
      cash.configured ? "" : h("p", {class:"a-review-note", text:"لم تحدّد رصيد البداية بعد، لذلك يبدأ الحساب من صفر عند أول شهر فيه بيانات. اضغط «تعديل رصيد البداية» وأدخل المبلغ الموجود في الصندوق عند بدء العمل بالنظام."}),
      h("p", {class:"hint", text:"الرصيد = رصيد البداية + كل الواردات − كل المصروفات، من شهر البداية حتى نهاية الشهر الحالي. الواردات تأتي تلقائياً من الاشتراكات المدفوعة، والمصروفات من الرواتب ومن الجداول. الراتب الذي لم يُسلَّم بعد يُخصم في شهره."}),
      h("div", {class:"a-row"}, [h("button", {type:"button", class:"a-btn ghost", text:"تعديل رصيد البداية", onclick:function(){ form.hidden = !form.hidden; }})]),
      form, cashMsg, h("h4", {text:"الرصيد شهراً بشهر"}), trail]);
  }
  function kpi(label, value, cls){ return h("div", {class:"a-kpi " + (cls || "")}, [h("span", {text:label}), h("strong", {text:value})]); }
  load();
  fill = null;
  var isAdmin = typeof TEACHER_MODE !== "undefined" && !TEACHER_MODE && !ACCOUNTANT_MODE;
  var resetRow = isAdmin ? h("div", {class:"a-row"}, [h("button", {type:"button", class:"a-btn danger", text:"تصفير كل البيانات المالية", onclick:async function(){
    if(!window.confirm("سيُحذف كل ما أُدخل من اشتراكات ودفعات ورواتب وأسطر جداول، لتبدأ الأرقام من الصفر. تبقى أسماء الأطفال والموظفين والحسابات. هل تريد المتابعة؟")) return;
    var word = window.prompt("للتأكيد اكتب الكلمة RESET بالأحرف الكبيرة:");
    if(word === null) return;
    try{
      var done = await request("/api/admin/accounting/reset", {method:"POST", body:JSON.stringify({confirm:word})});
      setMsg(msg, "تم التصفير: " + done.fees + " رسم، " + done.payments + " دفعة، " + done.salaries + " سطر راتب، " + done.sheet_rows + " سطر جدول.", "ok");
      await load();
    }catch(error){ setMsg(msg, errText(error), "err"); }
  }}), h("span", {class:"hint", text:"للمدير فقط. لا يمكن التراجع."})]) : null;
  return h("section", {}, [h("div", {class:"a-card"}, [h("h3", {text:"نظرة عامة على المحاسبة"}),
    h("p", {class:"hint", text:"الأرقام هنا تتحدّث تلقائياً من الإدخالات الجديدة فقط (الاشتراكات والدفعات والرواتب وجداول المحاسبة). بدون إدخالات تكون كلها صفراً."}),
    h("div", {class:"a-form-grid"}, [accField("السنة", year), accField("العملة", currencySel)]), resetRow, msg]), body]);
}

/* -------------------------------------------------------------- payroll */
function tabSalaries(){
  var now = new Date();
  var filters = {year:String(now.getFullYear()), month:String(now.getMonth() + 1), currency:"SYP", needs_review:""};
  var data = {rows:[], totals:{}};
  var employees = [];
  var openId = "";
  var msg = h("div", {class:"a-msg", role:"status", "aria-live":"polite"});
  var tables = h("div", {});

  var fYear = h("input", {type:"number", min:"2000", max:"2100", value:filters.year});
  var fMonth = accSelect(accMonths(true), filters.month);
  var fCurrency = accSelect(accCurrencyOptions(true), "SYP");
  var fReview = h("input", {type:"checkbox"});
  [fYear, fMonth, fCurrency, fReview].forEach(function(el){ el.addEventListener("change", function(){ filters.year = fYear.value; filters.month = fMonth.value; filters.currency = fCurrency.value; filters.needs_review = fReview.checked ? "true" : ""; load(); }); });

  var NEW = "__new__";
  var addEmp = accSelect([[NEW, "＋ موظف جديد (اكتب الاسم)"]], NEW);
  var addName = h("input", {type:"text", maxlength:"120", placeholder:"اسم الموظف / المدرسة", autocomplete:"off", list:"acc-staff"});
  var addJob = h("input", {type:"text", maxlength:"80", placeholder:"المسمى الوظيفي"});
  var addMonth = accSelect(accMonths(false), filters.month), addYear = h("input", {type:"number", min:"2000", max:"2100", value:filters.year});
  var addCurrency = accSelect(accCurrencyOptions(false), "SYP");
  var addBase = accNumber("", {required:"required"}), addBonus = accNumber("0"), addAdvance = accNumber("0"), addDeduction = accNumber("0");
  var addPaid = h("input", {type:"date"});
  var addPaidBy = h("input", {type:"text", maxlength:"120", placeholder:"من صرف الراتب؟", autocomplete:"off", list:"acc-persons"});
  var preview = h("strong", {class:"a-net", text:""});
  var nameField = accField("اسم الموظف", addName), jobField = accField("المسمى الوظيفي", addJob);
  function syncNew(){ var isNew = addEmp.value === NEW; nameField.hidden = !isNew; jobField.hidden = !isNew; }
  function netOf(b, p, a, d){ return Number(b || 0) + Number(p || 0) - Number(a || 0) - Number(d || 0); }
  function updatePreview(){ preview.textContent = "الصافي المستحق: " + money(netOf(addBase.value, addBonus.value, addAdvance.value, addDeduction.value)); }
  [addBase, addBonus, addAdvance, addDeduction].forEach(function(el){ el.addEventListener("input", updatePreview); });
  addEmp.addEventListener("change", function(){
    syncNew();
    var chosen = employees.filter(function(e){ return e.id === addEmp.value; })[0];
    if(chosen && chosen.salary !== null && chosen.salary !== undefined){ addBase.value = chosen.salary; addCurrency.value = chosen.salary_currency || "SYP"; if(addCurrency._accSync) addCurrency._accSync(); updatePreview(); }
  });
  accLinkCurrency(addCurrency, [addBase, addBonus, addAdvance, addDeduction], msg);
  var addForm = h("form", {class:"a-card a-form-grid", hidden:"hidden"}, [
    h("h3", {text:"إضافة سطر راتب"}), accField("الموظف", addEmp), nameField, jobField,
    accField("الشهر", addMonth), accField("السنة", addYear), accField("العملة", addCurrency),
    accField("الراتب الأساسي", addBase), accField("المكافآت / الإضافي", addBonus), accField("السلف", addAdvance), accField("الخصومات", addDeduction),
    accField("تاريخ الاستلام", addPaid), accField("من صرف الراتب", addPaidBy), preview,
    h("div", {class:"a-row"}, [h("button", {type:"submit", class:"a-btn sun", text:"إضافة السطر"})])
  ]);
  addForm.addEventListener("submit", async function(event){
    event.preventDefault();
    var body = {year:Number(addYear.value), month:Number(addMonth.value), currency:addCurrency.value, base:addBase.value || "0",
      bonus:addBonus.value || "0", advance:addAdvance.value || "0", deduction:addDeduction.value || "0", paid_on:addPaid.value || null, paid_by:addPaidBy.value.trim()};
    if(addEmp.value === NEW){ body.employee_name = addName.value.trim(); body.job_title = addJob.value.trim(); if(body.employee_name.length < 2){ setMsg(msg, "اكتب اسم الموظف.", "err"); return; } }
    else body.employee_id = addEmp.value;
    try{
      await request("/api/admin/accounting/salaries", {method:"POST", body:JSON.stringify(body)});
      setMsg(msg, "تمت إضافة سطر الراتب.", "ok"); addName.value = ""; addBase.value = ""; addBonus.value = "0"; addAdvance.value = "0"; addDeduction.value = "0"; updatePreview();
      await loadEmployees(); await load();
    }catch(error){ setMsg(msg, errText(error), "err"); }
  });

  function currencyTable(code){
    var rows = data.rows.filter(function(r){ return r.currency === code; });
    var t = data.totals[code] || {base:"0", bonus:"0", advance:"0", deduction:"0", net:"0"};
    var heads = ["الرقم","اسم الموظف / المدرسة","المسمى الوظيفي","الراتب الأساسي","المكافآت / الإضافي","السلف","الخصومات","الصافي المستحق","تاريخ الاستلام","صرفه",""];  // the signature column is only on the printed sheet
    var tbody = h("tbody", {});
    rows.forEach(function(r, i){
      var ed = r.needs_review ? salaryInline(r) : null;
      tbody.appendChild(h("tr", {class:"a-fee-row" + (r.needs_review ? " review" : "")}, [
        h("td", {class:"num", text:String(i + 1)}),
        ed ? h("td", {class:"name"}, [ed.name, h("span", {class:"a-badge review", text:"يحتاج مراجعة"})]) : h("td", {class:"name", dir:"auto", text:r.employee_name || "—"}),
        ed ? h("td", {}, [ed.job]) : h("td", {dir:"auto", text:r.job_title || "—"}),
        ed ? h("td", {class:"num"}, [ed.base]) : h("td", {class:"num", text:money(r.base)}),
        ed ? h("td", {class:"num"}, [ed.bonus]) : h("td", {class:"num", text:money(r.bonus)}),
        ed ? h("td", {class:"num"}, [ed.advance]) : h("td", {class:"num", text:money(r.advance)}),
        ed ? h("td", {class:"num"}, [ed.deduction]) : h("td", {class:"num", text:money(r.deduction)}),
        h("td", {class:"num strong", text:money(r.net)}),
        ed ? h("td", {}, [ed.date]) : h("td", {class:"num", text:r.paid_on || "—"}),
        ed ? h("td", {}, [ed.paid_by]) : h("td", {dir:"auto", title:r.recorded_by ? "سجّله: " + r.recorded_by : "", text:r.paid_by || "—"}),
        h("td", {}, [ed ? ed.save : "", h("button", {type:"button", class:"a-btn " + (openId === r.id ? "ghost" : "sun"), text:openId === r.id ? "إغلاق" : "تعديل", onclick:function(){ openId = openId === r.id ? "" : r.id; render(); }})])
      ]));
      if(openId === r.id) tbody.appendChild(editRow(r, heads.length));
    });
    if(!rows.length) tbody.appendChild(h("tr", {}, [h("td", {colspan:String(heads.length), class:"a-empty", text:"لا توجد رواتب بهذه العملة."})]));
    var foot = h("tfoot", {}, [h("tr", {class:"a-total"}, [h("td", {colspan:"3", text:"الإجمالي العام (" + code + ")"}), h("td", {class:"num", text:money(t.base)}), h("td", {class:"num", text:money(t.bonus)}),
      h("td", {class:"num", text:money(t.advance)}), h("td", {class:"num", text:money(t.deduction)}), h("td", {class:"num", text:money(t.net)}), h("td", {colspan:"3"})])]);
    return h("div", {class:"a-card"}, [h("h3", {text:"الرواتب بـ" + ACC_CURRENCY_NAME[code]}),
      h("div", {class:"a-table-wrap"}, [labelCells(h("table", {class:"a-table compact"}, [h("thead", {}, [h("tr", {}, heads.map(function(t){ return h("th", {text:t}); }))]), tbody, foot]))])]);
  }
  function salaryBody(fields){
    function num(el){ return el.value === "" ? null : el.value; }  // empty stays empty, never 0
    return JSON.stringify({employee_name:fields.name ? fields.name.value.trim() : null, job_title:fields.job.value.trim(), base:num(fields.base), bonus:num(fields.bonus),
      advance:num(fields.advance), deduction:num(fields.deduction), paid_on:fields.date.value || null, paid_by:fields.paid_by ? fields.paid_by.value.trim() : null});
  }
  function salaryInline(r){
    var f = {name:h("input", {type:"text", maxlength:"120", value:r.employee_name, placeholder:"الاسم", "aria-label":"اسم الموظف", list:"acc-staff"}),
      job:h("input", {type:"text", maxlength:"80", value:r.job_title, placeholder:"المسمى", "aria-label":"المسمى الوظيفي"}),
      base:accNumber(r.base, {"aria-label":"الراتب الأساسي"}), bonus:accNumber(r.bonus, {"aria-label":"المكافآت"}), advance:accNumber(r.advance, {"aria-label":"السلف"}),
      deduction:accNumber(r.deduction, {"aria-label":"الخصومات"}), date:h("input", {type:"date", value:r.paid_on || "", "aria-label":"تاريخ الاستلام"}),
      paid_by:h("input", {type:"text", maxlength:"120", value:r.paid_by || "", placeholder:"من صرف", "aria-label":"من صرف الراتب", list:"acc-persons"})};
    f.save = h("button", {type:"button", class:"a-btn sun", text:"حفظ", onclick:async function(){
      try{ await request("/api/admin/accounting/salaries/" + encodeURIComponent(r.id), {method:"PATCH", body:salaryBody(f)}); setMsg(msg, "تم حفظ التصحيح. اضغط «تمت المراجعة» بعد التأكد من السطر.", "ok"); await load(); }
      catch(error){ setMsg(msg, errText(error), "err"); }
    }});
    return f;
  }
  function editRow(r, cols){
    var job = h("input", {type:"text", maxlength:"80", value:r.job_title}), base = accNumber(r.base), bonus = accNumber(r.bonus), adv = accNumber(r.advance), ded = accNumber(r.deduction);
    var paid = h("input", {type:"date", value:r.paid_on || ""});
    var buttons = [h("button", {type:"submit", class:"a-btn sun", text:"حفظ"}),
      twoStep("حذف السطر", async function(){ await request("/api/admin/accounting/salaries/" + encodeURIComponent(r.id), {method:"DELETE"}); openId = ""; setMsg(msg, "تم حذف السطر.", "ok"); await load(); })];
    if(r.needs_review) buttons.unshift(h("button", {type:"button", class:"a-btn ghost", text:"تمت المراجعة", onclick:async function(){
      try{ await request("/api/admin/accounting/salaries/" + encodeURIComponent(r.id) + "/reviewed", {method:"POST"}); await load(); }catch(error){ setMsg(msg, errText(error), "err"); } }}));
    var form = h("form", {class:"a-form-grid"}, [
      r.needs_review ? h("p", {class:"a-review-note", dir:"auto", text:"النص الأصلي: " + (r.raw_text || "—") + " · المصدر: " + (r.source || "—")}) : "",
      accField("المسمى الوظيفي", job), accField("الراتب الأساسي", base), accField("المكافآت / الإضافي", bonus), accField("السلف", adv), accField("الخصومات", ded), accField("تاريخ الاستلام", paid),
      h("div", {class:"a-row"}, buttons)]);
    form.addEventListener("submit", async function(event){
      event.preventDefault();
      try{
        await request("/api/admin/accounting/salaries/" + encodeURIComponent(r.id), {method:"PATCH", body:salaryBody({name:null, job:job, base:base, bonus:bonus, advance:adv, deduction:ded, date:paid})});
        setMsg(msg, "تم حفظ التعديل.", "ok"); await load();
      }catch(error){ setMsg(msg, errText(error), "err"); }
    });
    return h("tr", {class:"a-detail-row"}, [h("td", {colspan:String(cols), class:"a-detail"}, [form])]);
  }
  function render(){ tables.innerHTML = ""; (filters.currency ? [filters.currency] : ACC_CURRENCIES).forEach(function(code){ tables.appendChild(currencyTable(code)); }); }
  async function load(){
    accLoadNames();
    var q = []; ["year","month","currency","needs_review"].forEach(function(k){ if(filters[k]) q.push(k + "=" + encodeURIComponent(filters[k])); });
    try{ data = await request("/api/admin/accounting/salaries?" + q.join("&")); render(); }
    catch(error){ tables.innerHTML = ""; tables.appendChild(h("p", {class:"a-msg err", text:errText(error)})); }
  }
  async function loadEmployees(){
    try{
      employees = await request("/api/admin/accounting/employees");
      var keep = addEmp.value; addEmp.innerHTML = ""; addEmp.appendChild(new Option("＋ موظف جديد (اكتب الاسم)", NEW));
      employees.forEach(function(e){ addEmp.appendChild(new Option(e.name + (e.job_title ? " — " + e.job_title : ""), e.id)); });
      addEmp.value = employees.some(function(e){ return e.id === keep; }) ? keep : NEW; syncNew();
    }catch(error){ setMsg(msg, errText(error), "err"); }
  }
  async function print(){
    var codes = filters.currency ? [filters.currency] : ACC_CURRENCIES;
    try{ if(await accFillSavedSalaries(filters.year, filters.month, codes, msg)) await load(); }
    catch(error){ setMsg(msg, errText(error), "err"); return; }
    var period = (filters.month ? MONTHS_AR[Number(filters.month) - 1] + " " : "") + (filters.year || "");
    var parts = codes.map(function(code){
      var rows = data.rows.filter(function(r){ return r.currency === code; });
      var t = data.totals[code] || {base:"0", bonus:"0", advance:"0", deduction:"0", net:"0"};
      var body = rows.map(function(r, i){ return "<tr><td>" + (i + 1) + "</td><td class='l'>" + esc(r.employee_name) + "</td><td>" + esc(r.job_title || "—") + "</td><td class='n'>" + money(r.base) + "</td><td class='n'>" + money(r.bonus) +
        "</td><td class='n'>" + money(r.advance) + "</td><td class='n'>" + money(r.deduction) + "</td><td class='n'><b>" + money(r.net) + "</b></td><td class='n'>" + esc(r.paid_on || "—") + "</td><td>" + esc(r.paid_by || "") + "</td><td><span class='line'>&nbsp;</span></td></tr>"; }).join("");
      return {code:code, cols:[5,12,9,12,10,8,8,13,8,7,8], html:"<table><thead>" + accTh(["الرقم","اسم الموظف / المدرسة","المسمى الوظيفي","الراتب الأساسي","المكافآت / الإضافي","السلف","الخصومات","الصافي المستحق","تاريخ الاستلام","صرفه","توقيع المستلم"]) + "</thead><tbody>" +
        (body || "<tr><td colspan='11'>لا توجد بيانات</td></tr>") + "</tbody><tfoot><tr><td colspan='3'>الإجمالي العام (" + code + ")</td><td>" + money(t.base) + "</td><td>" + money(t.bonus) + "</td><td>" + money(t.advance) +
        "</td><td>" + money(t.deduction) + "</td><td>" + money(t.net) + "</td><td colspan='3'></td></tr></tfoot></table>"};
    });
    accPrint("كشف رواتب الموظفين والمدرسات", function(part){ return "الفترة: " + esc(period) + " &nbsp;|&nbsp; العملة: " + esc(ACC_CURRENCY_NAME[part.code]); }, parts, msg);
  }
  var filterCard = h("div", {class:"a-card"}, [h("h3", {text:"كشف رواتب الموظفين والمدرسات"}),
    h("p", {class:"hint", text:"الصافي المستحق = الراتب الأساسي + المكافآت − السلف − الخصومات. يُحسب تلقائياً."}),
    h("div", {class:"a-form-grid"}, [accField("السنة", fYear), accField("الشهر", fMonth), accField("العملة", fCurrency), h("label", {class:"a-field a-check-field"}, [fReview, h("span", {text:"فقط ما يحتاج مراجعة"})])]),
    h("div", {class:"a-row"}, [h("button", {type:"button", class:"a-btn sun", text:"＋ إضافة سطر راتب", onclick:function(){ addForm.hidden = !addForm.hidden; }}),
      h("button", {type:"button", class:"a-btn ghost", text:"إنشاء رواتب الشهر للجميع", onclick:async function(){
        var month = Number(fMonth.value), year = Number(fYear.value);
        if(!month || !year){ setMsg(msg, "اختر السنة والشهر أولاً.", "err"); return; }
        try{
          var created = 0, skipped = 0;
          var codes = fCurrency.value ? [fCurrency.value] : ACC_CURRENCIES;
          for(var i = 0; i < codes.length; i++){
            var res = await request("/api/admin/accounting/salaries/generate", {method:"POST", body:JSON.stringify({year:year, month:month, currency:codes[i]})});
            created += res.created; skipped += res.skipped;
          }
          setMsg(msg, "تم إنشاء " + created + " سطر راتب، وتخطّي " + skipped + " (موجود مسبقاً). الموظفون بلا راتب محفوظ لا يُنشأ لهم سطر.", "ok"); await load();
        }catch(error){ setMsg(msg, errText(error), "err"); }
      }}),
      h("button", {type:"button", class:"a-btn", text:"تصدير PDF / طباعة", onclick:print})]), msg]);
  syncNew(); updatePreview(); loadEmployees(); load();
  fill = null;
  return h("section", {}, [filterCard, addForm, tables]);
}

/* ------------------------------------------------- monthly / weekly sheet */
function tabSheet(type){
  var now = new Date();
  var isWeek = type !== "month";  // week and day sheets have separate income / expense columns
  var isDay = type === "day";
  var SHEET_TITLE = isDay ? "جدول المحاسبة اليومي" : isWeek ? "جدول المحاسبة الأسبوعي" : "جدول المحاسبة الشهري";
  var filters = {year:String(now.getFullYear()), month:String(now.getMonth() + 1), day:localToday()};
  var data = null;  // the sheet from the server: pounds and dollars together, one line per currency of an item
  var cash = null;  // the capital and the balance per currency
  var msg = h("div", {class:"a-msg", role:"status", "aria-live":"polite"});
  var capital = h("div", {});
  var tables = h("div", {});
  var fYear = h("input", {type:"number", min:"2000", max:"2100", value:filters.year});
  var fMonth = accSelect(accMonths(false), filters.month);
  var fDay = h("input", {type:"date", value:filters.day});
  [fYear, fMonth, fDay].forEach(function(el){ el.addEventListener("change", function(){ filters.year = fYear.value; filters.month = fMonth.value; filters.day = fDay.value; load(); }); });
  var HEADS = isWeek ? ["البند / المادة", "التفاصيل", "البيان / الملاحظات", "المسؤول (من صرف / استلم)", "المبالغ الواردة", "المبالغ الصادرة", "العملة", ""]
    : ["البند / المادة", "التفاصيل", "البيان / الملاحظات", "المسؤول (من صرف / استلم)", "المبلغ", "العملة", ""];
  var CURRENCY_CHOICES = [["SYP", "SYP"], ["USD", "USD"]];

  function sheetYear(){ return isWeek ? String(filters.day || "").slice(0, 4) || filters.year : filters.year; }  // week / day: the date decides
  function query(){
    return "period_type=" + type + "&year=" + encodeURIComponent(sheetYear()) + (isWeek ? "&week_start=" + encodeURIComponent(filters.day) : "&month=" + encodeURIComponent(filters.month));
  }
  function entryBody(item, currency, details, note, income, expense, person){
    var b = {period_type:type, year:Number(sheetYear()), currency:currency, item_key:item.key, item_label:item.label, details:details, note:note, person:person || "", income:income || "0", expense:expense || "0", manual:true};
    if(isWeek) b.week_start = filters.day; else b.month = Number(filters.month);
    return b;
  }
  function nonZero(text){ return accCents(text) !== 0n; }
  function dollarsUsed(){
    if(!data) return false;
    return data.items.some(function(i){ return i.lines.some(function(l){ return l.currency === "USD" && (l.id || nonZero(l.income) || nonZero(l.expense)); }); }) ||
      nonZero(data.totals.USD.income) || nonZero(data.totals.USD.expense) || !!(data.balance && data.balance.USD && (nonZero(data.balance.USD.opening) || nonZero(data.balance.USD.closing)));
  }

  /* ---- one line of an item (an item can have a line in pounds and a line in dollars) ---- */
  function lineRow(item, line, first){
    var label;
    if(item.key === "rolled"){  // a free row written on a day / week sheet, added up here: shown, not edited
      var readOnly = isWeek ? [h("td", {class:"num", text:nonZero(line.income) ? money(line.income) : "—"}), h("td", {class:"num", text:nonZero(line.expense) ? money(line.expense) : "—"})]
        : [h("td", {class:"num", text:money(nonZero(line.income) ? line.income : line.expense)})];
      var roRow = h("tr", {class:"a-rolled"}, [h("td", {class:"name"}, [item.label, h("span", {class:"a-badge partial", text:"مجمّع تلقائياً"})]), h("td", {text:"—"}), h("td", {text:"—"}), h("td", {text:"—"})]
        .concat(readOnly).concat([h("td", {}, [h("span", {class:"a-tag", text:line.currency})]), h("td")]));
      Array.prototype.forEach.call(roRow.children, function(cellNode, i){ if(i > 0 && HEADS[i]) cellNode.setAttribute("data-label", HEADS[i]); });
      return roRow;
    }
    var details = h("input", {type:"text", maxlength:"500", value:line.details, "aria-label":"التفاصيل"});
    var note = h("input", {type:"text", maxlength:"500", value:line.note, "aria-label":"الملاحظات"});
    var person = h("input", {type:"text", maxlength:"120", value:line.person || "", placeholder:"الاسم", "aria-label":"المسؤول", list:"acc-persons", title:line.entered_by ? "أدخله: " + line.entered_by : ""});
    var income = accNumber(nonZero(line.income) ? line.income : "", {"aria-label":"الوارد", placeholder:"0.00", class:"amt in"});
    var expense = accNumber(nonZero(line.expense) ? line.expense : "", {"aria-label":"الصادر", placeholder:"0.00", class:"amt out"});
    var amount = accNumber(nonZero(line.income) ? line.income : nonZero(line.expense) ? line.expense : "", {"aria-label":"المبلغ", placeholder:"0.00", class:"amt " + (line.kind === "income" ? "in" : "out")});
    var kindSel = (item.custom || item.choice) && !isWeek ? accSelect([["expense", "صادر"], ["income", "وارد"]], line.kind) : null;
    var currencyCell, currencySel = null;
    if(item.auto){  // an automatic row belongs to the currency its payments came in
      currencyCell = h("td", {}, [h("span", {class:"a-tag", text:line.currency})]);
    }else{
      currencySel = accSelect(CURRENCY_CHOICES, line.currency);  // switching converts the amount typed in this row
      accLinkCurrency(currencySel, isWeek ? [income, expense] : [amount], msg);
      currencyCell = h("td", {}, [currencySel]);
    }
    var amountCells = isWeek
      ? [h("td", {}, [income]), h("td", {}, [expense])]
      : [h("td", {}, [h("div", {class:"a-amount"}, [kindSel ? kindSel : h("span", {class:"a-tag kind-" + line.kind, text:line.kind === "income" ? "وارد" : "صادر"}), amount])])];
    var actions = [h("button", {type:"button", class:"a-btn sun save", text:"حفظ", disabled:"disabled", onclick:async function(){
      var inc = income.value, exp = expense.value;
      if(!isWeek){
        var kind = kindSel ? kindSel.value : line.kind;
        inc = kind === "income" ? amount.value : "0";
        exp = kind === "expense" ? amount.value : "0";
      }
      var currency = currencySel ? currencySel.value : line.currency;
      var body = entryBody(item, currency, details.value, note.value, inc, exp, person.value);
      if(currency !== line.currency){ if(line.id) body.replaces = line.id; }  // the row moves to the other currency
      else if(item.custom && line.id) body.id = line.id;
      try{
        await request("/api/admin/accounting/entries", {method:"PUT", body:JSON.stringify(body)});
        setMsg(msg, currency !== line.currency ? "تم نقل السطر إلى " + currency + " وحفظه." : "تم الحفظ.", "ok"); await load();
      }catch(error){ setMsg(msg, errText(error), "err"); }
    }})];
    var removes = item.custom || !item.auto;  // a row without an automatic value is simply deleted; an automatic one goes back to it
    if(line.id && (item.custom || line.manual)) actions.push(twoStep(removes ? "حذف" : "إعادة للتلقائي", async function(){
      await request("/api/admin/accounting/entries/" + encodeURIComponent(line.id), {method:"DELETE"}); setMsg(msg, item.custom ? "تم حذف البند." : removes ? "تم حذف السطر." : "عاد البند إلى القيمة التلقائية.", "ok"); await load(); }));
    label = first
      ? h("td", {class:"name"}, [item.label, item.auto ? h("span", {class:"a-badge " + (line.manual ? "partial" : "paid"), text:line.manual ? "يدوي" : "تلقائي"}) : "",
          line.rolled ? h("span", {class:"a-badge partial", text:"مجمّع تلقائياً", title:"مجموع ما كُتب في الجداول الأدق (الأسبوعي واليومي)"}) : ""])
      : h("td", {class:"name"}, [h("small", {class:"hint", text:"↳ " + item.label})]);
    if(first && item.auto && line.manual) label.appendChild(h("small", {class:"hint", text:"القيمة التلقائية: " + money(item.key === "registration" ? line.auto_income : line.auto_expense)}));
    var hasData = !!line.id || nonZero(line.income) || nonZero(line.expense);
    var row = h("tr", {class:(item.auto ? "is-auto " : "") + (item.custom ? "is-custom " : "") + (hasData ? "has-data" : "idle")}, [label, h("td", {}, [details]), h("td", {}, [note]), h("td", {}, [person])].concat(amountCells).concat([currencyCell, h("td", {}, [h("div", {class:"a-row", style:"margin:0"}, actions)])]));
    Array.prototype.forEach.call(row.children, function(cellNode, i){ if(i > 0 && HEADS[i]) cellNode.setAttribute("data-label", HEADS[i]); });  // shown as captions on a phone
    // a row that was changed lights up and can be saved; nothing to save, nothing to press
    var saveButton = actions[0];
    function markChanged(){ saveButton.disabled = false; row.classList.add("dirty"); }
    [details, note, person, income, expense, amount, kindSel, currencySel].forEach(function(el){ if(el){ el.addEventListener("input", markChanged); el.addEventListener("change", markChanged); } });
    return row;
  }
  function sheetCard(){
    var tbody = h("tbody", {});
    data.items.forEach(function(item){ item.lines.forEach(function(line, index){ tbody.appendChild(lineRow(item, line, index === 0)); }); });
    var widths = isWeek ? [14, 11, 12, 11, 16, 16, 9, 11] : [18, 13, 14, 12, 19, 12, 12];
    return h("div", {class:"a-card"}, [h("h3", {text:(isDay ? "اليوم" : isWeek ? "الأسبوع" : "الشهر") + " — ليرة ودولار معاً"}),
      h("p", {class:"hint", text:"لكل سطر عملته. غيّر العملة في السطر فيتحوّل المبلغ المكتوب تلقائياً بسعر اليوم، ثم اضغط «حفظ» لينتقل السطر إلى دفتر العملة الأخرى."}),
      h("div", {class:"a-table-wrap"}, [h("table", {class:"a-table a-sheet"}, [h("colgroup", {}, widths.map(function(w){ return h("col", {style:"width:" + w + "%"}); })),
        h("thead", {}, [h("tr", {}, HEADS.map(function(t){ return h("th", {text:t}); }))]), tbody])]), customRowForm()]);
  }
  function customRowForm(){
    var label = h("input", {type:"text", maxlength:"120", placeholder:"اسم البند"});
    var details = h("input", {type:"text", maxlength:"500"}), note = h("input", {type:"text", maxlength:"500"});
    var kind = accSelect([["expense", "صادر (مصروف)"], ["income", "وارد (إيراد)"]], "expense");
    var personNew = h("input", {type:"text", maxlength:"120", placeholder:"من صرف / من استلم؟", list:"acc-persons"});
    var amount = accNumber("", {required:"required"});
    var currency = accSelect(CURRENCY_CHOICES, "SYP");
    accLinkCurrency(currency, [amount], msg);
    var form = h("form", {class:"a-form-grid a-custom"}, [h("strong", {text:"＋ إضافة بند جديد"}), accField("البند", label), accField("التفاصيل", details), accField("البيان / الملاحظات", note), accField("المسؤول (من صرف / استلم)", personNew), accField("النوع", kind), accField("المبلغ", amount), accField("العملة", currency),
      h("div", {class:"a-row"}, [h("button", {type:"submit", class:"a-btn ghost", text:"إضافة البند"})])]);
    form.addEventListener("submit", async function(event){
      event.preventDefault();
      var item = {key:"custom", label:label.value.trim(), custom:true};
      try{
        await request("/api/admin/accounting/entries", {method:"PUT", body:JSON.stringify(entryBody(item, currency.value, details.value, note.value, kind.value === "income" ? amount.value : "0", kind.value === "expense" ? amount.value : "0", personNew.value))});
        setMsg(msg, "تمت إضافة البند.", "ok"); await load();
      }catch(error){ setMsg(msg, errText(error), "err"); }
    });
    return form;
  }

  /* ---- totals per currency, both currencies added up, and the balance at the start and the end ---- */
  function summaryCard(){
    var codes = dollarsUsed() ? ACC_CURRENCIES : ["SYP"];
    var rows = codes.map(function(code){
      var t = data.totals[code];
      return h("tr", {}, [h("td", {class:"name", text:"الإجمالي (" + code + ")"}), h("td", {class:"num", text:money(t.income)}), h("td", {class:"num", text:money(t.expense)}), h("td", {class:"num strong" + (accCents(t.net) < 0n ? " due" : ""), text:money(t.net)})]);
    });
    var conv = data.converted;
    if(conv) ACC_CURRENCIES.forEach(function(code){
      var t = conv[code];
      rows.push(h("tr", {class:"a-rolled"}, [h("td", {class:"name", text:"المجموع بالـ" + (code === "SYP" ? "ليرة" : "دولار") + " (بعد التحويل)"}), h("td", {class:"num", text:money(t.income)}), h("td", {class:"num", text:money(t.expense)}), h("td", {class:"num strong" + (accCents(t.net) < 0n ? " due" : ""), text:money(t.net)})]));
    });
    var totals = h("div", {class:"a-table-wrap"}, [labelCells(h("table", {class:"a-table compact"}, [
      h("thead", {}, [h("tr", {}, ["", "الوارد", "الصادر", "الصافي"].map(function(t){ return h("th", {text:t}); }))]), h("tbody", {}, rows)]))]);
    var parts = [h("h3", {text:"الإجماليات والرصيد"}), totals];
    if(data.balance){
      var label = isDay ? "اليوم" : isWeek ? "الأسبوع" : "الشهر";
      var brows = codes.filter(function(c){ return data.balance[c]; }).map(function(code){
        var b = data.balance[code];
        return h("tr", {}, [h("td", {class:"name", text:"الرصيد (" + code + ")"}), h("td", {class:"num", text:money(b.opening)}), h("td", {class:"num strong" + (accCents(b.closing) < 0n ? " due" : ""), text:money(b.closing)})]);
      });
      if(conv && conv.SYP && conv.SYP.opening !== undefined) ACC_CURRENCIES.forEach(function(code){
        var c = conv[code];
        brows.push(h("tr", {class:"a-rolled"}, [h("td", {class:"name", text:"الرصيد الكلي بالـ" + (code === "SYP" ? "ليرة" : "دولار") + " (بعد التحويل)"}), h("td", {class:"num", text:money(c.opening)}), h("td", {class:"num strong" + (accCents(c.closing) < 0n ? " due" : ""), text:money(c.closing)})]));
      });
      if(brows.length) parts.push(h("h4", {text:"رصيد الكيتا"}), h("div", {class:"a-table-wrap"}, [labelCells(h("table", {class:"a-table compact"}, [
        h("thead", {}, [h("tr", {}, ["", "رصيد أول " + label, "رصيد آخر " + label].map(function(t){ return h("th", {text:t}); }))]), h("tbody", {}, brows)]))]));
    }else{
      parts.push(h("p", {class:"hint", text:"لم يُدخَل رأس مال الكيتا بعد، لذلك لا يظهر الرصيد. أدخله في الصندوق أعلى هذه الصفحة."}));
    }
    if(conv) parts.push(h("p", {class:"hint", text:"1 دولار = " + conv.rate + " ليرة (" + (conv.source === "auto" ? "سعر اليوم تلقائياً من الإنترنت" : "السعر المحفوظ") + (conv.stale ? "، تعذّر جلب سعر اليوم فاستُعمل آخر سعر بتاريخ " + conv.rate_date : "") + ")."}));
    if(isWeek && data.balance) parts.push(h("p", {class:"hint", text:"رصيد أول اليوم/الأسبوع = رصيد أول الشهر + ما سُجّل في الأيام السابقة من الشهر. البنود الأسبوعية والشهرية وغير المؤرخة تُحتسب كاملة في رصيد الشهر."}));
    return h("div", {class:"a-card"}, parts);
  }

  /* ---- the capital of the kindergarten: entered here, every income and expense is counted from it ---- */
  function renderCapital(){
    capital.innerHTML = "";
    if(!cash) return;
    function kpiBox(label, value, cls){ return h("div", {class:"a-kpi " + (cls || "")}, [h("span", {text:label}), h("strong", {text:value})]); }
    var shown = ACC_CURRENCIES.filter(function(c){ return c === "SYP" || cash[c].configured || nonZero(cash[c].balance); });
    var kpis = shown.map(function(c){ return kpiBox("الرصيد الحالي (" + c + ")", money(cash[c].balance), accCents(cash[c].balance) < 0n ? "due" : "good"); });
    if(cash.total) ACC_CURRENCIES.forEach(function(c){ kpis.push(kpiBox("إجمالي الكيتا بالـ" + (c === "SYP" ? "ليرة" : "دولار"), money(cash.total[c].balance), accCents(cash.total[c].balance) < 0n ? "due" : "good")); });
    var base = cash.SYP.configured ? cash.SYP : cash.USD.configured ? cash.USD : null;
    var amount = accNumber(base ? base.opening : "", {"aria-label":"رأس المال", required:"required"});
    var currencySel = accSelect(CURRENCY_CHOICES, base ? base.currency : "SYP");
    accLinkCurrency(currencySel, [amount], msg);
    var monthSel = accSelect(accMonths(false), String(base ? base.start_month : Number(filters.month)));
    var yearInput = h("input", {type:"number", min:"2000", max:"2100", value:String(base ? base.start_year : Number(sheetYear()))});
    var form = h("form", {class:"a-form-grid", hidden:base ? "hidden" : null}, [accField("رأس مال الكيتا (المبلغ عند البداية)", amount), accField("العملة", currencySel), accField("يبدأ الحساب من شهر", monthSel), accField("السنة", yearInput),
      h("div", {class:"a-row"}, [h("button", {type:"submit", class:"a-btn sun", text:"حفظ رأس المال"})])]);
    if(!base) form.removeAttribute("hidden");
    form.addEventListener("submit", async function(event){
      event.preventDefault();
      try{
        await request("/api/admin/accounting/cash", {method:"PUT", body:JSON.stringify({currency:currencySel.value, opening:amount.value || "0", start_year:Number(yearInput.value), start_month:Number(monthSel.value)})});
        setMsg(msg, "تم حفظ رأس المال.", "ok"); await load();
      }catch(error){ setMsg(msg, errText(error), "err"); }
    });
    var configured = ACC_CURRENCIES.filter(function(c){ return cash[c].configured; }).map(function(c){ return money(cash[c].opening) + " " + c + " (من " + MONTHS_AR[cash[c].start_month - 1] + " " + cash[c].start_year + ")"; });
    capital.appendChild(h("div", {class:"a-card a-cash"}, [h("h3", {text:"رأس مال الكيتا والرصيد"}),
      h("div", {class:"a-kpis"}, kpis),
      configured.length ? h("p", {class:"hint", text:"رأس المال عند البداية: " + configured.join(" · ") + ". الرصيد = رأس المال + كل الوارد − كل الصادر."})
        : h("p", {class:"a-review-note", text:"أدخل رأس مال الكيتا (المبلغ الموجود عند بدء العمل بالنظام)، وبعدها يُحسب الوارد والصادر منه ويظهر الرصيد في كل جدول لتتبّع أين ذهب المال."}),
      base ? h("div", {class:"a-row"}, [h("button", {type:"button", class:"a-btn ghost", text:"تعديل رأس المال", onclick:function(){ form.hidden = !form.hidden; }})]) : "", form]));
  }
  function render(){
    renderCapital();
    tables.innerHTML = "";
    tables.appendChild(sheetCard());
    tables.appendChild(summaryCard());
  }
  async function load(){
    accLoadNames();
    try{
      var results = await Promise.all([request("/api/admin/accounting/sheet-all?" + query()), request("/api/admin/accounting/cash")]);
      data = results[0]; cash = results[1];
      render();
    }catch(error){ tables.innerHTML = ""; tables.appendChild(h("p", {class:"a-msg err", text:errText(error)})); }
  }

  /* ---- print ---- */
  async function print(){
    if(!isWeek){  // monthly sheet: the "salaries" line comes from the payroll, so fill it from the saved salaries first
      try{ if(await accFillSavedSalaries(filters.year, filters.month, ACC_CURRENCIES, msg)) await load(); }
      catch(error){ setMsg(msg, errText(error), "err"); return; }
    }
    var body = "";
    data.items.forEach(function(item){
      item.lines.forEach(function(line){
        var kindText = nonZero(line.income) ? "وارد" : nonZero(line.expense) ? "صادر" : "";
        var amounts = isWeek ? "<td class='n'>" + (nonZero(line.income) ? money(line.income) : "") + "</td><td class='n'>" + (nonZero(line.expense) ? money(line.expense) : "") + "</td>"
          : "<td>" + kindText + "</td><td class='n'>" + ((nonZero(line.income) || nonZero(line.expense)) ? money(nonZero(line.income) ? line.income : line.expense) : "") + "</td>";
        body += "<tr><td class='l'>" + esc(item.label) + "</td><td class='l'>" + esc(line.details) + "</td><td class='l'>" + esc(line.note) + "</td><td class='l'>" + esc(line.person || "") + "</td>" + amounts + "<td>" + esc(line.currency) + "</td></tr>";
      });
    });
    var codes = dollarsUsed() ? ACC_CURRENCIES : ["SYP"], conv = data.converted;
    var totalRows = codes.map(function(c){ var t = data.totals[c]; return "<tr><td class='l'>الإجمالي (" + c + ")</td><td>" + money(t.income) + "</td><td>" + money(t.expense) + "</td><td>" + money(t.net) + "</td></tr>"; }).join("");
    if(conv) totalRows += ACC_CURRENCIES.map(function(c){ var t = conv[c]; return "<tr><td class='l'>المجموع بالـ" + (c === "SYP" ? "ليرة" : "دولار") + " (بعد التحويل)</td><td>" + money(t.income) + "</td><td>" + money(t.expense) + "</td><td>" + money(t.net) + "</td></tr>"; }).join("");
    var label = isDay ? "اليوم" : isWeek ? "الأسبوع" : "الشهر";
    var balanceTable = "";
    if(data.balance){
      var brows = codes.filter(function(c){ return data.balance[c]; }).map(function(c){ var b = data.balance[c]; return "<tr><td class='l'>الرصيد (" + c + ")</td><td>" + money(b.opening) + "</td><td>" + money(b.closing) + "</td></tr>"; }).join("");
      if(conv && conv.SYP && conv.SYP.opening !== undefined) brows += ACC_CURRENCIES.map(function(c){ var b = conv[c]; return "<tr><td class='l'>الرصيد الكلي بالـ" + (c === "SYP" ? "ليرة" : "دولار") + " (بعد التحويل)</td><td>" + money(b.opening) + "</td><td>" + money(b.closing) + "</td></tr>"; }).join("");
      balanceTable = "<table style='margin-top:6px'><thead>" + accTh(["رصيد الكيتا", "رصيد أول " + label, "رصيد آخر " + label]) + "</thead><tbody>" + brows + "</tbody></table>";
    }
    var html = "<table><thead>" + accTh(isWeek ? ["البند / المادة", "التفاصيل", "البيان / الملاحظات", "المسؤول (من صرف / استلم)", "المبالغ الواردة", "المبالغ الصادرة", "العملة"] : ["البند / المادة", "التفاصيل", "البيان / الملاحظات", "المسؤول (من صرف / استلم)", "النوع", "المبلغ", "العملة"]) + "</thead><tbody>" + body + "</tbody></table>" +
      "<table style='margin-top:6px'><thead>" + accTh(["", "الوارد", "الصادر", "الصافي"]) + "</thead><tbody>" + totalRows + "</tbody></table>" + balanceTable;
    var parts = [{code:"all", sheet:data, cols:isWeek ? [19, 14, 15, 13, 12, 12, 9] : [20, 15, 16, 14, 9, 17, 9], html:html}];
    accPrint(SHEET_TITLE, function(part){
      return (isDay ? "التاريخ: " + esc(part.sheet.start) + " (" + esc(new Date(part.sheet.start + "T00:00:00").toLocaleDateString("ar-SY", {weekday:"long"})) + ")" : isWeek ? "من " + esc(part.sheet.start) + " إلى " + esc(part.sheet.end) : "الشهر: " + esc(MONTHS_AR[Number(filters.month) - 1]) + " " + esc(filters.year)) +
        (part.sheet.converted ? " &nbsp;|&nbsp; 1 $ = " + esc(part.sheet.converted.rate) + " ل.س" : ""); }, parts, msg);
  }
  var periodFields = isWeek ? [accField(isDay ? "اليوم" : "أي يوم من الأسبوع", fDay)] : [accField("السنة", fYear), accField("الشهر", fMonth)];
  var head = h("div", {class:"a-card"}, [h("h3", {text:SHEET_TITLE}),
    h("p", {class:"hint", text:"«رسوم التسجيل والاشتراكات» و«رواتب المدرسات والموظفين» تُعبَّآن تلقائياً: الاشتراكات حسب تاريخ الدفع، والرواتب حسب تاريخ الاستلام (الراتب الذي لم يُستلم بعد يُحسب في الجدول الشهري لشهره). عند تعديل المبلغ يدوياً يتوقف التحديث التلقائي لذلك البند؛ وحفظ ملاحظة فقط لا يغيّره. ما لم يُكتب في هذا الجدول يُجمع تلقائياً من الجداول الأدق (اليومي ثم الأسبوعي)، وما يُكتب هنا يغلب عليها."}),
    h("div", {class:"a-form-grid"}, periodFields),
    h("div", {class:"a-row"}, [h("button", {type:"button", class:"a-btn", text:"تصدير PDF / طباعة", onclick:print})]), msg]);
  load();
  fill = null;
  return h("section", {}, [head, capital, tables]);
}

/* ----------------------------------------------------------- saved staff names */
/* Each saved person can be tied to a platform account (teacher / accountant); the name then belongs to that account. */
function tabEmployees(){
  var msg = h("div", {class:"a-msg", role:"status", "aria-live":"polite"});
  var body = h("div", {});
  var accounts = [];
  var name = h("input", {type:"text", maxlength:"120", placeholder:"الاسم الكامل", autocomplete:"off", required:"required"});
  var job = h("input", {type:"text", maxlength:"80", placeholder:"المسمى الوظيفي (معلمة، مساعدة، سائق...)"});
  var accountNew = h("select", {});
  var salaryNew = accNumber("", {placeholder:"الراتب الشهري المعتاد"});
  var salaryCurNew = accSelect(accCurrencyOptions(false), "SYP");
  accLinkCurrency(salaryCurNew, [salaryNew], msg);
  var form = h("form", {class:"a-form-grid", style:"margin-top:8px"}, [accField("الاسم", name), accField("المسمى الوظيفي", job), accField("الراتب الشهري (يُحفظ ويُملأ تلقائياً)", salaryNew), accField("عملة الراتب", salaryCurNew), accField("حساب الدخول (اختياري)", accountNew),
    h("div", {class:"a-row"}, [h("button", {type:"submit", class:"a-btn sun", text:"＋ حفظ الموظف"})])]);
  function accountOptions(select, current){
    select.innerHTML = "";
    select.appendChild(new Option("— بلا حساب دخول —", ""));
    accounts.forEach(function(a){
      var roleText = a.roles.map(function(r){ return r === "teacher" ? "معلمة" : "محاسب"; }).join(" + ");
      var takenByOther = a.linked_to && a.id !== current;
      var option = new Option(a.username + " (" + roleText + ")" + (takenByOther ? " — مرتبط بـ " + a.linked_to : ""), a.id);
      option.disabled = !!takenByOther;
      select.appendChild(option);
    });
    select.value = current || "";
  }
  form.addEventListener("submit", async function(event){
    event.preventDefault();
    try{
      await request("/api/admin/accounting/employees", {method:"POST", body:JSON.stringify({name:name.value.trim(), job_title:job.value.trim(), account_id:accountNew.value || null, salary:salaryNew.value === "" ? null : salaryNew.value, salary_currency:salaryCurNew.value})});
      name.value = ""; job.value = ""; salaryNew.value = ""; setMsg(msg, "تم حفظ الموظف، وسيظهر اسمه كاقتراح في كل الجداول.", "ok"); await load();
    }catch(error){ setMsg(msg, errText(error), "err"); }
  });
  async function load(){
    accLoadNames();
    body.innerHTML = "";
    try{
      var results = await Promise.all([request("/api/admin/accounting/employees"), request("/api/admin/accounting/staff-accounts")]);
      var list = results[0]; accounts = results[1];
      accountOptions(accountNew, "");
      if(!list.length){ body.appendChild(h("div", {class:"a-empty", text:"لا يوجد موظفون محفوظون بعد."})); return; }
      list.forEach(function(employee){
        var nameInput = h("input", {type:"text", maxlength:"120", value:employee.name, "aria-label":"الاسم"});
        var jobInput = h("input", {type:"text", maxlength:"80", value:employee.job_title, "aria-label":"المسمى الوظيفي"});
        var salaryInput = accNumber(employee.salary, {"aria-label":"الراتب الشهري"});
        var salaryCur = accSelect(accCurrencyOptions(false), employee.salary_currency || "SYP");
        accLinkCurrency(salaryCur, [salaryInput], msg);
        var accountSelect = h("select", {"aria-label":"حساب الدخول"});
        accountOptions(accountSelect, employee.account_id);
        body.appendChild(h("article", {class:"a-child"}, [
          h("div", {class:"a-child-head"}, [employee.account_username ? h("span", {class:"a-tag sun", text:"حساب: " + employee.account_username}) : h("span", {class:"a-tag", text:"بلا حساب دخول"})]),
          h("div", {class:"a-form-grid"}, [accField("الاسم", nameInput), accField("المسمى الوظيفي", jobInput), accField("الراتب الشهري", salaryInput), accField("عملة الراتب", salaryCur), accField("حساب الدخول", accountSelect),
            h("div", {class:"a-row"}, [
              h("button", {type:"button", class:"a-btn sun", text:"حفظ", onclick:async function(){
                try{
                  var saved = await request("/api/admin/accounting/employees/" + encodeURIComponent(employee.id), {method:"PATCH", body:JSON.stringify({name:nameInput.value.trim(), job_title:jobInput.value.trim(), account_id:accountSelect.value || null, salary:salaryInput.value === "" ? null : salaryInput.value, salary_currency:salaryCur.value})});
                  setMsg(msg, "تم الحفظ." + (saved.updated_salary_rows ? " وتحدّث راتب " + saved.updated_salary_rows + " سطر لم يُستلم بعد ليوافق الراتب الجديد." : ""), "ok"); await load(); }
                catch(error){ setMsg(msg, errText(error), "err"); }
              }}),
              twoStep("حذف من القائمة", async function(){
                await request("/api/admin/accounting/employees/" + encodeURIComponent(employee.id), {method:"DELETE"}); setMsg(msg, "أُزيل من القائمة (تبقى سجلات رواتبه القديمة).", "ok"); await load();
              })])])]));
      });
    }catch(error){ body.appendChild(h("p", {class:"a-msg err", text:errText(error)})); }
  }
  load();
  fill = null;
  return h("section", {}, [h("div", {class:"a-card"}, [h("h3", {text:"الموظفون والأسماء المحفوظة"}),
    h("p", {class:"hint", text:"احفظ اسم كل موظف أو مدرّسة مرة واحدة واربطه بحساب دخوله إن وُجد، فيرتبط الاسم بالحساب (ويُعدَّل معه من «حسابات المنصة»). تظهر الأسماء كاقتراحات في الرواتب والجداول."}),
    form, msg]), h("div", {class:"a-card"}, [h("h3", {text:"القائمة"}), body])]);
}
