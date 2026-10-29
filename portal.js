(function () {
  "use strict";

  var root = document.getElementById("portal");
  var portalType = root.dataset.portal;
  var isLogin = portalType === "login";
  var isTeacherPortal = portalType === "teacher";
  var storeKey = isTeacherPortal ? "zm-teacher-session" : "zm-parent-session";
  var langKey = isLogin ? "zm-login-lang" : isTeacherPortal ? "zm-teacher-lang" : "zm-parent-lang";
  var PORTAL_TARGETS = {
    admin: {key: "zm-admin-session", lang: "zm-admin-lang", url: "../admin/"},
    teacher: {key: "zm-teacher-session", lang: "zm-teacher-lang", url: "../teachers/"},
    parent: {key: "zm-parent-session", lang: "zm-parent-lang", url: "../parents/"},
    accountant: {key: "zm-accountant-session", lang: "zm-accountant-lang", url: "../admin/"}
  };
  var token = sessionStorage.getItem(storeKey) || "";
  var lang = localStorage.getItem(langKey) === "en" ? "en" : "ar";
  var profile = null;
  var signupMode = false;
  var requestMode = false;
  var requestForm = {guardian_name: "", email: "", phone: "", child_name: "", child_birth_date: "", relationship_to_child: "", notes: ""};
  var editingReportId = "";
  var teacherControls = null;
  var formState = {username:"", password:"", invitation_code:"", child_id:"", title:"", body:""};
  var loginAlert = "";
  var expiredNotice = false;
  (function readCodeFromLink() {
    var query = new URLSearchParams(window.location.search);
    if (query.get("expired")) { expiredNotice = true; history.replaceState(null, "", window.location.pathname); }
    var code = query.get("code");
    if (!code || !/^[A-Za-z0-9_-]{6,64}$/.test(code)) return;
    signupMode = true;
    formState.invitation_code = code;
    history.replaceState(null, "", window.location.pathname);
  })();
  var apiBase = (window.ZM_API_BASE || (/^(localhost|127.0.0.1)$/.test(location.hostname) ? "http://127.0.0.1:8001" : "https://zahra-123hub-almadain-api.onrender.com")).replace(/\/+$/, "");
  var copy = {
    ar: {
      parentTitle: "بوابة أولياء الأمور", teacherTitle: "بوابة المعلمات",
      publishSite: "النشر على الموقع (صور، فيديو، أخبار)",      finishTitle: "إكمال التسجيل: أنشئي حسابك", finishHint: "أدخلي رمز التسجيل الذي وصلك، ثم اختاري اسم مستخدم وكلمة مرور لحسابك.",
      newUsername: "اختاري اسم مستخدم", usernameRule: "أحرف إنجليزية وأرقام و . _ - فقط، 3 أحرف على الأقل.",
      newPassword: "اختاري كلمة مرور", passwordRule: "12 حرفاً على الأقل.", confirmPassword: "أعيدي كتابة كلمة المرور",
      passwordMismatch: "كلمتا المرور غير متطابقتين.", accountantTitle: "المحاسبة (الاشتراكات والرسوم)", chooseTitle: "اختر البوابة",
      showPassword: "إظهار", hidePassword: "إخفاء", capsOn: "مفتاح الأحرف الكبيرة (Caps Lock) مفعّل.",
      strengthWeak: "ضعيفة", strengthMedium: "متوسطة", strengthStrong: "قوية", strengthLabel: "قوة كلمة المرور",
      ruleLength: "12 حرفاً على الأقل", ruleCommon: "ليست كلمة مرور شائعة", ruleUser: "لا تحتوي على اسم المستخدم", ruleVariety: "متنوّعة الأحرف وليست أرقاماً فقط",
      changePassword: "تغيير كلمة المرور", currentPassword: "كلمة المرور الحالية", repeatPassword: "أعيدي كتابة كلمة المرور الجديدة",
      passwordChanged: "تم تغيير كلمة المرور، وأُنهيت جلساتك الأخرى.", sessionExpired: "انتهت جلستك بعد فترة من عدم النشاط. سجّلي الدخول من جديد.",
      cancel: "إلغاء", save: "حفظ",
      chooseHint: "حسابك يملك أكثر من صلاحية. إلى أين تريد الدخول؟", switchPortal: "تبديل البوابة",
      loginTitle: "تسجيل الدخول", loginIntro: "ادخلي ببياناتك، وسننقلك تلقائياً إلى بوابتك حسب نوع حسابك.",
      school: "روضة زهرة المدائن", parentWelcome: "تابع التقارير اليومية المنشورة لأطفالك.",
      teacherWelcome: "أنشئي مسودات التقارير وأرسليها للمراجعة. لن تظهر للأهل حتى اعتمادها.",
      login: "تسجيل الدخول", signup: "إنشاء حساب بدعوة", username: "اسم المستخدم",
      password: "كلمة المرور", invite: "رمز التسجيل الذي وصلك بعد موافقة الروضة",
      switchRequest: "ليس لديك حساب؟ قدّمي طلب تسجيل",
      requestTitle: "طلب تسجيل ولي أمر",
      requestHint: "أدخلي بياناتك وبيانات طفلك. تراجع الإدارة الطلب، وعند الموافقة يصلك رمز تسجيل لمرة واحدة لإكمال إنشاء الحساب.",
      guardianName: "اسم ولي الأمر الكامل", email: "البريد الإلكتروني", phone: "رقم الهاتف",
      childName: "اسم الطفل", childBirth: "تاريخ ميلاد الطفل", relationship: "صلة القرابة (أم، أب...)",
      notes: "ملاحظات (اختياري)", sendRequest: "إرسال الطلب",
      requestSent: "تم استلام طلبك. ستراجعه إدارة الروضة، وسيصلك رمز التسجيل عند الموافقة.",
      accountReadyNotice: "تم إنشاء الحساب وتفعيله. يمكنك تسجيل الدخول الآن.",
      language: "اللغة", signIn: "دخول", createAccount: "إنشاء الحساب",
      switchSignup: "وصلك رمز التسجيل؟ أكملي إنشاء الحساب", switchLogin: "لديك حساب؟ تسجيل الدخول",
      logout: "تسجيل الخروج", children: "الأطفال", reports: "التقارير اليومية",
      noChildren: "لا توجد ملفات أطفال مرتبطة بهذا الحساب بعد.",
      portalTagline: "مساحة آمنة لمتابعة رحلة طفلك التعليمية.",
      secureAccess: "دخول آمن إلى حسابك",
      parentPortalIntro: "تابع تقارير طفلك المنشورة واطّلع على تقدّمه من مكان واحد.",
      teacherPortalIntro: "أدِر تقارير الأطفال المعيّنين لك وموادك التعليمية من حسابك.",
      accountLabel: "الحساب",
      activeAccount: "حساب مفعّل",
      welcomeUser: "مرحباً",
      portalOverview: "لوحة المتابعة",
      signInHint: "استخدمي بيانات الحساب التي زوّدتك بها الروضة.",
      parentSignupHint: "قدّمي طلب تسجيل أولاً. بعد موافقة الإدارة يصلك رمز لمرة واحدة لإكمال إنشاء حسابك.",
      approvalPendingNotice: "تم إنشاء الحساب. يمكنك الدخول بعد موافقة إدارة الروضة على تفعيله.",
      pendingAccount: "حسابك بانتظار موافقة إدارة الروضة. جرّبي تسجيل الدخول بعد تفعيله.",
      disabledAccount: "الحساب موقوف حالياً. يرجى التواصل مع إدارة الروضة.",
      error: "خطأ",
      noReports: "لا توجد تقارير منشورة بعد.", loading: "جارٍ التحميل…",
      serviceUnavailable: "بوابة الحسابات غير مهيأة بعد. يلزم إعداد قاعدة البيانات وترحيلها قبل تسجيل الدخول.",
      genericError: "تعذر إكمال الطلب. حاول مرة أخرى.",
      title: "عنوان التقرير", body: "ملخص اليوم", child: "الطفل",
      selectChild: "اختاري طفلاً", saveDraft: "حفظ كمسودة", submit: "إرسال للمراجعة",
      reportSaved: "تم حفظ التقرير.", reportSent: "أرسل التقرير للمراجعة.",
      status: "الحالة", draft: "مسودة", submitted: "بانتظار المراجعة",
      published: "منشور للأهل", rejected: "يحتاج تعديلاً", archived: "مؤرشف",
      review: "تقارير بانتظار المراجعة", approve: "نشر للأهل", reject: "إرجاع للتعديل",
      noReview: "لا توجد تقارير بانتظار المراجعة.", accessDenied: "هذا الحساب لا يملك صلاحية هذه البوابة.",
      notAssigned: "لم تُسند إليك ملفات أطفال بعد.", backToWebsite: "العودة إلى الموقع",
      privacy: "لا تكتبي معلومات طبية أو حساسة في هذه التقارير. لا ترفعي صوراً خاصة هنا.",
      signInFirst: "سجّلي الدخول أولاً.", originalLanguage: "محتوى التقرير بلغته الأصلية؛ لا تتوفر ترجمة له بعد.",
      edit: "تعديل المسودة", reportUpdated: "تم تحديث التقرير.", cancelEdit: "إلغاء التعديل",
      teacherFiles: "ملفاتي التعليمية", teacherFilesHelp: "الملفات خاصة بك وبإدارة الروضة فقط. يمكنك رفع أي نوع ملف عدا البرامج وصفحات الويب. PDF حتى 20 ميغابايت، والصور حتى 10، والفيديو حتى 25، وغيرها حتى 50 ميغابايت. الحد الإجمالي 250 ميغابايت.",
      other: "أي ملف (وورد، إكسل، عرض تقديمي، مضغوط...)", uploadFile: "رفع ملف", uploadType: "نوع الملف", document: "مادة أو مستند PDF",
      image: "صورة", video: "فيديو", chooseFile: "اختاري ملفاً", fileUploaded: "تم رفع الملف بشكل خاص.",
      postTitle: "العنوان", postBody: "النص (اختياري إذا أرفقتِ ملفاً)",
      postsComposeTitle: "نشر للأهل",
      postsComposeHelp: "اختاري نوع المنشور: عام يراه كل أولياء الأمور، أو خاص بطفل (علامات، ملاحظات) لا يراه إلا أهل هذا الطفل. يظهر المنشور للأهل فور نشره.",
      scopeLabel: "نوع المنشور", scopeGeneral: "عام — يراه جميع أولياء الأمور", scopeChild: "خاص بطفل — يراه أهل هذا الطفل فقط",
      scopeGeneralBadge: "عام", scopePrivateBadge: "خاص", postFiles: "مرفقات (حتى 5 ملفات)", publishPost: "نشر الآن",
      postPublished: "تم النشر وهو ظاهر للأهل الآن.", myPosts: "منشوراتي", allPosts: "كل المنشورات", noPosts: "لا توجد منشورات بعد.",
      postsForYou: "منشورات الروضة", noPostsParent: "لا توجد منشورات بعد.", deletePostConfirm: "حذف هذا المنشور نهائياً؟",
      noAssignedChildren: "لا يوجد أطفال معيّنون لك بعد لإرسال منشور خاص.",
      noTeacherFiles: "لم ترفعي ملفات بعد.", deleteFile: "حذف", fileDeleted: "تم حذف الملف.",
      downloadFile: "تنزيل", reportAttachments: "مرفقات التقرير (خاصة بالمعلمة والإدارة)",
      reportAttachmentsHelp: "يمكن إرفاق حتى 5 ملفات PDF أو صور أو فيديوهات. لن تظهر هذه المرفقات للأهل.",
      report_attachment: "مرفق تقرير", noAttachments: "لا توجد مرفقات.",
      storageLimit: "تجاوز حجم الملف أو مساحة التخزين المتاحة."
    },
    en: {
      parentTitle: "Parents' portal", teacherTitle: "Teachers' portal",
      publishSite: "Publish to website (photos, videos, news)",      finishTitle: "Finish registration: create your account", finishHint: "Enter the registration code you received, then choose a username and password for your account.",
      newUsername: "Choose a username", usernameRule: "English letters, digits and . _ - only, at least 3 characters.",
      newPassword: "Choose a password", passwordRule: "At least 12 characters.", confirmPassword: "Repeat the password",
      passwordMismatch: "The two passwords do not match.", accountantTitle: "Accounting (fees and payroll)", chooseTitle: "Choose a portal",
      showPassword: "Show", hidePassword: "Hide", capsOn: "Caps Lock is on.",
      strengthWeak: "Weak", strengthMedium: "Fair", strengthStrong: "Strong", strengthLabel: "Password strength",
      ruleLength: "At least 12 characters", ruleCommon: "Not a common password", ruleUser: "Does not contain the username", ruleVariety: "Varied characters, not only digits",
      changePassword: "Change password", currentPassword: "Current password", repeatPassword: "Repeat the new password",
      passwordChanged: "Password changed. Your other sessions were signed out.", sessionExpired: "Your session ended after a period of inactivity. Please sign in again.",
      cancel: "Cancel", save: "Save",
      chooseHint: "Your account has more than one role. Where do you want to go?", switchPortal: "Switch portal",
      loginTitle: "Sign in", loginIntro: "Sign in and we will take you to the right portal for your account.",
      school: "Zahrat Al-Madayn Kindergarten", parentWelcome: "View the published daily reports for your children.",
      teacherWelcome: "Save reports as drafts or submit them for review. Families will not see them until approved.",
      login: "Sign in", signup: "Join with an invitation", username: "Username",
      password: "Password", invite: "Registration code you received after approval",
      switchRequest: "No account yet? Request registration",
      requestTitle: "Parent registration request",
      requestHint: "Enter your details and your child's. The kindergarten reviews the request and, once approved, sends you a one-time registration code to finish creating your account.",
      guardianName: "Guardian's full name", email: "Email address", phone: "Phone number",
      childName: "Child's name", childBirth: "Child's date of birth", relationship: "Relationship (mother, father...)",
      notes: "Notes (optional)", sendRequest: "Submit request",
      requestSent: "Your request was received. The kindergarten will review it and send you a registration code once approved.",
      accountReadyNotice: "Your account is ready. You can sign in now.",
      language: "Language", signIn: "Sign in", createAccount: "Create account",
      switchSignup: "Got your registration code? Finish signing up", switchLogin: "Already registered? Sign in",
      logout: "Sign out", children: "Children", reports: "Daily reports",
      noChildren: "No child profiles are linked to this account yet.",
      portalTagline: "A secure space to follow your child's learning journey.",
      secureAccess: "Secure account access",
      parentPortalIntro: "View your child's published reports and follow their progress in one place.",
      teacherPortalIntro: "Manage reports for your assigned children and your learning materials.",
      accountLabel: "Account",
      activeAccount: "Active account",
      welcomeUser: "Welcome",
      portalOverview: "Overview",
      signInHint: "Use the account details provided by the kindergarten.",
      parentSignupHint: "Submit a registration request first. After the kindergarten approves it you receive a one-time code to finish creating your account.",
      approvalPendingNotice: "Your account has been created. Sign in after the kindergarten administrator approves it.",
      pendingAccount: "Your account is awaiting kindergarten administrator approval. Try signing in again after it is activated.",
      disabledAccount: "This account is currently disabled. Please contact the kindergarten administration.",
      error: "Error",
      noReports: "No published reports yet.", loading: "Loading…",
      serviceUnavailable: "The account portal is not configured yet. A database and migrations are required before sign-in.",
      genericError: "The request could not be completed. Please try again.",
      title: "Report title", body: "Daily summary", child: "Child",
      selectChild: "Select a child", saveDraft: "Save draft", submit: "Submit for review",
      reportSaved: "Report saved.", reportSent: "Report submitted for review.",
      status: "Status", draft: "Draft", submitted: "Awaiting review",
      published: "Published for parents", rejected: "Needs revision", archived: "Archived",
      review: "Reports awaiting review", approve: "Publish for parents", reject: "Return for revision",
      noReview: "No reports are waiting for review.", accessDenied: "This account does not have access to this portal.",
      notAssigned: "No child profiles have been assigned to you yet.", backToWebsite: "Back to website",
      privacy: "Do not include medical or sensitive details in these reports. Do not upload private photos here.",
      signInFirst: "Please sign in first.", originalLanguage: "This report is shown in its original language; no translation is available yet.",
      edit: "Edit draft", reportUpdated: "Report updated.", cancelEdit: "Cancel edit",
      teacherFiles: "My learning files", teacherFilesHelp: "Files are private to you and kindergarten admins. Any file type except programs and web pages. PDF up to 20 MB, images up to 10 MB, videos up to 25 MB, other files up to 50 MB. Total storage limit: 250 MB.",
      other: "Any file (Word, Excel, slides, zip...)", uploadFile: "Upload file", uploadType: "File type", document: "Learning material or PDF",
      image: "Image", video: "Video", chooseFile: "Choose a file", fileUploaded: "File uploaded privately.",
      postTitle: "Title", postBody: "Message (optional if you attach a file)",
      postsComposeTitle: "Post to parents",
      postsComposeHelp: "Choose the post type: General is seen by all parents; Private to one child (grades, remarks) is seen only by that child's parents. Posts are visible to families as soon as you publish.",
      scopeLabel: "Post type", scopeGeneral: "General — all parents can see it", scopeChild: "Private to one child — only that child's parents",
      scopeGeneralBadge: "General", scopePrivateBadge: "Private", postFiles: "Attachments (up to 5 files)", publishPost: "Publish now",
      postPublished: "Published. Families can see it now.", myPosts: "My posts", allPosts: "All posts", noPosts: "No posts yet.",
      postsForYou: "Kindergarten posts", noPostsParent: "No posts yet.", deletePostConfirm: "Delete this post permanently?",
      noAssignedChildren: "No children are assigned to you yet for private posts.",
      noTeacherFiles: "You have not uploaded any files yet.", deleteFile: "Delete", fileDeleted: "File deleted.",
      downloadFile: "Download", reportAttachments: "Report attachments (private to teacher and admins)",
      reportAttachmentsHelp: "Attach up to 5 PDFs, images or videos. Parents will not see these attachments.",
      report_attachment: "Report attachment", noAttachments: "No attachments.",
      storageLimit: "The file exceeds its size or storage limit."
    }
  };
  var API_ERROR = {
    "Child profile not found.": {ar: "لم يُعثر على ملف الطفل، أو ليس معيّناً لك.", en: "Child profile not found or not assigned to you."},
    "A title is required.": {ar: "العنوان مطلوب.", en: "A title is required."},
    "Write a message or attach a file.": {ar: "اكتبي رسالة أو أرفقي ملفاً.", en: "Write a message or attach a file."},
    "Select the child this private post is for.": {ar: "اختاري الطفل الذي يخصه هذا المنشور.", en: "Select the child this private post is for."},
    "A post can have up to five files.": {ar: "يمكن إرفاق 5 ملفات كحد أقصى.", en: "A post can have up to five files."},
    "Platform sessions are not configured on the server.": {
      ar: "بوابة الحسابات غير مهيأة بعد. يلزم إعداد قاعدة البيانات وترحيلها قبل تسجيل الدخول.",
      en: "The account portal is not configured yet. A database and migrations are required before sign-in."
    },
    "A request for this email is already awaiting review.": {ar:"يوجد طلب بهذا البريد بانتظار المراجعة بالفعل.",en:"A request for this email is already awaiting review."},
    "Too many requests. Try again later.": {ar:"طلبات كثيرة. حاولي لاحقاً.",en:"Too many requests. Try again later."},
    "The invitation is invalid, expired, or already used.": {ar:"رمز التسجيل غير صالح أو منتهي أو مستخدم من قبل.",en:"The registration code is invalid, expired or already used."},
    "That username is already in use.": {ar:"اسم المستخدم مستخدم بالفعل.",en:"That username is already in use."},
    "Too many sign-in attempts. Try again later.": {ar:"محاولات دخول كثيرة. حاولي مجدداً بعد 15 دقيقة.",en:"Too many sign-in attempts. Try again in 15 minutes."},
    "Password is too short.": {ar:"كلمة المرور قصيرة (12 حرفاً على الأقل).",en:"The password is too short (at least 12 characters)."},
    "Password is too common or too easy to guess.": {ar:"كلمة المرور شائعة وسهلة التخمين. اختاري كلمة أصعب.",en:"This password is too common or easy to guess. Choose a harder one."},
    "Password must not contain the username.": {ar:"يجب ألا تحتوي كلمة المرور على اسم المستخدم.",en:"The password must not contain the username."},
    "Password must not be only digits.": {ar:"يجب ألا تكون كلمة المرور أرقاماً فقط.",en:"The password must not be only digits."},
    "Password needs at least 6 different characters.": {ar:"استخدمي 6 محارف مختلفة على الأقل.",en:"Use at least 6 different characters."},
    "The current password is incorrect.": {ar:"كلمة المرور الحالية غير صحيحة.",en:"The current password is incorrect."},
    "Choose a new password that differs from the current one.": {ar:"اختاري كلمة مرور جديدة تختلف عن الحالية.",en:"Choose a new password that differs from the current one."},
    "Sign in to the platform.": {ar:"سجّلي الدخول أولاً.",en:"Please sign in first."},
    "Your platform session expired. Sign in again.": {ar:"انتهت الجلسة. سجّلي الدخول مرة أخرى.",en:"Your session expired. Sign in again."},
    "Your platform session is no longer valid.": {ar:"انتهت الجلسة. سجّلي الدخول مرة أخرى.",en:"Your session is no longer valid. Sign in again."},
    "You do not have permission to perform this action.": {ar:"هذا الحساب لا يملك صلاحية هذه البوابة.",en:"This account does not have permission to access this portal."},
    "This account cannot view child profiles.": {ar:"هذا الحساب لا يملك صلاحية عرض ملفات الأطفال.",en:"This account cannot view child profiles."},
    "Assigned child not found.": {ar:"الطفل غير موجود ضمن الملفات المسندة إليك.",en:"That child is not assigned to you."},
    "Report title and text are required.": {ar:"أدخلي عنوان التقرير والنص.",en:"A report title and text are required."},
    "Your account is awaiting administrator approval.": {ar:"حسابك بانتظار موافقة إدارة الروضة. جرّبي تسجيل الدخول بعد تفعيله.",en:"Your account is awaiting kindergarten administrator approval. Try signing in again after it is activated."},
    "Your account has been disabled. Contact the kindergarten.": {ar:"الحساب موقوف حالياً. يرجى التواصل مع إدارة الروضة.",en:"This account is currently disabled. Please contact the kindergarten administration."},
    "The file exceeds the size limit for its type.": {ar:"حجم الملف أكبر من الحد المسموح لنوعه.",en:"The file is larger than the limit for its type."},
    "The teacher account has reached its 250 MB storage limit.": {ar:"وصل حساب المعلمة إلى الحد الأقصى للتخزين وهو 250 ميغابايت.",en:"The teacher account has reached its 250 MB storage limit."},
    "A report can have up to five attachments.": {ar:"يمكن إرفاق خمسة ملفات كحد أقصى بالتقرير الواحد.",en:"A report can have up to five attachments."},
    "Only PDF, JPG, PNG, WebP, MP4, and WebM files are allowed.": {ar:"الملفات المسموحة هي PDF وJPG وPNG وWebP وMP4 وWebM فقط.",en:"Only PDF, JPG, PNG, WebP, MP4 and WebM files are allowed."},
    "Executable and web-page files are not allowed.": {ar:"لا يُسمح برفع الملفات التنفيذية أو صفحات الويب.",en:"Executable and web-page files are not allowed."},
    "The uploaded file contents do not match its file type.": {ar:"محتوى الملف لا يطابق نوعه.",en:"The uploaded file contents do not match its file type."},
    "The file exceeds its size or storage limit.": {ar:"تجاوز الملف الحد المسموح للحجم أو التخزين.",en:"The file exceeds its size or storage limit."}
  };
  var t = function (key) { return copy[lang][key] || key; };
  /* ---- password helpers: strength meter, show/hide, Caps Lock warning ---- */
  var COMMON_PASSWORDS = ["password", "passw0rd", "qwertyuiop", "qwerty", "asdfghjkl", "zxcvbnm", "iloveyou", "welcome", "letmein", "admin", "administrator",
    "changeme", "abc123", "123456789012", "1234567890", "zahra", "zahrat", "zahratalmadain", "almadain", "kindergarten", "damascus", "syria"];
  function passwordRules(pw, user) {
    var lowered = pw.toLowerCase().replace(/\s/g, "");
    var stripped = lowered.replace(/[0-9!@#$%^&*._-]+$/, "");
    var common = COMMON_PASSWORDS.indexOf(lowered) !== -1 || COMMON_PASSWORDS.indexOf(stripped) !== -1;
    var uniq = {}; pw.split("").forEach(function (c) { uniq[c] = true; });
    return [
      {ok: pw.length >= 12, label: t("ruleLength")},
      {ok: pw.length > 0 && !common, label: t("ruleCommon")},
      {ok: pw.length > 0 && !(user && user.length >= 3 && lowered.indexOf(user) !== -1), label: t("ruleUser")},
      {ok: pw.length > 0 && !/^\d+$/.test(pw) && Object.keys(uniq).length >= 6, label: t("ruleVariety")}
    ];
  }
  function strengthMeter(input, getUser, container) {
    var box = element("div", "p-meter");
    var bar = element("div", "p-meter-bar");
    var fill = element("span");
    bar.appendChild(fill);
    var caption = element("small", "p-meter-text");
    var list = element("ul", "p-rules");
    box.appendChild(bar); box.appendChild(caption); box.appendChild(list);
    function update() {
      var pw = input.value;
      var rules = passwordRules(pw, getUser());
      var passed = rules.filter(function (r) { return r.ok; }).length;
      var classes = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter(function (re) { return re.test(pw); }).length;
      var score = passed === rules.length ? (pw.length >= 16 && classes >= 3 ? 3 : 2) : (passed >= 3 ? 1 : 0);
      fill.style.width = (pw ? (score + 1) * 25 : 0) + "%";
      box.className = "p-meter level-" + (pw ? score : "none");
      caption.textContent = pw ? t("strengthLabel") + ": " + t(score >= 3 ? "strengthStrong" : score === 2 ? "strengthMedium" : "strengthWeak") : "";
      list.innerHTML = "";
      rules.forEach(function (r) { var li = element("li", r.ok ? "ok" : "", (r.ok ? "✓ " : "• ") + r.label); list.appendChild(li); });
    }
    input.addEventListener("input", update);
    update();
    container.appendChild(box);
    return update;
  }
  function decoratePassword(label, input) {
    var toggle = element("button", "p-eye", t("showPassword"));
    toggle.type = "button";
    toggle.addEventListener("click", function () {
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      toggle.textContent = show ? t("hidePassword") : t("showPassword");
    });
    var caps = element("small", "p-caps", t("capsOn"));
    caps.hidden = true;
    function checkCaps(event) { caps.hidden = !(event.getModifierState && event.getModifierState("CapsLock")); }
    input.addEventListener("keydown", checkCaps);
    input.addEventListener("keyup", checkCaps);
    input.addEventListener("blur", function () { caps.hidden = true; });
    label.appendChild(toggle);
    label.appendChild(caps);
  }
  function toggleChangePassword() {
    var main = root.querySelector("main");
    if (!main) return;
    var existing = main.querySelector(".p-change-password");
    if (existing) { existing.remove(); return; }
    var card = element("section", "p-card p-change-password");
    card.appendChild(element("h2", "", t("changePassword")));
    var form = element("form");
    function secret(labelText, autocomplete) {
      var wrap = element("div", "p-field");
      var label = element("label", "", labelText);
      var input = element("input");
      input.type = "password"; input.required = true; input.autocomplete = autocomplete;
      label.appendChild(input); wrap.appendChild(label); form.appendChild(wrap);
      decoratePassword(label, input);
      return input;
    }
    var current = secret(t("currentPassword"), "current-password");
    var fresh = secret(t("password"), "new-password");
    strengthMeter(fresh, function () { return (profile && profile.username || "").toLowerCase(); }, fresh.parentNode.parentNode);
    var again = secret(t("repeatPassword"), "new-password");
    var message = element("p", "p-alert");
    message.setAttribute("role", "alert");
    var save = element("button", "p-button sun", t("save"));
    save.type = "submit";
    var cancel = button(t("cancel"), "outline", function () { card.remove(); });
    form.appendChild(save); form.appendChild(cancel); form.appendChild(message);
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      message.className = "p-alert error";
      if (fresh.value !== again.value) { message.textContent = t("passwordMismatch"); return; }
      save.disabled = true;
      request("/api/platform/auth/change-password", {method: "POST", body: JSON.stringify({current_password: current.value, new_password: fresh.value})}).then(function () {
        current.value = fresh.value = again.value = "";
        message.className = "p-alert success";
        message.textContent = t("passwordChanged");
      }).catch(function (error) { message.textContent = errorMessage(error); }).finally(function () { save.disabled = false; });
    });
    card.appendChild(form);
    main.insertBefore(card, main.firstChild);
    current.focus();
  }
  function portalLabel(name) {
    return name === "teacher" ? t("teacherTitle") : name === "parent" ? t("parentTitle") : name === "accountant" ? t("accountantTitle") : name;
  }
  function otherPortals() {
    var list = [];
    try { list = JSON.parse(sessionStorage.getItem("zm-portals") || "[]"); } catch (e) {}
    var current = isTeacherPortal ? "teacher" : "parent";
    return list.filter(function (name) { return name !== current && PORTAL_TARGETS[name] && name !== "admin"; });
  }
  function portalTitle() { return isLogin ? t("loginTitle") : isTeacherPortal ? t("teacherTitle") : t("parentTitle"); }
  var element = function (tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  function setLanguage(next) {
    lang = next === "en" ? "en" : "ar";
    localStorage.setItem(langKey, lang);
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    if (token) {
      request("/api/platform/auth/language", {
        method: "PATCH",
        body: JSON.stringify({language: lang})
      }).catch(function (error) { loginAlert = errorMessage(error); });
    }
    render();
  }
  function button(label, className, onClick) {
    var node = element("button", "p-button " + (className || ""), label);
    node.type = "button";
    node.addEventListener("click", onClick);
    return node;
  }
  function request(path, options) {
    options = options || {};
    var headers = new Headers(options.headers || {});
    if (token) headers.set("Authorization", "Bearer " + token);
    var isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
    if (options.body && !isFormData && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    return fetch(apiBase + path, Object.assign({}, options, {headers: headers})).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (body) {
        if (!response.ok) throw new Error(body.detail || t("genericError"));
        return body;
      });
    });
  }
  function errorMessage(error) {
    var localized = API_ERROR[error.message];
    if (localized) return localized[lang];
    if (error instanceof TypeError) return t("serviceUnavailable");
    return error.message || t("genericError");
  }
  function header() {
    var bar = element("header", "p-header");
    var inner = element("div", "p-header-inner");
    var brand = element("a", "p-brand");
    brand.href = "/";
    var logo = element("img");
    logo.src = "../images/logo.png?v=2";
    logo.alt = "";
    brand.appendChild(logo);
    var brandText = element("div");
    brandText.appendChild(element("h1", "", portalTitle()));
    brandText.appendChild(element("span", "", t("school")));
    brand.appendChild(brandText);
    inner.appendChild(brand);
    var actions = element("div", "p-actions");
    if (profile) {
      var identity = element("div", "p-account-identity");
      actions.appendChild(element("span", "p-avatar", (profile.username || "?").charAt(0).toUpperCase()));
      identity.appendChild(element("span", "p-account-label", t("welcomeUser")));
      identity.appendChild(element("strong", "", profile.username));
      actions.appendChild(identity);
    }
    var langGroup = element("div", "p-lang");
    langGroup.setAttribute("role", "group");
    langGroup.setAttribute("aria-label", t("language"));
    [["ar", "العربية"], ["en", "English"]].forEach(function (choice) {
      var languageButton = element("button", "", choice[1]);
      languageButton.lang = choice[0];
      languageButton.type = "button";
      languageButton.setAttribute("aria-pressed", String(lang === choice[0]));
      languageButton.addEventListener("click", function () { setLanguage(choice[0]); });
      langGroup.appendChild(languageButton);
    });
    actions.appendChild(langGroup);
    if (token && !isLogin) {
      otherPortals().forEach(function (name) {
        var other = element("a", "p-button outline", portalLabel(name));
        other.href = PORTAL_TARGETS[name].url;
        other.title = t("switchPortal");
        actions.appendChild(other);
      });
    }
    if (token && profile && !isLogin) actions.appendChild(button(t("changePassword"), "outline", toggleChangePassword));
    if (token && isTeacherPortal) {
      var publishLink = element("a", "p-button sun", t("publishSite"));
      publishLink.href = "../admin/";
      actions.appendChild(publishLink);
    }
    if (token) actions.appendChild(button(t("logout"), "outline", logout));
    inner.appendChild(actions);
    bar.appendChild(inner);
    return bar;
  }
  function shell() {
    root.innerHTML = "";
    root.appendChild(header());
    var main = element("main", "p-main");
    root.appendChild(main);
    return main;
  }
  function showError(container, error) {
    var msg = element("p", "p-alert error", errorMessage(error));
    msg.setAttribute("role", "alert");
    container.appendChild(msg);
  }
  function loginScreen() {
    if (!isLogin) { window.location.replace("../login/"); return; }
    if (expiredNotice) { loginAlert = t("sessionExpired"); expiredNotice = false; }
    var main = shell();
    main.classList.add("p-auth-main");
    var layout = element("div", "p-auth-layout");
    var intro = element("section", "p-auth-intro");
    intro.appendChild(element("span", "p-auth-kicker", t("secureAccess")));
    intro.appendChild(element("h2", "", portalTitle()));
    intro.appendChild(element("p", "", isLogin ? t("loginIntro") : isTeacherPortal ? t("teacherPortalIntro") : t("parentPortalIntro")));
    intro.appendChild(element("div", "p-auth-note", isTeacherPortal ? t("signInHint") : t("parentSignupHint")));
    layout.appendChild(intro);
    var card = element("section", "p-card p-auth-card");
    card.appendChild(element("h2", "", portalTitle()));
    card.appendChild(element("p", "p-subtitle", t("signInHint")));
    var error = element("p", "p-alert error");
    error.setAttribute("role", "alert");
    function drawForm() {
      card.querySelectorAll("form,.p-form-switch,.p-alert").forEach(function (node) { node.remove(); });
      if (requestMode) { drawRequestForm(); return; }
      var form = element("form");
      var username = field(signupMode ? t("newUsername") : t("username"), "text", "username");
      username.autocomplete = "username";
      if (signupMode) { username.pattern = "[A-Za-z0-9_.\-]{3,80}"; username.dir = "ltr"; username.autocapitalize = "none"; }
      username.required = true;
      username.minLength = 3;
      username.value = formState.username;
      username.addEventListener("input", function () { formState.username = username.value; });
      var password = field(signupMode ? t("newPassword") : t("password"), "password", signupMode ? "new-password" : "current-password");
      password.required = true;
      password.minLength = signupMode ? 12 : 1;
      password.value = formState.password;
      password.addEventListener("input", function () { formState.password = password.value; });
      form.appendChild(username.parentNode.parentNode);
      form.appendChild(password.parentNode.parentNode);
      var invite = null;
      var confirm = null;
      if (signupMode) {
        invite = field(t("invite"), "text", "off");
        invite.required = true;
        invite.minLength = 6;
        invite.maxLength = 64;
        invite.dir = "ltr";
        invite.placeholder = "XXXX-XXXX";
        invite.style.textTransform = "uppercase";
        invite.style.letterSpacing = ".12em";
        invite.value = formState.invitation_code;
        invite.addEventListener("input", function () { formState.invitation_code = invite.value; });
        form.insertBefore(invite.parentNode.parentNode, username.parentNode.parentNode);
        username.parentNode.appendChild(element("small", "p-muted", t("usernameRule")));
        password.parentNode.appendChild(element("small", "p-muted", t("passwordRule")));
        strengthMeter(password, function () { return username.value.trim().toLowerCase(); }, password.parentNode);
        confirm = field(t("confirmPassword"), "password", "new-password");
        confirm.required = true;
        confirm.minLength = 12;
        form.appendChild(confirm.parentNode.parentNode);
        var heading = element("div", "p-finish-intro");
        heading.appendChild(element("h3", "", t("finishTitle")));
        heading.appendChild(element("p", "p-muted", t("finishHint")));
        form.insertBefore(heading, form.firstChild);
      }
      var submit = element("button", "p-button sun", signupMode ? t("createAccount") : t("signIn"));
      submit.type = "submit";
      form.appendChild(submit);
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        error.textContent = "";
        if (signupMode && password.value !== confirm.value) { error.className = "p-alert error"; error.textContent = t("passwordMismatch"); return; }
        submit.disabled = true;
        var path = signupMode ? "/api/platform/auth/redeem-invitation" : isLogin ? "/api/auth/entry" : "/api/platform/auth/login";
        var payload = {username: username.value.trim(), password: password.value};
        if (signupMode) {
          payload.invitation_code = invite.value.trim();
          payload.preferred_language = lang;
        }
        request(path, {method: "POST", body: JSON.stringify(payload)}).then(function (result) {
          if (signupMode) {
            var chosen = {username: username.value.trim(), password: password.value};
            signupMode = false;
            formState.password = "";
            formState.invitation_code = "";
            if (result.approval_status === "active" && isLogin) {
              // The code was issued by the kindergarten, so the account is ready: sign in right away.
              return request("/api/auth/entry", {method: "POST", body: JSON.stringify(chosen)}).then(enterPortals);
            }
            loginAlert = result.approval_status === "active" ? t("accountReadyNotice") : t("approvalPendingNotice");
            drawForm();
            return;
          }
          formState.password = "";
          if (isLogin) {
            enterPortals(result);
            return;
          }
          token = result.access_token;
          sessionStorage.setItem(storeKey, token);
          return loadDashboard();
        }).catch(function (err) {
          error.textContent = errorMessage(err);
          submit.disabled = false;
        });
      });
      card.appendChild(form);
      card.appendChild(error);
      if (loginAlert) {
        error.className = "p-alert success";
        error.textContent = loginAlert;
        loginAlert = "";
      }
      if (!isTeacherPortal) {
        card.appendChild(button(signupMode ? t("switchLogin") : t("switchSignup"), "outline p-form-switch", function () {
          signupMode = !signupMode;
          error.className = "p-alert error";
          drawForm();
        }));
        card.appendChild(button(t("switchRequest"), "outline p-form-switch", function () {
          requestMode = true;
          signupMode = false;
          error.className = "p-alert error";
          drawForm();
        }));
      }
    }
    function drawRequestForm() {
      var form = element("form");
      var openedAt = Date.now();
      var trap = element("input");  // humans never see or fill this field; bots do
      trap.type = "text"; trap.name = "website"; trap.tabIndex = -1; trap.autocomplete = "off";
      trap.setAttribute("aria-hidden", "true");
      trap.style.cssText = "position:absolute;left:-9999px;width:1px;height:1px;opacity:0";
      form.appendChild(trap);
      form.appendChild(element("h3", "", t("requestTitle")));
      form.appendChild(element("p", "p-muted", t("requestHint")));
      var inputs = {};
      [
        ["guardian_name", "guardianName", "text", "name", true],
        ["email", "email", "email", "email", true],
        ["phone", "phone", "tel", "tel", true],
        ["child_name", "childName", "text", "off", true],
        ["child_birth_date", "childBirth", "date", "off", false],
        ["relationship_to_child", "relationship", "text", "off", false],
        ["notes", "notes", "textarea", "off", false]
      ].forEach(function (spec) {
        var wrap = element("div", "p-field");
        var label = element("label", "", t(spec[1]));
        var input = element(spec[2] === "textarea" ? "textarea" : "input");
        if (spec[2] === "textarea") { input.rows = 3; input.maxLength = 1000; input.style.minHeight = "90px"; }
        else { input.type = spec[2]; }
        input.autocomplete = spec[3];
        input.required = spec[4];
        if (spec[0] === "guardian_name" || spec[0] === "child_name") input.minLength = 2;
        if (spec[0] === "phone") { input.minLength = 6; input.pattern = "[0-9+()\\-\\s]{6,40}"; input.dir = "ltr"; }
        if (spec[0] === "email") input.dir = "ltr";
        input.value = requestForm[spec[0]];
        input.addEventListener("input", function () { requestForm[spec[0]] = input.value; });
        label.appendChild(input);
        wrap.appendChild(label);
        form.appendChild(wrap);
        inputs[spec[0]] = input;
      });
      var submit = element("button", "p-button sun", t("sendRequest"));
      submit.type = "submit";
      form.appendChild(submit);
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        submit.disabled = true;
        error.textContent = "";
        var payload = {preferred_language: lang, website: trap.value, form_age_ms: Date.now() - openedAt};
        Object.keys(requestForm).forEach(function (key) { payload[key] = requestForm[key].trim(); });
        request("/api/platform/registration-requests", {method: "POST", body: JSON.stringify(payload)}).then(function () {
          Object.keys(requestForm).forEach(function (key) { requestForm[key] = ""; });
          requestMode = false;
          loginAlert = t("requestSent");
          drawForm();
        }).catch(function (err) {
          error.className = "p-alert error";
          error.textContent = errorMessage(err);
          submit.disabled = false;
        });
      });
      card.appendChild(form);
      card.appendChild(error);
      card.appendChild(button(t("switchLogin"), "outline p-form-switch", function () {
        requestMode = false;
        error.className = "p-alert error";
        drawForm();
      }));
    }
    /* One role: straight to its portal. Several roles: the user picks (one session works for all). */
    function enterPortals(result) {
      var portals = (result.portals && result.portals.length ? result.portals : [result.role]).filter(function (name) { return PORTAL_TARGETS[name]; });
      if (!portals.length) throw new Error(t("accessDenied"));
      try { sessionStorage.setItem("zm-portals", JSON.stringify(portals)); } catch (e) {}
      portals.forEach(function (name) {
        sessionStorage.setItem(PORTAL_TARGETS[name].key, result.access_token);
        localStorage.setItem(PORTAL_TARGETS[name].lang, lang);
      });
      if (portals.length === 1) { window.location.href = PORTAL_TARGETS[portals[0]].url; return; }
      card.innerHTML = "";
      card.appendChild(element("h2", "", t("chooseTitle")));
      card.appendChild(element("p", "p-subtitle", t("chooseHint")));
      portals.forEach(function (name) {
        var link = element("a", "p-button sun p-portal-choice", portalLabel(name));
        link.href = PORTAL_TARGETS[name].url;
        card.appendChild(link);
      });
    }
    function field(labelText, type, autocomplete) {
      var wrap = element("div", "p-field");
      var label = element("label", "", labelText);
      var input = element("input");
      input.type = type;
      if (autocomplete) input.autocomplete = autocomplete;
      label.appendChild(input);
      wrap.appendChild(label);
      if (type === "password") decoratePassword(label, input);
      return input;
    }
    drawForm();
    var back = element("a", "p-muted", t("backToWebsite"));
    back.href = "/";
    card.appendChild(back);
    layout.appendChild(card);
    main.appendChild(layout);
  }
  function renderDashboardWelcome(main) {
    var welcome = element("section", "p-dashboard-welcome");
    var copy = element("div");
    copy.appendChild(element("span", "p-auth-kicker", t("portalOverview")));
    copy.appendChild(element("h2", "", t("welcomeUser") + " " + profile.username));
    copy.appendChild(element("p", "", isTeacherPortal ? t("teacherWelcome") : t("parentWelcome")));
    welcome.appendChild(copy);
    welcome.appendChild(element("span", "p-badge p-status-active", t("activeAccount")));
    main.appendChild(welcome);
  }
  function statusLabel(status) {
    return t(status === "published" ? "published" : status === "submitted" ? "submitted" : status === "rejected" ? "rejected" : status === "archived" ? "archived" : "draft");
  }
  function renderReports(container, reports) {
    if (!reports.length) {
      container.appendChild(element("p", "p-muted", isTeacherPortal ? t("notAssigned") : t("noReports")));
      return;
    }
    reports.forEach(function (report) {
      var card = element("article", "p-report");
      var meta = element("div", "p-report-meta");
      meta.appendChild(element("span", "p-badge", statusLabel(report.status)));
      if (report.created_at) meta.appendChild(element("small", "p-muted", new Date(report.created_at).toLocaleDateString(lang === "ar" ? "ar" : "en")));
      card.appendChild(meta);
      card.appendChild(element("h3", "", report.title));
      if (report.language && report.language.split("-")[0] !== lang) {
        card.appendChild(element("p", "p-muted", t("originalLanguage")));
      }
      var body = element("p", "", report.body);
      if (report.language) {
        body.lang = report.language;
        body.dir = report.language.split("-")[0] === "ar" ? "rtl" : "ltr";
      }
      card.appendChild(body);
      container.appendChild(card);
    });
  }
  function fileSizeLabel(bytes) {
    return bytes >= 1048576 ? (bytes / 1048576).toFixed(1) + " MB" : Math.max(1, Math.ceil(bytes / 1024)) + " KB";
  }
  function downloadByPath(path, filename) {
    fetch(apiBase + path, {headers: {Authorization: "Bearer " + token}}).then(function (response) {
      if (!response.ok) {
        return response.json().catch(function () { return {}; }).then(function (body) { throw new Error(body.detail || t("genericError")); });
      }
      return response.blob();
    }).then(function (blob) {
      var url = URL.createObjectURL(blob);
      var link = element("a");
      link.href = url; link.download = filename || "download";
      document.body.appendChild(link); link.click(); link.remove();
      URL.revokeObjectURL(url);
    }).catch(function (error) { window.alert(errorMessage(error)); });
  }
  /* A post card: scope badge, title, text, attachments. fileUrl(post, file) gives the download path; onDelete adds a delete button. */
  function postCard(post, fileUrl, onDelete) {
    var card = element("article", "p-post p-post-" + (post.scope === "child" ? "private" : "general"));
    var meta = element("div", "p-report-meta");
    var badge = element("span", "p-badge " + (post.scope === "child" ? "p-scope-private" : "p-scope-general"),
      post.scope === "child" ? t("scopePrivateBadge") + (post.child_name ? " · " + post.child_name : "") : t("scopeGeneralBadge"));
    meta.appendChild(badge);
    var when = post.created_at ? post.created_at.slice(0, 10) : "";
    var who = post.author || post.author_username || "";
    var info = element("small", "p-muted p-post-info");
    if (who) { var whoNode = element("span", "", who); whoNode.setAttribute("dir", "auto"); info.appendChild(whoNode); }
    if (when) { var whenNode = element("span", "", when); whenNode.setAttribute("dir", "ltr"); info.appendChild(whenNode); }
    meta.appendChild(info);
    card.appendChild(meta);
    var postTitle = element("h3", "", post.title); postTitle.setAttribute("dir", "auto"); card.appendChild(postTitle);
    if (post.body) { var postBody = element("p", "p-post-body", post.body); postBody.setAttribute("dir", "auto"); card.appendChild(postBody); }
    if (post.files && post.files.length) {
      var files = element("div", "p-post-files");
      post.files.forEach(function (file) {
        var chip = element("button", "p-file-chip", file.filename + " · " + fileSizeLabel(file.size));
        chip.type = "button";
        chip.addEventListener("click", function () { downloadByPath(fileUrl(post, file), file.filename); });
        files.appendChild(chip);
      });
      card.appendChild(files);
    }
    if (onDelete) card.appendChild(button(t("deleteFile"), "outline p-post-delete", function () {
      if (window.confirm(t("deletePostConfirm"))) onDelete(post);
    }));
    return card;
  }
  function renderParentPosts(main) {
    var card = element("section", "p-card");
    card.appendChild(element("h2", "", t("postsForYou")));
    var list = element("div", "p-post-list");
    list.appendChild(element("p", "p-muted", t("loading")));
    card.appendChild(list);
    main.appendChild(card);
    request("/api/platform/parent/posts").then(function (posts) {
      list.innerHTML = "";
      if (!posts.length) { list.appendChild(element("p", "p-muted", t("noPostsParent"))); return; }
      posts.forEach(function (post) {
        list.appendChild(postCard(post, function (p, f) { return "/api/platform/parent/posts/" + encodeURIComponent(p.id) + "/files/" + encodeURIComponent(f.id); }));
      });
    }).catch(function (error) { list.innerHTML = ""; showError(card, error); });
  }
  function renderTeacherPosts(main, adminMode) {
    var card = element("section", "p-card");
    card.appendChild(element("h2", "", adminMode ? t("allPosts") : t("postsComposeTitle")));
    var list = element("div", "p-post-list");
    function loadPosts() {
      list.innerHTML = "";
      list.appendChild(element("p", "p-muted", t("loading")));
      request(adminMode ? "/api/platform/admin/posts" : "/api/platform/teacher/posts").then(function (posts) {
        list.innerHTML = "";
        if (!posts.length) { list.appendChild(element("p", "p-muted", t("noPosts"))); return; }
        posts.forEach(function (post) {
          list.appendChild(postCard(post, function (p, f) {
            return adminMode ? "/api/platform/admin/teacher-content/" + encodeURIComponent(f.id) + "/download"
              : "/api/platform/teacher/content/" + encodeURIComponent(f.id) + "/download";
          }, function (p) {
            request((adminMode ? "/api/platform/admin/posts/" : "/api/platform/teacher/posts/") + encodeURIComponent(p.id), {method: "DELETE"})
              .then(loadPosts).catch(function (error) { showError(card, error); });
          }));
        });
      }).catch(function (error) { list.innerHTML = ""; showError(card, error); });
    }
    if (!adminMode) {
      card.appendChild(element("p", "p-muted", t("postsComposeHelp")));
      var form = element("form", "p-compose");
      var scope = element("select");
      scope.appendChild(new Option(t("scopeGeneral"), "general"));
      scope.appendChild(new Option(t("scopeChild"), "child"));
      var scopeLabel = element("label", "p-field", t("scopeLabel")); scopeLabel.appendChild(scope); form.appendChild(scopeLabel);
      var childSelect = element("select");
      childSelect.appendChild(new Option(t("selectChild"), ""));
      var childLabel = element("label", "p-field", t("child")); childLabel.appendChild(childSelect); childLabel.hidden = true; form.appendChild(childLabel);
      request("/api/platform/teacher/children").then(function (children) {
        children.forEach(function (child) { childSelect.appendChild(new Option(child.display_name, child.id)); });
      }).catch(function () {});
      scope.addEventListener("change", function () { childLabel.hidden = scope.value !== "child"; childSelect.required = scope.value === "child"; });
      var title = element("input"); title.type = "text"; title.maxLength = 120; title.required = true;
      var titleLabel = element("label", "p-field", t("postTitle")); titleLabel.appendChild(title); form.appendChild(titleLabel);
      var body = element("textarea"); body.maxLength = 3000;
      var bodyLabel = element("label", "p-field", t("postBody")); bodyLabel.appendChild(body); form.appendChild(bodyLabel);
      var fileInput = element("input"); fileInput.type = "file"; fileInput.multiple = true;
      var fileLabel = element("label", "p-field", t("postFiles")); fileLabel.appendChild(fileInput); form.appendChild(fileLabel);
      var message = element("p", "p-alert"); message.setAttribute("role", "status");
      var submit = element("button", "p-button sun", t("publishPost")); submit.type = "submit";
      form.appendChild(submit); form.appendChild(message);
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        if (fileInput.files.length > 5) { message.className = "p-alert error"; message.textContent = t("postFiles"); return; }
        var data = new FormData();
        data.append("scope", scope.value); data.append("title", title.value.trim()); data.append("body", body.value);
        if (scope.value === "child") data.append("child_id", childSelect.value);
        Array.prototype.forEach.call(fileInput.files, function (file) { data.append("files", file); });
        submit.disabled = true; message.className = "p-alert"; message.textContent = "";
        request("/api/platform/teacher/posts", {method: "POST", body: data}).then(function () {
          title.value = ""; body.value = ""; fileInput.value = "";
          message.className = "p-alert success"; message.textContent = t("postPublished");
          loadPosts();
        }).catch(function (error) {
          message.className = "p-alert error"; message.textContent = errorMessage(error);
        }).finally(function () { submit.disabled = false; });
      });
      card.appendChild(form);
      card.appendChild(element("h3", "p-subhead", t("myPosts")));
    }
    card.appendChild(list);
    main.appendChild(card);
    loadPosts();
  }
  function renderParent(main) {
    renderDashboardWelcome(main);
    renderParentPosts(main);
    var listCard = element("section", "p-card");
    listCard.appendChild(element("h2", "", t("children")));
    listCard.appendChild(element("p", "p-muted", t("loading")));
    main.appendChild(listCard);
    request("/api/platform/children").then(function (children) {
      listCard.innerHTML = "";
      listCard.appendChild(element("h2", "", t("children")));
      if (!children.length) {
        listCard.appendChild(element("p", "p-muted", t("noChildren")));
        return;
      }
      var grid = element("div", "p-grid");
      children.forEach(function (child) {
        var card = element("article", "p-card p-child");
        var childHead = element("div", "p-child-head");
        childHead.appendChild(element("span", "p-avatar sun", (child.display_name || "?").charAt(0)));
        childHead.appendChild(element("h3", "", child.display_name));
        card.appendChild(childHead);
        card.appendChild(element("p", "p-muted", t("loading")));
        grid.appendChild(card);
        request("/api/platform/children/" + encodeURIComponent(child.id) + "/reports").then(function (reports) {
          card.querySelectorAll(".p-muted").forEach(function (node) { node.remove(); });
          renderReports(card, reports);
          if (!reports.length) card.appendChild(element("p", "p-muted", t("noReports")));
        }).catch(function (error) { card.querySelectorAll(".p-muted").forEach(function (node) { node.remove(); }); showError(card, error); });
      });
      listCard.appendChild(grid);
    }).catch(function (error) { listCard.innerHTML = ""; listCard.appendChild(element("h2", "", t("children"))); showError(listCard, error); });
  }
  function downloadTeacherContent(contentId, adminMode, filename) {
    var basePath = adminMode ? "/api/platform/admin/teacher-content/" : "/api/platform/teacher/content/";
    fetch(apiBase + basePath + encodeURIComponent(contentId) + "/download", {
      headers: {Authorization:"Bearer " + token}
    }).then(function (response) {
      if (!response.ok) {
        return response.json().catch(function () { return {}; }).then(function (body) {
          throw new Error(body.detail || t("genericError"));
        });
      }
      return response.blob();
    }).then(function (blob) {
      var url = URL.createObjectURL(blob);
      var link = element("a");
      link.href = url;
      link.download = filename || "download";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    }).catch(function (error) {
      window.alert(errorMessage(error));
    });
  }
  function loadTeacherContent(card, adminMode) {
    var path = adminMode ? "/api/platform/admin/teacher-content" : "/api/platform/teacher/content";
    var list = card.querySelector(".p-content-list");
    list.innerHTML = "";
    request(path).then(function (contents) {
      if (!contents.length) {
        list.appendChild(element("p", "p-muted", t("noTeacherFiles")));
        return;
      }
      contents.forEach(function (content) {
        var item = element("article", "p-content-item");
        item.appendChild(element("span", "p-file-icon p-file-" + content.category, {document:"DOC", image:"IMG", video:"VID"}[content.category] || "FILE"));
        var description = element("div", "p-content-text");
        description.appendChild(element("strong", "", content.filename));
        if (adminMode && content.owner_username) {
          description.appendChild(element("small", "p-muted", content.owner_username));
        }
        description.appendChild(element("small", "p-muted", t(content.category) + " · " + Math.max(1, Math.ceil(content.size / 1024)) + " KB"));
        item.appendChild(description);
        item.appendChild(button(t("downloadFile"), "outline", function () {
          downloadTeacherContent(content.id, adminMode, content.filename);
        }));
        if (!adminMode || profile.roles.indexOf("admin") !== -1) {
          item.appendChild(button(t("deleteFile"), "outline", function () {
            if (!window.confirm(t("deleteFile") + " · " + content.filename + "?")) return;
            var deletePath = adminMode
              ? "/api/platform/admin/teacher-content/" + encodeURIComponent(content.id)
              : "/api/platform/teacher/content/" + encodeURIComponent(content.id);
            request(deletePath, {method:"DELETE"}).then(function () {
              loadTeacherContent(card, adminMode);
            }).catch(function (error) { showError(card, error); });
          }));
        }
        list.appendChild(item);
      });
    }).catch(function (error) { list.innerHTML = ""; showError(card, error); });
  }
  function renderTeacherContent(main, adminMode) {
    var card = element("section", "p-card");
    card.appendChild(element("h2", "", t("teacherFiles")));
    if (!adminMode) {
      card.appendChild(element("p", "p-muted", t("teacherFilesHelp")));
      var form = element("form", "p-card");
      var typeLabel = element("label", "p-field", t("uploadType"));
      var type = element("select");
      [["other","other"],["document","document"],["image","image"],["video","video"]].forEach(function (option) {
        type.appendChild(new Option(t(option[1]), option[0]));
      });
      typeLabel.appendChild(type);
      form.appendChild(typeLabel);
      var fileLabel = element("label", "p-field", t("chooseFile"));
      var fileInput = element("input");
      fileInput.type = "file";
      fileInput.required = true;
      fileLabel.appendChild(fileInput);
      form.appendChild(fileLabel);
      var message = element("p", "p-alert");
      var uploadButton = element("button", "p-button sun", t("uploadFile"));
      uploadButton.type = "submit";
      form.appendChild(uploadButton);
      form.appendChild(message);
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        if (!fileInput.files.length) return;
        uploadButton.disabled = true;
        message.textContent = "";
        var data = new FormData();
        data.append("file", fileInput.files[0]);
        data.append("category", type.value);
        request("/api/platform/teacher/content", {method:"POST",body:data}).then(function () {
          fileInput.value = "";
          message.className = "p-alert success";
          message.textContent = t("fileUploaded");
          loadTeacherContent(card, false);
        }).catch(function (error) {
          message.className = "p-alert error";
          message.textContent = errorMessage(error);
        }).finally(function () { uploadButton.disabled = false; });
      });
      card.appendChild(form);
    }
    var list = element("div", "p-content-list");
    list.appendChild(element("p", "p-muted", t("loading")));
    card.appendChild(list);
    main.appendChild(card);
    loadTeacherContent(card, adminMode);
  }
  function renderTeacher(main) {
    renderDashboardWelcome(main);
    var canTeach = profile.roles.indexOf("teacher") !== -1;
    if (!canTeach) {
      if (profile.roles.indexOf("admin") !== -1) { renderTeacherPosts(main, true); renderTeacherContent(main, true); }
      loadReviewQueue(main);
      return;
    }
    renderTeacherPosts(main, false);
    renderTeacherContent(main, false);
    var childrenCard = element("section", "p-card");
    childrenCard.appendChild(element("h2", "", t("children")));
    childrenCard.appendChild(element("p", "p-muted", t("loading")));
    main.appendChild(childrenCard);
    var reportCard = element("section", "p-card");
    reportCard.appendChild(element("h2", "", t("reports")));
    reportCard.appendChild(element("p", "p-muted", t("loading")));
    main.appendChild(reportCard);
    request("/api/platform/teacher/children").then(function (children) {
      childrenCard.innerHTML = "";
      childrenCard.appendChild(element("h2", "", t("children")));
      if (!children.length) childrenCard.appendChild(element("p", "p-muted", t("notAssigned")));
      else {
        var select = element("select");
        select.required = true;
        select.appendChild(new Option(t("selectChild"), ""));
        children.forEach(function (child) { select.appendChild(new Option(child.display_name, child.id)); });
        select.value = formState.child_id;
        select.addEventListener("change", function () { formState.child_id = select.value; });
        var form = element("form", "p-card");
        var selectLabel = element("label", "p-field", t("child"));
        selectLabel.appendChild(select);
        form.appendChild(selectLabel);
        var title = element("input");
        title.type = "text"; title.maxLength = 120; title.required = true;
        title.value = formState.title;
        title.addEventListener("input", function () { formState.title = title.value; });
        var titleLabel = element("label", "p-field", t("title")); titleLabel.appendChild(title); form.appendChild(titleLabel);
        var body = element("textarea");
        body.maxLength = 3000; body.required = true;
        body.value = formState.body;
        body.addEventListener("input", function () { formState.body = body.value; });
        var bodyLabel = element("label", "p-field", t("body")); bodyLabel.appendChild(body); form.appendChild(bodyLabel);
        var attachmentLabel = element("label", "p-field", t("reportAttachments"));
        var attachmentInput = element("input");
        attachmentInput.type = "file"; attachmentInput.multiple = true;
        attachmentLabel.appendChild(attachmentInput); form.appendChild(attachmentLabel);
        form.appendChild(element("p", "p-muted", t("reportAttachmentsHelp")));
        form.appendChild(element("p", "p-muted", t("privacy")));
        var message = element("p", "p-alert");
        var save = element("button", "p-button outline", t("saveDraft")); save.type = "button";
        var submit = element("button", "p-button sun", t("submit")); submit.type = "submit";
        form.appendChild(element("div", "p-row"));
        form.lastChild.appendChild(save); form.lastChild.appendChild(submit);
        var cancelEdit = element("button", "p-button outline", t("cancelEdit"));
        cancelEdit.type = "button"; cancelEdit.hidden = !editingReportId;
        form.lastChild.appendChild(cancelEdit);
        form.appendChild(message);
        teacherControls = {select:select,title:title,body:body,form:form,save:save,submit:submit,cancel:cancelEdit,message:message};
        function saveReport(submitForReview) {
          if (!select.value || !title.value.trim() || !body.value.trim()) {
            message.className = "p-alert error";
            message.textContent = t("selectChild") + " · " + t("title") + " · " + t("body");
            return Promise.resolve();
          }
          save.disabled = true; submit.disabled = true; message.textContent = "";
          var updating = !!editingReportId;
          var path = updating
            ? "/api/platform/teacher/reports/" + encodeURIComponent(editingReportId)
            : "/api/platform/teacher/reports";
          var attachmentFiles = Array.from(attachmentInput.files || []);
          if (attachmentFiles.length > 5) {
            message.className = "p-alert error";
            message.textContent = t("reportAttachmentsHelp");
            save.disabled = false; submit.disabled = false;
            return Promise.resolve();
          }
          var uploadedAttachments = [];
          var reportPayload = {
            title: title.value.trim(), body: body.value.trim(),
            submit_for_review: submitForReview && attachmentFiles.length === 0
          };
          if (!updating) reportPayload.child_id = select.value;
          return request(path, {method:updating ? "PATCH" : "POST",body:JSON.stringify(reportPayload)}).then(function (report) {
            var reportId = updating ? editingReportId : report.id;
            if (!updating && attachmentFiles.length) {
              editingReportId = reportId;
              select.disabled = true;
            }
            return attachmentFiles.reduce(function (chain, file) {
              return chain.then(function () {
                var data = new FormData();
                data.append("file", file);
                data.append("category", "report_attachment");
                data.append("report_id", reportId);
                return request("/api/platform/teacher/content", {method:"POST",body:data}).then(function () {
                  uploadedAttachments.push(file);
                  var remainingFiles = Array.from(attachmentInput.files || []).filter(function (selected) {
                    return uploadedAttachments.indexOf(selected) === -1;
                  });
                  var transfer = new DataTransfer();
                  remainingFiles.forEach(function (remaining) { transfer.items.add(remaining); });
                  attachmentInput.files = transfer.files;
                });
              });
            }, Promise.resolve()).then(function () {
              if (submitForReview && attachmentFiles.length) {
                return request("/api/platform/teacher/reports/" + encodeURIComponent(reportId), {
                  method:"PATCH",
                  body:JSON.stringify({title:title.value.trim(),body:body.value.trim(),submit_for_review:true})
                });
              }
            }).then(function () {
              message.className = "p-alert success";
              message.textContent = updating ? t("reportUpdated") : submitForReview ? t("reportSent") : t("reportSaved");
              title.value = ""; body.value = "";
              attachmentInput.value = "";
              formState.title = ""; formState.body = "";
              editingReportId = "";
              cancelEdit.hidden = true;
              select.disabled = false;
              return loadTeacherReports(reportCard);
            });
          }).catch(function (error) {
            if (uploadedAttachments.length) {
              var remainingFiles = Array.from(attachmentInput.files || []).filter(function (selected) {
                return uploadedAttachments.indexOf(selected) === -1;
              });
              var transfer = new DataTransfer();
              remainingFiles.forEach(function (remaining) { transfer.items.add(remaining); });
              attachmentInput.files = transfer.files;
            }
            message.className = "p-alert error"; message.textContent = errorMessage(error);
          }).finally(function () { save.disabled = false; submit.disabled = false; });
        }
        save.addEventListener("click", function () { saveReport(false); });
        form.addEventListener("submit", function (event) { event.preventDefault(); saveReport(true); });
        cancelEdit.addEventListener("click", function () {
          editingReportId = "";
          formState.title = ""; formState.body = ""; formState.child_id = "";
          title.value = ""; body.value = ""; attachmentInput.value = ""; select.value = ""; select.disabled = false;
          cancelEdit.hidden = true; message.textContent = "";
        });
        if (editingReportId) select.disabled = true;
        childrenCard.appendChild(form);
      }
    }).catch(function (error) { childrenCard.innerHTML = ""; childrenCard.appendChild(element("h2", "", t("children"))); showError(childrenCard, error); });
    loadTeacherReports(reportCard);
    if (profile.roles.indexOf("manager") !== -1 || profile.roles.indexOf("admin") !== -1) loadReviewQueue(main);
  }
  function loadTeacherReports(card) {
    request("/api/platform/teacher/reports").then(function (reports) {
      card.innerHTML = "";
      card.appendChild(element("h2", "", t("reports")));
      if (!reports.length) card.appendChild(element("p", "p-muted", t("noReports")));
      else reports.forEach(function (report) {
        var item = element("article", "p-report");
        item.appendChild(element("h3", "", report.title));
        item.appendChild(element("span", "p-badge", statusLabel(report.status)));
        var body = element("p", "", report.body);
        body.lang = report.language || "ar";
        body.dir = body.lang.split("-")[0] === "ar" ? "rtl" : "ltr";
        item.appendChild(body);
        if (report.status === "draft" || report.status === "rejected") {
          item.appendChild(button(t("edit"), "outline", function () {
            editingReportId = report.id;
            formState.child_id = report.child_id;
            formState.title = report.title;
            formState.body = report.body;
            if (teacherControls) {
              teacherControls.select.value = report.child_id;
              teacherControls.select.disabled = true;
              teacherControls.title.value = report.title;
              teacherControls.body.value = report.body;
              teacherControls.cancel.hidden = false;
              teacherControls.form.scrollIntoView({behavior:"smooth", block:"start"});
            }
          }));
        }
        loadTeacherReportAttachments(report.id, item);
        card.appendChild(item);
      });
    }).catch(function (error) { card.innerHTML = ""; card.appendChild(element("h2", "", t("reports"))); showError(card, error); });
  }
  function loadTeacherReportAttachments(reportId, container) {
    request("/api/platform/teacher/reports/" + encodeURIComponent(reportId) + "/attachments").then(function (attachments) {
      if (!attachments.length) return;
      var list = element("ul", "p-attachments");
      attachments.forEach(function (attachment) {
        var row = element("li");
        row.appendChild(element("span", "", attachment.filename));
        row.appendChild(button(t("downloadFile"), "outline", function () {
          downloadTeacherContent(attachment.id, false, attachment.filename);
        }));
        list.appendChild(row);
      });
      container.appendChild(element("h4", "", t("reportAttachments")));
      container.appendChild(list);
    }).catch(function (error) { showError(container, error); });
  }
  function loadReviewQueue(main) {
    var card = element("section", "p-card");
    card.appendChild(element("h2", "", t("review")));
    card.appendChild(element("p", "p-muted", t("loading")));
    main.appendChild(card);
    request("/api/platform/review/reports").then(function (reports) {
      card.innerHTML = "";
      card.appendChild(element("h2", "", t("review")));
      if (!reports.length) card.appendChild(element("p", "p-muted", t("noReview")));
      reports.forEach(function (report) {
        var item = element("article", "p-report");
        item.appendChild(element("h3", "", report.title));
        item.appendChild(element("p", "", report.body));
        ["published", "rejected"].forEach(function (status) {
          item.appendChild(button(t(status === "published" ? "approve" : "reject"), status === "published" ? "sun" : "outline", function () {
            request("/api/platform/review/reports/" + encodeURIComponent(report.id), {
              method: "PATCH", body: JSON.stringify({status: status})
            }).then(function () { loadReviewQueue(main); }).catch(function (error) { showError(item, error); });
          }));
        });
        card.appendChild(item);
      });
    }).catch(function (error) { card.innerHTML = ""; card.appendChild(element("h2", "", t("review"))); showError(card, error); });
  }
  function loadDashboard() {
    return request("/api/platform/auth/me").then(function (data) {
      profile = data;
      var allowed = isTeacherPortal
        ? data.roles.indexOf("teacher") !== -1 || data.roles.indexOf("manager") !== -1 || data.roles.indexOf("admin") !== -1
        : data.roles.indexOf("parent") !== -1;
      if (!allowed) {
        token = ""; sessionStorage.removeItem(storeKey);
        window.location.replace("../login/");
        return;
      }
      if (data.preferred_language === "ar" || data.preferred_language === "en") {
        lang = data.preferred_language;
        localStorage.setItem(langKey, lang);
      }
      document.documentElement.lang = lang;
      document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
      var main = shell();
      if (isTeacherPortal) renderTeacher(main);
      else renderParent(main);
    }).catch(function (error) {
      token = ""; sessionStorage.removeItem(storeKey);
      loginScreen();
      var alert = root.querySelector('[role="alert"]');
      if (alert) alert.textContent = errorMessage(error);
    });
  }
  function logout() {
    request("/api/platform/auth/logout", {method: "POST"}).catch(function () {}).then(function () {
      token = "";
      sessionStorage.removeItem(storeKey);
      profile = null;
      window.location.href = "../login/";
    });
  }
  function render() {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    document.title = portalTitle() + " | " + t("school");
    if (token && profile) {
      var main = shell();
      if (isTeacherPortal) renderTeacher(main); else renderParent(main);
    } else if (token) {
      loadDashboard();
    } else if (!isLogin) {
      window.location.replace("../login/");
    } else {
      loginScreen();
    }
  }

  (function idleGuard() {
    if (isLogin) return;
    var limit = 30 * 60 * 1000, timer;
    function expire() {
      ["zm-teacher-session", "zm-parent-session", "zm-accountant-session", "zm-admin-session", "zm-portals"].forEach(function (key) { try { sessionStorage.removeItem(key); } catch (e) {} });
      window.location.replace("../login/?expired=1");
    }
    function reset() { clearTimeout(timer); timer = setTimeout(expire, limit); }
    ["click", "keydown", "mousemove", "touchstart", "scroll"].forEach(function (name) { window.addEventListener(name, reset, {passive: true}); });
    reset();
  }());
  render();
}());
