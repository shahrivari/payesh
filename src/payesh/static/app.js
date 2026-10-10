"use strict";
const $ = id => document.getElementById(id);
const state = { page: 1, total: 0, pageSize: 10, selected: null, items: [], active: false, starting: false, searchTimer: null, request: 0, detailRequest: 0, lastRunKey: null };
const statusLabels = { complete: "کامل", partial: "ناقص", unrecognized: "ناشناخته", no_text: "بدون متن", error: "خطا", none: "بدون استخراج" };
const types = { daily_interest: "سود روزشمار", subscription: "پذیره‌نویسی", opening: "گشایش اوراق", unknown: "ناشناخته" };
const sourceNames = { ifb: "فرابورس", tse: "بورس تهران" };
const runLabels = { completed: "دریافت موفق", partial: "دریافت با خطای بعضی فایل‌ها", failed: "دریافت ناموفق", interrupted: "دریافت متوقف‌شده", running: "دریافت در حال اجرا" };
const fieldLabels = { instrument_name: "نام و نوع اوراق", issuer: "ناشر", market_maker: "بازارگردان", guarantor: "ضامن", profit_formula: "فرمول محاسبه سود", annual_yield_percent: "نرخ سود سالانه", repurchase_rate_percent: "نرخ بازخرید", nominal_value_rial: "ارزش اسمی (ریال)", profit_payment_interval_months: "فاصله پرداخت سود (ماه)", publication_date: "تاریخ انتشار اوراق", maturity_date: "تاریخ سررسید", subscription_start_date: "شروع پذیره‌نویسی", subscription_end_date: "پایان پذیره‌نویسی", subscription_period_days: "دوره پذیره‌نویسی", term_months: "مدت اوراق (ماه)", symbols: "نمادها" };
const fa = value => String(value ?? "—").replace(/[0-9]/g, d => "۰۱۲۳۴۵۶۷۸۹"[d]);
const escapeHTML = value => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const text = value => escapeHTML(fa(value));
const amount = value => {
  if (value == null) return "—";
  const [integer, fraction] = String(value).split(".");
  return fa(integer.replace(/\B(?=(\d{3})+(?!\d))/g, "٬") + (fraction === undefined ? "" : `.${fraction}`));
};
const badge = status => `<span class="badge ${Object.hasOwn(statusLabels, status) ? status : "none"}">${escapeHTML(statusLabels[status] || "بدون استخراج")}</span>`;
const icon = name => `<svg aria-hidden="true"><use href="#icon-${name}"/></svg>`;
function publicationDate(value) {
  const date = String(value).match(/[۰-۹٠-٩\d]{4}[/-][۰-۹٠-٩\d]{1,2}[/-][۰-۹٠-٩\d]{1,2}/);
  const time = String(value).match(/[۰-۹٠-٩\d]{1,2}:[۰-۹٠-٩\d]{2}(?::[۰-۹٠-٩\d]{2})?/);
  return date ? `<bdi dir="ltr">${text(date[0])}</bdi>${time ? `<small><bdi dir="ltr">${text(time[0])}</bdi></small>` : ""}` : text(value);
}
const dateTime = value => value ? new Intl.DateTimeFormat("fa-IR", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Tehran" }).format(new Date(value)) : "—";
function showError(message) { $("error").textContent = message; $("error").hidden = !message; }
async function api(path, options = {}) {
  const response = await fetch(`/api/v1/${path}`, { ...options, headers: { Accept: "application/json", ...options.headers } });
  if (!response.ok) {
    const messages = { 404: "اطلاعات یا فایل موردنظر پیدا نشد.", 409: "یک دریافت دیگر در حال اجراست.", 422: "فیلترها معتبر نیستند؛ تاریخ‌ها را به شکل ۱۴۰۵/۰۷/۱۸ وارد کنید.", 403: "این درخواست مجاز نیست." };
    throw new Error(messages[response.status] || "ارتباط با برنامه با خطا مواجه شد. دوباره تلاش کنید.");
  }
  return response.json();
}
function dateParam(value) {
  return value.trim().replace(/[۰-۹]/g, d => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d))).replace(/[٠-٩]/g, d => String("٠١٢٣٤٥٦٧٨٩".indexOf(d))).replaceAll("/", "-");
}
function parameters() {
  const params = new URLSearchParams({ page: state.page, page_size: state.pageSize });
  for (const [key, value] of [["source", $("source").value], ["q", $("search").value.trim()], ["status", $("status").value], ["symbol", $("symbol").value.trim()], ["document_type", $("document-type").value], ["date_from", dateParam($("date-from").value)], ["date_to", dateParam($("date-to").value)]]) if (value) params.set(key, value);
  return params;
}
function renderRows() {
  $("rows").innerHTML = state.items.map(item => `<tr class="${item.notice_number === state.selected ? "selected" : ""}"><td><button class="row-title-button" type="button" data-notice="${escapeHTML(item.notice_number)}" aria-pressed="${item.notice_number === state.selected}"><span class="row-symbol">${text(item.symbol || "بدون نماد")}<small class="source-label">${escapeHTML(sourceNames[item.source] || "")}</small></span><span class="row-title">${escapeHTML(item.title)}</span><span class="row-mobile-date">${publicationDate(item.published_at)}</span></button></td><td class="publication-date">${publicationDate(item.published_at)}</td><td>${badge(item.extraction_status)}</td><td><button class="row-action" type="button" data-notice="${escapeHTML(item.notice_number)}" aria-label="جزئیات ${escapeHTML(item.symbol || item.notice_number)}">${icon("chevron")}</button></td></tr>`).join("");
  $("rows").querySelectorAll("[data-notice]").forEach(button => button.addEventListener("click", () => selectAnnouncement(button.dataset.notice)));
}
async function loadList() {
  const request = ++state.request;
  $("count").textContent = "در حال بارگذاری…";
  try {
    const data = await api(`announcements?${parameters()}`);
    if (request !== state.request) return;
    if (!data.items.length && data.total && state.page > 1) { state.page = Math.ceil(data.total / state.pageSize); return loadList(); }
    state.items = data.items; state.total = data.total;
    renderRows();
    $("count").textContent = `${fa(data.total)} اطلاعیه`;
    $("empty").hidden = data.items.length > 0;
    const filtered = [...parameters().keys()].some(k => !["page", "page_size"].includes(k));
    $("empty-title").textContent = filtered ? "اطلاعیه‌ای پیدا نشد" : "هنوز اطلاعیه‌ای ثبت نشده است";
    $("empty-text").textContent = filtered ? "جستجو یا فیلترها را تغییر دهید." : "با «دریافت اطلاعیه‌ها» اطلاعات فرابورس را به پایش اضافه کنید.";
    $("page-description").textContent = data.total ? `${fa((state.page - 1) * state.pageSize + 1)} تا ${fa(Math.min(state.page * state.pageSize, data.total))} از ${fa(data.total)}` : "بدون اطلاعیه";
    $("page-number").textContent = `صفحه ${fa(state.page)}`;
    $("previous").disabled = state.page <= 1;
    $("next").disabled = state.page * state.pageSize >= state.total;
    if (data.items.length && !data.items.some(item => item.notice_number === state.selected)) await selectAnnouncement(data.items[0].notice_number);
  } catch (error) { if (request === state.request) { $("count").textContent = "بارگذاری ناموفق"; showError(error.message); } }
}
function field(label, value) { return `<div><dt>${escapeHTML(label)}</dt><dd>${text(value)}</dd></div>`; }
function extractionDetails(data) {
  if (!data) return "";
  const missing = (data.missing_fields || []).map(key => fieldLabels[key] || (key === "symbol" ? "نماد" : key));
  const reasons = (data.parsing_reasons || []).map(reason => {
    const labels = {error: "خطا در استخراج فایل", no_text: "متن PDF قابل استخراج نیست", unrecognized: "قالب سند شناسایی نشد", missing_daily_values: "جدول سود روزشمار استخراج نشد", attachment_error: "استخراج یکی از پیوست‌ها با خطا مواجه شد"};
    if (reason.code === "missing_values") return `مقدار سود موجود نیست: ${fa(reason.count)} ردیف`;
    if (reason.code === "missing_file") return `فایل دریافت نشده: ${reason.filename}`;
    return labels[reason.code] || "";
  }).filter(Boolean);
  if (!missing.length && !reasons.length) return "";
  return `<div class="extraction-issues">${missing.length ? `<h4>موارد استخراج‌نشده</h4><ul>${missing.map(label => `<li>${escapeHTML(label)}</li>`).join("")}</ul>` : ""}${reasons.map(reason => `<p>${escapeHTML(reason)}</p>`).join("")}</div>`;
}
function attachmentsView(item, notice) {
  return `<section class="attachments"><h3>پیوست‌ها · ${fa(item.attachments.length)} فایل</h3>${item.attachments.map(file => {
    const url = item.source === "ifb"
      ? `/api/v1/announcements/${encodeURIComponent(notice)}/pdf`
      : `/api/v1/announcements/${encodeURIComponent(notice)}/attachments/${file.attachment_id}`;
    return `<div class="attachment"><span class="attachment-title">${icon("file")}<span>${escapeHTML(file.filename)}</span><b>${file.kind === "pdf" ? "PDF" : "Excel"}</b></span><div class="attachment-actions">${file.downloaded ? `${file.kind === "pdf" ? `<a href="${url}" target="_blank" rel="noopener">مشاهده</a>` : ""}<a href="${url}?download=true">دانلود</a>${badge(file.extraction_status)}` : '<span class="caution">در انتظار دانلود مجدد</span>'}</div>${extractionDetails(file.extracted_data)}</div>`;
  }).join("")}${!item.attachments.length ? `<p class="caution">${item.source === "ifb" ? "فایل هنوز ذخیره نشده است؛ در دریافت بعدی دوباره تلاش می‌شود." : "پیوست PDF یا Excel برای این اطلاعیه وجود ندارد."}</p>` : ""}</section>`;
}
async function selectAnnouncement(notice) {
  const request = ++state.detailRequest;
  state.selected = notice; renderRows();
  $("detail").innerHTML = '<div class="detail-placeholder">در حال بارگذاری جزئیات…</div>';
  try {
    const item = await api(`announcements/${encodeURIComponent(notice)}`);
    if (request !== state.detailRequest) return;
    const data = item.extracted_data || {};
    const core = field("نرخ سود سالانه", data.annual_yield_percent ? `${data.annual_yield_percent}٪` : null) + field("ارزش اسمی (ریال)", amount(data.nominal_value_rial)) + field("تاریخ سررسید", data.maturity_date);
    const extra = Object.entries(fieldLabels).filter(([key]) => !["annual_yield_percent", "nominal_value_rial", "maturity_date"].includes(key) && data[key] != null && data[key] !== "" && (!Array.isArray(data[key]) || data[key].length)).map(([key, label]) => field(label, Array.isArray(data[key]) ? data[key].join("، ") : data[key])).join("");
    const values = item.daily_interest_values;
    $("detail").innerHTML = `<div class="detail-top"><span class="eyebrow">جزئیات اطلاعیه</span><span class="file-label">${icon("file")}${item.has_pdf ? "PDF" : "فایل دریافت نشده"}</span></div><h2>${text(item.symbol || "بدون نماد")}</h2><p class="detail-title">${escapeHTML(item.title)}</p>${item.abstract ? `<details class="extra-fields"><summary>خلاصه اطلاعیه</summary><p>${escapeHTML(item.abstract)}</p></details>` : ""}${badge(item.extraction_status)}<dl class="fields">${field("منبع", sourceNames[item.source])}${field("شماره اطلاعیه", item.source_id || item.notice_number)}${field("تاریخ انتشار", item.published_at)}${field("نوع سند", types[item.document_type] || "—")}</dl><section class="extracted"><h3>اطلاعات استخراج‌شده</h3>${extractionDetails(item.extracted_data)}${item.extracted_data ? `<dl class="fields">${core}</dl>${extra ? `<details class="extra-fields"><summary>اطلاعات بیشتر</summary><dl class="fields">${extra}</dl></details>` : ""}` : '<p class="caution">اطلاعات ساختاری برای این سند استخراج نشده است.</p>'}${item.extraction_status !== "complete" && item.extracted_data ? '<p class="caution">اطلاعات این سند کامل نیست؛ فایل اصلی را بررسی کنید.</p>' : ""}${data.error ? `<details class="extra-fields"><summary>جزئیات خطا</summary><p dir="auto">${escapeHTML(data.error)}</p></details>` : ""}</section>${values.length ? `<section class="payments"><h3>سود روزشمار · ${fa(values.length)} ردیف</h3><table><thead><tr><th>تاریخ پرداخت</th><th>مبلغ (ریال)</th></tr></thead><tbody id="daily-rows"></tbody></table>${values.length > 10 ? '<button class="quiet" type="button" id="daily-more">نمایش همه ردیف‌ها</button>' : ""}</section>` : ""}${attachmentsView(item, notice)}`;
    if (values.length) {
      const draw = all => { $("daily-rows").innerHTML = (all ? values : values.slice(0, 10)).map(row => `<tr><td>${text(row.payment_date)}</td><td>${escapeHTML(amount(row.amount_rial))}</td></tr>`).join(""); };
      draw(false);
      if ($("daily-more")) $("daily-more").addEventListener("click", () => { draw(true); $("daily-more").hidden = true; });
    }
  } catch (error) { if (request === state.detailRequest) { $("detail").innerHTML = '<div class="detail-placeholder">بارگذاری جزئیات ناموفق بود.</div>'; showError(error.message); } }
}
function renderRun(run) {
  state.active = run?.status === "running";
  $("collect").disabled = state.active || state.starting;
  $("collect-label").textContent = state.active ? "دریافت در حال اجرا…" : "دریافت اطلاعیه‌ها";
  $("run-progress").hidden = !state.active || !run.total;
  const percent = run?.total ? Math.round(run.done / run.total * 100) : 0;
  $("run-progress").setAttribute("aria-valuenow", percent);
  $("progress-bar").style.width = `${percent}%`;
  const container = $("run-text").closest(".run");
  container.classList.toggle("warning", ["partial", "interrupted"].includes(run?.status));
  container.classList.toggle("failure", run?.status === "failed");
  if (!run) { $("run-text").textContent = "هنوز دریافتی از طریق وب انجام نشده است"; $("run-note").textContent = "برای به‌روزرسانی، دریافت اطلاعیه‌ها را بزنید"; return; }
  const stages = { fetching: "در حال دریافت فهرست اطلاعیه‌ها…", downloading: "در حال دانلود فایل‌ها…", extracting: "در حال استخراج اطلاعات…", fetching_ifb: "دریافت اطلاعیه‌های فرابورس…", fetching_tse: "دریافت صفحه جدیدترین اطلاعیه‌های بورس تهران…", downloading_ifb: "دانلود فایل‌های فرابورس…", downloading_tse: "دانلود پیوست‌های بورس تهران…", extracting_ifb: "استخراج اطلاعات فرابورس…", extracting_tse: "استخراج PDF و Excel بورس تهران…" };
  $("run-text").textContent = state.active ? stages[run.stage] || "دریافت در حال اجرا…" : `${runLabels[run.status] || run.status} · ${dateTime(run.finished_at || run.started_at)}`;
  $("run-note").textContent = state.active ? run.total ? `${fa(run.done)} از ${fa(run.total)} فایل پردازش شد` : "ممکن است چند دقیقه طول بکشد" : run.result ? `${fa(run.result.fetched)} اطلاعیه · ${fa(run.result.downloaded)} فایل جدید${run.result.failures.length ? ` · ${fa(run.result.failures.length)} خطا` : ""}` : run.error ? "جزئیات در تاریخچه دریافت‌ها" : "";
}
async function loadStats() {
  const stats = await api("stats");
  for (const [id, value] of [["stat-announcements", stats.announcement_count], ["stat-pdfs", stats.pdf_count], ["stat-complete", stats.complete_count], ["stat-review", stats.review_count]]) $(id).textContent = amount(value);
  $("stat-storage").textContent = `${fa((stats.pdf_bytes / 1048576).toFixed(1))} مگابایت فایل${stats.excel_count ? ` · ${fa(stats.excel_count)} Excel` : ""}`;
  renderRun(stats.latest_run);
  $("auto-update").textContent = stats.auto_update?.enabled
    ? `به‌روزرسانی خودکار هر ساعت · دریافت بعدی: ${dateTime(stats.auto_update.next_run_at)}`
    : "به‌روزرسانی خودکار غیرفعال است";
  const key = stats.latest_run ? `${stats.latest_run.id}:${stats.latest_run.status}` : "none";
  if (state.lastRunKey !== key) {
    const completedChange = state.lastRunKey !== null;
    state.lastRunKey = key;
    await loadHistory();
    if (completedChange && !state.active) { await loadList(); if (state.selected) await selectAnnouncement(state.selected); }
  }
}
async function loadHistory() {
  const history = await api("collection-runs");
  $("history-count").textContent = `(${fa(history.items.length)})`;
  $("history-items").innerHTML = history.items.length ? history.items.map(run => `<article class="history-entry"><div class="history-entry-top"><strong>${escapeHTML(runLabels[run.status] || run.status)} · ${run.started_by === "scheduled" ? "خودکار" : "دستی"}</strong><span>${escapeHTML(dateTime(run.started_at))}</span></div>${run.result ? `<p>${fa(run.result.fetched)} اطلاعیه دریافت‌شده · ${fa(run.result.downloaded)} فایل جدید · ${fa(run.result.complete_extractions)} استخراج کامل</p>` : ""}${run.result?.sources ? `<p>${Object.entries(run.result.sources).map(([name, result]) => `${escapeHTML(sourceNames[name] || name)}: ${fa(result.fetched)} اطلاعیه · ${fa(result.downloaded)} فایل${result.status === "failed" ? " · ناموفق" : result.status === "partial" ? " · ناقص" : ""}`).join(" / ")}</p>` : ""}${run.error ? `<p dir="auto">${escapeHTML(run.error)}</p>` : ""}${run.result?.failures.length ? `<details><summary>خطاهای دریافت (${fa(run.result.failures.length)})</summary><ul>${run.result.failures.map(f => `<li>اطلاعیه ${text(f.notice_number)}: <span dir="auto">${escapeHTML(f.error)}</span></li>`).join("")}</ul></details>` : ""}</article>`).join("") : '<p class="empty">هنوز دریافتی ثبت نشده است.</p>';
}
async function collect() {
  if (state.starting || state.active) return;
  state.starting = true; $("collect").disabled = true; showError("");
  try { const run = await api("collection-runs", { method: "POST" }); renderRun(run); await loadStats(); }
  catch (error) { showError(error.message); }
  finally { state.starting = false; $("collect").disabled = state.active; }
}
async function poll() {
  try { await loadStats(); }
  catch (error) { showError("ارتباط با برنامه قطع شده است. باز بودن سرور محلی را بررسی کنید."); }
  setTimeout(poll, state.active ? 1500 : 15000);
}
function filter() { state.page = 1; showError(""); loadList(); }
$("collect").addEventListener("click", collect);
$("search").addEventListener("input", () => { clearTimeout(state.searchTimer); state.searchTimer = setTimeout(filter, 250); });
$("status").addEventListener("change", filter);
$("source").addEventListener("change", filter);
$("advanced-toggle").addEventListener("click", () => { $("advanced").hidden = !$("advanced").hidden; $("advanced-toggle").setAttribute("aria-expanded", !$("advanced").hidden); });
$("apply-filters").addEventListener("click", filter);
$("clear-filters").addEventListener("click", () => { for (const id of ["search", "source", "status", "symbol", "document-type", "date-from", "date-to"]) $(id).value = ""; filter(); });
$("advanced").querySelectorAll("input").forEach(input => input.addEventListener("keydown", event => { if (event.key === "Enter") filter(); }));
$("previous").addEventListener("click", () => { if (state.page > 1) { state.page--; loadList(); } });
$("next").addEventListener("click", () => { if (state.page * state.pageSize < state.total) { state.page++; loadList(); } });
loadList(); poll();
