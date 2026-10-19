const ROOT = document.querySelector("#app");
const CONFIG = window.AOA || {};
const PAGE_SIZE = 60;
const DEFAULT_LOAN_DAYS = 14;
const MAX_LOANS = 2;

const COVER_COLORS = [
  "#11513d", "#6a4f1f", "#8a4f2b", "#2f5f91", "#0b3d2e",
  "#455a38", "#a35d24", "#315b5f", "#263f55", "#5f6f34",
];

const state = {
  me: null,
  booting: true,
  bootError: "",
  page: "",
  busy: false,
  modal: null,
  toast: null,
  titles: [],
  borrowers: [],
  loans: [],
  returns: [],
  returnsLoaded: false,
  myBooks: { current: [], history: [] },
  openMenuKey: null,
  filters: { search: "", category: "All categories", dewey: "All Dewey classes", availability: "All availability" },
  catalogueView: "cards",
  catalogueLimit: PAGE_SIZE,
  borrowerSearch: "",
  borrowerGroup: "All groups",
  selectedBorrowerId: null,
  borrowerHistory: null,
  opsTab: "active",
  loanSearch: "",
  loanStatus: "All loans",
  assign: {},
  form: {},
};

function esc(value) {
  return String(value ?? "").replace(
    /[&<>"'`]/g,
    (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;", "`": "&#096;" })[char],
  );
}

function todayISO() {
  return state.me?.today || new Date().toISOString().slice(0, 10);
}

function addDaysISO(iso, days) {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function formatDate(iso) {
  if (!iso) return "-";
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return esc(iso);
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric" }).format(d);
}

function daysUntil(iso) {
  return Math.round((new Date(`${iso}T00:00:00`) - new Date(`${todayISO()}T00:00:00`)) / 86400000);
}

function initials(name) {
  return String(name || "?")
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

function hashString(text) {
  let h = 0;
  for (const ch of String(text)) h = (h * 31 + ch.charCodeAt(0)) | 0;
  return Math.abs(h);
}

function plural(n, word, many = `${word}s`) {
  return `${n} ${n === 1 ? word : many}`;
}

function isAdmin() {
  return state.me?.role === "admin";
}

function isStaff() {
  return state.me?.role === "staff";
}

function canAssign() {
  return isAdmin() || isStaff();
}

function homePage() {
  return isAdmin() ? "dashboard" : "library";
}

function copyLabels(loans) {
  const totals = {};
  for (const l of loans) totals[l.title] = (totals[l.title] || 0) + 1;
  const seen = {};
  return loans.map((l) => {
    seen[l.title] = (seen[l.title] || 0) + 1;
    return totals[l.title] > 1 ? `Copy ${seen[l.title]} of ${totals[l.title]} · ` : "";
  });
}

function titleByKey(key) {
  return state.titles.find((t) => t.key === String(key));
}

function findTitle(title, author) {
  const t = String(title || "").toLowerCase();
  const a = String(author || "").toLowerCase();
  return state.titles.find((x) => x.title.toLowerCase() === t && x.author.toLowerCase() === a)
    || state.titles.find((x) => x.title.toLowerCase() === t);
}

function borrowerById(id) {
  return state.borrowers.find((b) => b.userid === String(id));
}

function loansFor(userid) {
  return state.loans.filter((l) => l.userid === String(userid));
}

function categories() {
  return state.me?.categories || [];
}

const DEWEY_CLASSES = [
  "000 Computers, information & general works",
  "100 Philosophy & psychology",
  "200 Religion",
  "300 Social sciences",
  "400 Language",
  "500 Science",
  "600 Technology",
  "700 Arts & recreation",
  "800 Literature",
  "900 History & geography",
];

const DEWEY_PATTERN = /^\d{3}(\.\d+)?$/;

function deweyClass(dewey) {
  return dewey ? DEWEY_CLASSES[Number(dewey[0])] : "Not classified";
}

function deweyBadge(t) {
  return t.dewey ? `<span class="badge muted" title="Dewey ${esc(deweyClass(t.dewey))}">${esc(t.dewey)}</span>` : "";
}

async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(path, {
    method,
    headers: {
      "X-Requested-With": "XMLHttpRequest",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.success === false) {
    throw new Error(data.message || `Request failed (${res.status})`);
  }
  return data;
}

async function mutate(request, { reload = true, after } = {}) {
  if (state.busy) return;
  state.busy = true;
  render();
  try {
    const data = await request();
    if (reload) await loadData();
    state.modal = null;
    if (after) after(data);
    showToast(data.message || "Saved");
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    state.busy = false;
    render();
  }
}

function showToast(message, tone = "ok") {
  state.toast = { message, tone };
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => {
    state.toast = null;
    const toast = document.querySelector(".toast");
    if (toast) toast.remove();
  }, tone === "error" ? 6000 : 3800);
}

async function loadData() {
  if (isAdmin()) {
    const [titles, borrowers, loans, me] = await Promise.all([
      api("/api/titles"), api("/api/borrowers"), api("/api/loans"), api("/api/me"),
    ]);
    state.me.staff = me.staff;
    state.me.people = me.people;
    state.titles = titles.titles;
    state.borrowers = borrowers.borrowers;
    state.loans = loans.loans;
    if (state.returnsLoaded) await loadReturns();
    if (state.page === "borrower-detail" && state.selectedBorrowerId) await loadBorrowerHistory();
  } else {
    const [titles, mine, borrowers, loans] = await Promise.all([
      api("/api/titles"),
      api("/api/my-books"),
      isStaff() ? api("/api/borrowers") : Promise.resolve({ borrowers: [] }),
      isStaff() ? api("/api/loans") : Promise.resolve({ loans: [] }),
    ]);
    state.titles = titles.titles;
    state.myBooks = { current: mine.current, history: mine.history };
    state.borrowers = borrowers.borrowers;
    state.loans = loans.loans;
  }
}

async function loadReturns() {
  const data = await api("/api/returns?limit=500");
  state.returns = data.returns;
  state.returnsLoaded = true;
}

async function loadBorrowerHistory() {
  const id = state.selectedBorrowerId;
  state.borrowerHistory = null;
  const data = await api(`/api/returns?userid=${encodeURIComponent(id)}&limit=2000`);
  if (state.selectedBorrowerId === id) state.borrowerHistory = data.returns;
}

const ADMIN_PAGES = ["dashboard", "catalogue", "borrowers", "borrower", "operations", "book-form", "assign", "digital"];
const STAFF_PAGES = ["library", "on-loan", "assign", "my-books", "digital"];
const BORROWER_PAGES = ["library", "my-books", "digital"];

function go(page, param) {
  const hash = `#/${page}${param !== undefined && param !== null ? `/${encodeURIComponent(param)}` : ""}`;
  if (window.location.hash === hash) applyRoute();
  else window.location.hash = hash;
}

async function applyRoute() {
  const [, rawPage = "", rawParam] = window.location.hash.split("/");
  const allowed = isAdmin() ? ADMIN_PAGES : isStaff() ? STAFF_PAGES : BORROWER_PAGES;
  let page = allowed.includes(rawPage) ? rawPage : allowed[0];
  const param = rawParam ? decodeURIComponent(rawParam) : null;

  state.modal = null;
  state.openMenuKey = null;

  if (page === "borrower") {
    if (!param || !borrowerById(param)) page = "borrowers";
    else {
      state.page = "borrower-detail";
      state.selectedBorrowerId = param;
      render();
      try {
        await loadBorrowerHistory();
      } catch (err) {
        showToast(err.message, "error");
      }
      render();
      window.scrollTo(0, 0);
      return;
    }
  }
  if (page === "book-form" && !state.form.mode) resetBookForm("add");
  if (page === "assign" && !state.assign.dueDate) resetAssign();
  if (page === "operations" && state.opsTab === "history" && !state.returnsLoaded) {
    loadReturns().then(render).catch((err) => showToast(err.message, "error"));
  }

  state.page = page;
  render();
  window.scrollTo(0, 0);
}

async function boot() {
  try {
    const me = await api("/api/me");
    state.me = me;
    resetAssign();
    await loadData();
    state.booting = false;
    window.addEventListener("hashchange", applyRoute);
    await applyRoute();
  } catch (err) {
    state.booting = false;
    state.bootError = err.message;
    render();
  }
}

const icons = {
  search: '<svg class="icon" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"></circle><path d="m21 21-4.3-4.3"></path></svg>',
  plus: '<svg class="icon" viewBox="0 0 24 24"><path d="M12 5v14"></path><path d="M5 12h14"></path></svg>',
  book: '<svg class="icon" viewBox="0 0 24 24"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5z"></path></svg>',
  user: '<svg class="icon" viewBox="0 0 24 24"><path d="M20 21a8 8 0 0 0-16 0"></path><circle cx="12" cy="7" r="4"></circle></svg>',
  edit: '<svg class="icon" viewBox="0 0 24 24"><path d="M12 20h9"></path><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"></path></svg>',
  eye: '<svg class="icon" viewBox="0 0 24 24"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z"></path><circle cx="12" cy="12" r="3"></circle></svg>',
  more: '<svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="1"></circle><circle cx="19" cy="12" r="1"></circle><circle cx="5" cy="12" r="1"></circle></svg>',
  check: '<svg class="icon" viewBox="0 0 24 24"><path d="m20 6-11 11-5-5"></path></svg>',
  arrow: '<svg class="icon" viewBox="0 0 24 24"><path d="M5 12h14"></path><path d="m12 5 7 7-7 7"></path></svg>',
  x: '<svg class="icon" viewBox="0 0 24 24"><path d="M18 6 6 18"></path><path d="m6 6 12 12"></path></svg>',
  clock: '<svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3 2"></path></svg>',
};

function render() {
  if (state.booting) {
    ROOT.innerHTML = `<div class="boot-screen">Loading the library...</div>`;
    return;
  }
  if (state.bootError) {
    ROOT.innerHTML = `
      <section class="panel error-screen">
        <h2>Could not load the library</h2>
        <p class="lead">${esc(state.bootError)}</p>
        <div class="button-row" style="justify-content:center;margin-top:16px;">
          <button class="btn primary" onclick="location.reload()">Try again</button>
        </div>
      </section>`;
    return;
  }
  ROOT.innerHTML = `
    <div class="app-shell">
      ${renderTopbar()}
      <main class="main">${renderPage()}</main>
      ${state.modal ? renderModal() : ""}
      ${state.toast ? `<div class="toast ${state.toast.tone === "error" ? "error" : ""}" role="status">${esc(state.toast.message)}</div>` : ""}
    </div>`;
}

function renderKeepingFocus(el) {
  const selector = el.dataset.bind ? `[data-bind="${el.dataset.bind}"]` : el.id ? `#${el.id}` : null;
  const cursor = el.selectionStart;
  render();
  if (!selector) return;
  const next = document.querySelector(selector);
  if (next) {
    next.focus();
    if (cursor !== null && next.setSelectionRange) {
      try {
        next.setSelectionRange(cursor, cursor);
      } catch (_) {
      }
    }
  }
}

function renderTopbar() {
  const nav = isAdmin()
    ? [["dashboard", "Dashboard"], ["catalogue", "Catalogue"], ["borrowers", "Borrowers"], ["operations", "Operations"], ["digital", "Digital Library"]]
    : isStaff()
      ? [["library", "Library"], ["on-loan", "On Loan"], ["my-books", "My Books"], ["digital", "Digital Library"]]
      : [["library", "Library"], ["my-books", "My Books"], ["digital", "Digital Library"]];
  const home = homePage();
  const activeNav = state.page === "borrower-detail" ? "borrowers" : state.page;

  return `
    <header class="topbar">
      <a class="brand" href="#/${home}" data-action="nav" data-page="${home}" title="Go to ${home}">
        <div class="brand-logo-wrap">
          <img class="brand-logo" src="${esc(CONFIG.logo)}" alt="African Olympiad Academy logo" />
        </div>
        <div class="brand-copy">
          <strong>AOA Library</strong>
          <span>Physical catalogue and circulation</span>
        </div>
      </a>
      <nav class="topnav" aria-label="Main navigation">
        ${nav.map(([page, label]) => `<button class="nav-button ${activeNav === page ? "active" : ""}" data-action="nav" data-page="${page}">${label}</button>`).join("")}
      </nav>
      <div class="top-actions">
        ${isStaff() ? `<button class="btn secondary" data-action="open-return">${icons.check} Return Book</button>` : ""}
        ${canAssign() ? `<button class="btn primary" data-action="open-assign">${icons.plus} Assign Book</button>` : ""}
        ${renderViewSwitch()}
        <div class="user-chip">
          <div class="avatar">${esc(initials(state.me.name))}</div>
          <div class="user-chip-copy">
            <strong>${esc(state.me.name)}</strong>
            <span>${isAdmin() ? "Admin" : isStaff() ? "Staff" : "Borrower"}</span>
          </div>
        </div>
      </div>
    </header>`;
}

function renderViewSwitch() {
  const people = state.me.people || [];
  const staff = people.filter((p) => p.role === "staff");
  const borrowers = people.filter((p) => p.role !== "staff");
  const current = isAdmin() ? "admin" : `${state.me.role}:${state.me.userid}`;
  const option = (value, label) => `<option value="${esc(value)}" ${current === value ? "selected" : ""}>${esc(label)}</option>`;
  const group = (label, role, list) => list.length
    ? `<optgroup label="${label}">${list.map((p) => option(`${role}:${p.userid}`, p.name)).join("")}</optgroup>`
    : "";
  return `
    <label class="view-switch" title="Switch between the admin, staff and borrower views">
      <span>View as</span>
      <select data-view-as aria-label="View as" ${state.busy ? "disabled" : ""}>
        ${option("admin", "Admin")}
        ${group("Staff", "staff", staff)}
        ${group("Borrowers", "borrower", borrowers)}
        ${people.length ? "" : `<option disabled>Add borrowers to try other views</option>`}
      </select>
    </label>`;
}

async function switchView(value) {
  const [role, userid] = value.split(":");
  try {
    await api("/api/view-as", { method: "POST", body: { role, userid } });
    window.location.replace(window.location.pathname);
  } catch (err) {
    showToast(err.message, "error");
    render();
  }
}

function renderPage() {
  switch (state.page) {
    case "dashboard": return renderDashboard();
    case "catalogue": return renderCatalogue();
    case "library": return renderCatalogue();
    case "borrowers": return renderBorrowers();
    case "borrower-detail": return renderBorrowerDetail();
    case "operations": return renderOperations();
    case "on-loan": return renderStaffLoans();
    case "book-form": return renderBookForm();
    case "assign": return renderAssign();
    case "my-books": return renderMyBooks();
    case "digital": return renderDigitalLibrary();
    default: return "";
  }
}

function pageHead(eyebrow, title, lead, actions = "", aside = "") {
  const buttons = actions ? `<div class="button-row">${actions}</div>` : "";
  return `
    <section class="page-head">
      <div>
        <p class="eyebrow">${esc(eyebrow)}</p>
        <h1>${esc(title)}</h1>
        ${lead ? `<p class="lead">${esc(lead)}</p>` : ""}
      </div>
      ${aside ? `<div class="page-head-side">${buttons}${aside}</div>` : buttons}
    </section>`;
}

function metric(label, value, note, tone, tag) {
  return `
    <article class="metric-card">
      <div class="metric-label"><span>${esc(label)}</span><span class="badge ${tone}">${esc(tag)}</span></div>
      <div class="metric-value">${esc(value)}</div>
      <div class="metric-note">${esc(note)}</div>
    </article>`;
}

function cover(title, author, size = "") {
  const color = COVER_COLORS[hashString(`${title}|${author}`) % COVER_COLORS.length];
  return `
    <div class="book-cover ${size}" style="--cover-bg:${color}">
      <span class="cover-art"></span>
      <span class="cover-title">${esc(title)}</span>
      <span class="cover-author">${esc(author)}</span>
    </div>`;
}

function availabilityBadge(t) {
  if (t.available === 0) return `<span class="badge red">All on loan</span>`;
  if (t.available === t.total) return `<span class="badge green">${t.available} available</span>`;
  return `<span class="badge amber">${t.available} of ${t.total} available</span>`;
}

function dueBadge(loan) {
  if (loan.days_overdue > 0) return `<span class="badge red">${plural(loan.days_overdue, "day")} overdue</span>`;
  const left = daysUntil(loan.due);
  if (left === 0) return `<span class="badge amber">Due today</span>`;
  if (left <= 3) return `<span class="badge amber">Due in ${plural(left, "day")}</span>`;
  return `<span class="badge green">On track</span>`;
}

function groupBadge(group) {
  return group ? `<span class="badge blue">${esc(group)}</span>` : `<span class="badge muted">No group</span>`;
}

function titleLink(title, author) {
  const t = findTitle(title, author);
  return t
    ? `<button class="item-title" data-action="view-title" data-key="${esc(t.key)}">${esc(title)}</button>`
    : `<span class="item-title">${esc(title)}</span>`;
}

function borrowerLink(userid, name) {
  if (!isAdmin()) return esc(name);
  return `<button class="link-button" data-action="view-borrower" data-id="${esc(userid)}">${esc(name)}</button>`;
}

function loanActions(loan) {
  return `
    <div class="row-actions">
      <button class="btn text small" data-action="open-return" data-id="${esc(loan.userid)}" data-book="${esc(loan.book_id)}">${icons.check} Return</button>
      ${isAdmin() ? `<button class="btn text small" data-action="open-extend" data-id="${esc(loan.userid)}" data-book="${esc(loan.book_id)}">${icons.clock} Extend</button>` : ""}
    </div>`;
}

function renderDashboard() {
  const copies = state.titles.reduce((sum, t) => sum + t.total, 0);
  const overdue = state.loans.filter((l) => l.days_overdue > 0).sort((a, b) => b.days_overdue - a.days_overdue);
  const dueSoon = state.loans.filter((l) => l.days_overdue === 0 && daysUntil(l.due) <= 3);
  const recent = state.loans.slice().sort((a, b) => (b.issued || "").localeCompare(a.issued || "")).slice(0, 6);

  return `
    ${pageHead("Admin dashboard", "Library operations at a glance",
      "Track physical copies, overdue books and the latest loans.",
      `<button class="btn primary" data-action="open-assign">${icons.plus} Assign Book</button>
       <button class="btn secondary" data-action="open-book-form" data-mode="add">${icons.book} Add Book</button>`)}

    <section class="metrics-grid" aria-label="Library metrics">
      ${metric("Titles", state.titles.length, "Across all categories", "green", "Live")}
      ${metric("Physical copies", copies, "Shelved and on loan", "blue", "Live")}
      ${metric("On loan", state.loans.length, `${plural(new Set(state.loans.map((l) => l.userid)).size, "borrower")}`, "amber", "Live")}
      ${metric("Overdue", overdue.length, overdue.length ? "Need follow-up" : "Nothing overdue", overdue.length ? "red" : "green", overdue.length ? "Action" : "Clear")}
    </section>

    <section class="dashboard-grid">
      <div class="stack">
        <article class="panel">
          <div class="panel-header">
            <h2>Overdue books</h2>
            <span class="badge ${overdue.length ? "red" : "green"}">${overdue.length} overdue</span>
          </div>
          ${overdue.length ? overdue.slice(0, 8).map((loan) => `
            <div class="overdue-item">
              ${cover(loan.title, loan.author, "cover-sm")}
              <div>
                ${titleLink(loan.title, loan.author)}
                <div class="meta">
                  ${borrowerLink(loan.userid, loan.borrower)}<br />
                  Due ${formatDate(loan.due)}
                </div>
              </div>
              <div class="row-actions">${dueBadge(loan)}${loanActions(loan)}</div>
            </div>`).join("") : `<div class="empty-panel">No overdue books right now.</div>`}
          ${overdue.length > 8 ? `<button class="btn text" data-action="ops-filter" data-status="Overdue">See all ${overdue.length} overdue loans</button>` : ""}
        </article>

        <article class="panel">
          <div class="panel-header">
            <h2>Recent loans</h2>
            <button class="btn text" data-action="nav" data-page="operations">View operations</button>
          </div>
          ${recent.length ? renderLoansTable(recent, false) : `<div class="empty-panel">No books are on loan.</div>`}
        </article>
      </div>

      <aside class="stack">
        <article class="panel">
          <div class="panel-header"><h2>Quick actions</h2></div>
          <div class="quick-actions">
            <button class="quick-action primary" data-action="open-assign">
              <span><strong>Assign Book</strong><span>Check out a physical copy to a borrower</span></span>${icons.arrow}
            </button>
            <button class="quick-action" data-action="nav" data-page="operations">
              <span><strong>Return Book</strong><span>Close an active loan</span></span>${icons.check}
            </button>
            <button class="quick-action" data-action="open-book-form" data-mode="add">
              <span><strong>Add Book</strong><span>Create a catalogue title and its copies</span></span>${icons.plus}
            </button>
            <button class="quick-action" data-action="open-borrower-form">
              <span><strong>Add Borrower</strong><span>Register a Y1, Y2 or Faculty borrower</span></span>${icons.user}
            </button>
          </div>
        </article>
        <article class="panel">
          <div class="panel-header"><h2>Due in the next 3 days</h2><span class="badge amber">${dueSoon.length}</span></div>
          ${dueSoon.length ? dueSoon.slice(0, 6).map((loan) => `
            <div class="summary-row">
              <span>${esc(loan.title)}<br /><small>${esc(loan.borrower)}</small></span>
              <strong>${formatDate(loan.due)}</strong>
            </div>`).join("") : `<div class="empty-panel">Nothing due in the next few days.</div>`}
        </article>
      </aside>
    </section>`;
}

function filteredTitles() {
  const q = state.filters.search.trim().toLowerCase();
  return state.titles.filter((t) => {
    const matchesSearch = !q || `${t.title} ${t.author} ${t.category} ${t.dewey}`.toLowerCase().includes(q);
    const matchesCategory = state.filters.category === "All categories" || t.category === state.filters.category;
    const matchesDewey = state.filters.dewey === "All Dewey classes" || deweyClass(t.dewey) === state.filters.dewey;
    const matchesAvailability =
      state.filters.availability === "All availability" ||
      (state.filters.availability === "Available" && t.available > 0) ||
      (state.filters.availability === "All on loan" && t.available === 0);
    return matchesSearch && matchesCategory && matchesDewey && matchesAvailability;
  });
}

function hasActiveFilters() {
  const f = state.filters;
  return f.search || f.category !== "All categories" || f.dewey !== "All Dewey classes" || f.availability !== "All availability";
}

function renderCatalogue() {
  const admin = isAdmin();
  const list = filteredTitles();
  const shown = list.slice(0, state.catalogueLimit);

  return `
    ${pageHead(admin ? "Catalogue management" : "Library catalogue",
      admin ? "Manage the physical collection" : "Find books on the shelf",
      admin ? "Search, filter, assign and edit titles. Open a title to manage its individual copies."
            : "Check what is available before visiting the library desk. Borrowing happens in person at the library.",
      admin ? `<button class="btn primary" data-action="open-assign">${icons.plus} Assign Book</button>
               <button class="btn secondary" data-action="open-book-form" data-mode="add">${icons.book} Add Book</button>`
        : isStaff() ? `<button class="btn primary" data-action="open-assign">${icons.plus} Assign Book</button>` : "",
      `<a class="digital-callout" href="#/digital" data-action="nav" data-page="digital">
        ${icons.book}
        <span><strong>Journals and e-books?</strong> Read them in the AOA Digital Library (JSTOR).</span>
        ${icons.arrow}
      </a>`)}

    <section class="toolbar" aria-label="Catalogue filters">
      <div class="search-field">
        ${icons.search}
        <input type="search" data-bind="filters.search" data-rerender data-reset-limit value="${esc(state.filters.search)}" placeholder="Search by title, author, category or Dewey number" />
      </div>
      <select data-bind="filters.category" data-rerender data-reset-limit aria-label="Category">
        ${["All categories", ...categories()].map((c) => `<option ${state.filters.category === c ? "selected" : ""}>${esc(c)}</option>`).join("")}
      </select>
      <select data-bind="filters.dewey" data-rerender data-reset-limit aria-label="Dewey class">
        ${["All Dewey classes", ...DEWEY_CLASSES, "Not classified"].map((c) => `<option ${state.filters.dewey === c ? "selected" : ""}>${esc(c)}</option>`).join("")}
      </select>
      <select data-bind="filters.availability" data-rerender data-reset-limit aria-label="Availability">
        ${["All availability", "Available", "All on loan"].map((o) => `<option ${state.filters.availability === o ? "selected" : ""}>${o}</option>`).join("")}
      </select>
      <div class="view-toggle" aria-label="Catalogue view">
        <button class="${state.catalogueView === "cards" ? "active" : ""}" data-action="set-view" data-view="cards" type="button">Cards</button>
        <button class="${state.catalogueView === "list" ? "active" : ""}" data-action="set-view" data-view="list" type="button">List</button>
      </div>
      <div class="button-row">
        <button class="btn secondary" data-action="reset-filters" ${hasActiveFilters() ? "" : "disabled"}>Reset</button>
      </div>
    </section>

    <p class="result-count">Showing ${shown.length} of ${plural(list.length, "title")}${hasActiveFilters() ? ` (filtered from ${state.titles.length})` : ""}</p>

    ${list.length
      ? state.catalogueView === "cards"
        ? `<section class="catalogue-grid">${shown.map(renderBookCard).join("")}</section>`
        : renderCatalogueList(shown)
      : `<section class="empty-state"><h2>No books found</h2><p>Try clearing the search or filters.</p></section>`}

    ${list.length > shown.length ? `<div class="load-more"><button class="btn secondary" data-action="show-more">Show ${Math.min(PAGE_SIZE, list.length - shown.length)} more</button></div>` : ""}`;
}

function renderBookCard(t) {
  return `
    <article class="book-card">
      <button class="book-cover-button" data-action="view-title" data-key="${esc(t.key)}" aria-label="View ${esc(t.title)}" style="border:0;padding:0;background:transparent;">
        ${cover(t.title, t.author)}
      </button>
      <div class="book-card-body">
        <div class="book-meta-block">
          <button class="item-title book-title" data-action="view-title" data-key="${esc(t.key)}">${esc(t.title)}</button>
          <div class="book-author">${esc(t.author)}</div>
          <div class="button-row"><span class="badge blue">${esc(t.category)}</span>${deweyBadge(t)}</div>
        </div>
        <div class="book-footer">
          ${availabilityBadge(t)}
          ${renderBookActions(t, "card")}
        </div>
      </div>
    </article>`;
}

function renderCatalogueList(items) {
  return `
    <article class="panel catalogue-list-panel">
      <div class="table-wrap">
        <table class="catalogue-list-table">
          <thead><tr><th>Book</th><th>Author</th><th>Category</th><th>Dewey</th><th>Availability</th><th>Actions</th></tr></thead>
          <tbody>
            ${items.map((t) => `
              <tr>
                <td><div class="row-book">${cover(t.title, t.author, "cover-sm")}<button class="item-title" data-action="view-title" data-key="${esc(t.key)}">${esc(t.title)}</button></div></td>
                <td>${esc(t.author)}</td>
                <td><span class="badge blue">${esc(t.category)}</span></td>
                <td>${deweyBadge(t)}</td>
                <td>${availabilityBadge(t)}</td>
                <td>${renderBookActions(t, "list")}</td>
              </tr>`).join("")}
          </tbody>
        </table>
      </div>
    </article>`;
}

function renderBookActions(t, context) {
  const key = esc(t.key);
  const menuOpen = state.openMenuKey === t.key;
  return `
    <div class="${context === "list" ? "book-list-actions" : "card-actions"}">
      <button class="icon-button" title="View details" data-action="view-title" data-key="${key}">${icons.eye}</button>
      ${canAssign() ? `
        <button class="icon-button" title="Assign this book" data-action="open-assign" data-key="${key}" ${t.available ? "" : "disabled"}>${icons.plus}</button>` : ""}
      ${isAdmin() ? `
        <button class="icon-button" title="Edit title" data-action="open-book-form" data-mode="edit" data-key="${key}">${icons.edit}</button>
        <div class="overflow-wrap">
          <button class="icon-button" title="More actions" data-action="toggle-menu" data-key="${key}">${icons.more}</button>
          ${menuOpen ? `
            <div class="overflow-menu">
              <button data-action="view-title" data-key="${key}">${icons.eye} View copies</button>
              <button data-action="add-copy" data-key="${key}">${icons.plus} Add a copy</button>
              <button data-action="open-book-form" data-mode="edit" data-key="${key}">${icons.edit} Edit title</button>
              <button class="danger" data-action="confirm-delete-title" data-key="${key}">Delete title</button>
            </div>` : ""}
        </div>` : ""}
    </div>`;
}

function resetBookForm(mode, t = null) {
  state.form = {
    mode,
    key: t?.key || null,
    origTitle: t?.title || "",
    origAuthor: t?.author || "",
    title: t?.title || "",
    author: t?.author || "",
    category: t?.category || "",
    dewey: t?.dewey || "",
    copies: 1,
    touched: false,
  };
}

function renderBookForm() {
  const f = state.form;
  const edit = f.mode === "edit";
  const err = (cond, msg) => (f.touched && cond ? `<div class="validation">${msg}</div>` : "");
  return `
    ${pageHead(edit ? "Edit title" : "Add book", edit ? "Update catalogue details" : "Add a physical title",
      edit ? "Changes apply to every copy of this title." : "Adding a title that already exists just adds more copies.",
      `<button class="btn secondary" data-action="nav" data-page="catalogue">Back to Catalogue</button>`)}

    <form class="form-shell" data-submit="save-book" novalidate>
      <section class="form-section">
        <h2>Book information</h2>
        <div class="field-grid">
          <div class="field">
            <label for="bf-title">Title</label>
            <input id="bf-title" data-bind="form.title" value="${esc(f.title)}" placeholder="e.g. Things Fall Apart" />
            ${err(!f.title.trim(), "Title is required.")}
          </div>
          <div class="field">
            <label for="bf-author">Author</label>
            <input id="bf-author" data-bind="form.author" value="${esc(f.author)}" placeholder="e.g. Chinua Achebe" />
            ${err(!f.author.trim(), "Author is required.")}
          </div>
          <div class="field">
            <label for="bf-category">Category</label>
            <select id="bf-category" data-bind="form.category" data-rerender>
              ${f.category ? "" : `<option value="" selected disabled>Choose a category</option>`}
              ${categories().map((c) => `<option value="${esc(c)}" ${f.category === c ? "selected" : ""}>${esc(c)}</option>`).join("")}
            </select>
            ${err(!f.category, "Category is required.")}
          </div>
          <div class="field">
            <label for="bf-dewey">Dewey number <span class="helper">(optional)</span></label>
            <input id="bf-dewey" data-bind="form.dewey" value="${esc(f.dewey)}" placeholder="e.g. 823.914" inputmode="decimal" />
            ${err(f.dewey.trim() && !DEWEY_PATTERN.test(f.dewey.trim()), "Use three digits, optionally with decimals, e.g. 510 or 823.914.")}
          </div>
          ${edit
            ? `<div class="field"><label>Copies</label><p class="helper">Add or remove individual copies from the title's details window.</p></div>`
            : `<div class="field">
                 <label for="bf-copies">Number of copies</label>
                 <input id="bf-copies" type="number" min="1" max="100" data-bind="form.copies" data-number value="${esc(f.copies)}" />
                 <p class="helper">Physical copies that can be assigned from the library desk.</p>
               </div>`}
        </div>
      </section>
      <div class="button-row">
        <button class="btn primary" type="submit" ${state.busy ? "disabled" : ""}>${edit ? "Save Changes" : "Add Book"}</button>
        <button class="btn secondary" type="button" data-action="nav" data-page="catalogue">Cancel</button>
      </div>
    </form>`;
}

function saveBook() {
  const f = state.form;
  f.touched = true;
  const category = f.category;
  const dewey = f.dewey.trim();
  if (!f.title.trim() || !f.author.trim() || !category || (dewey && !DEWEY_PATTERN.test(dewey))) {
    render();
    return;
  }
  if (f.mode === "edit") {
    mutate(() => api("/api/titles", {
      method: "PUT",
      body: { title: f.origTitle, author: f.origAuthor, new_title: f.title, new_author: f.author, new_category: category, new_dewey: dewey },
    }), { after: () => go("catalogue") });
  } else {
    mutate(() => api("/api/titles", {
      method: "POST",
      body: { title: f.title, author: f.author, category, dewey, copies: f.copies },
    }), { after: () => { resetBookForm("add"); go("catalogue"); } });
  }
}

function resetAssign(t = null, borrower = null) {
  state.assign = {
    userid: borrower?.userid || "",
    borrowerQuery: borrower?.name || "",
    items: t ? [{ key: t.key, copies: 1 }] : [],
    bookQuery: "",
    issued: todayISO(),
    dueDate: addDaysISO(todayISO(), DEFAULT_LOAN_DAYS),
    staff: isStaff() ? state.me.name
      : (state.me?.staff || [""])[0],
  };
}

function renderAssign() {
  const a = state.assign;
  const borrower = borrowerById(a.userid);
  const items = a.items.map((it) => ({ ...it, t: titleByKey(it.key) })).filter((it) => it.t);
  const picked = new Set(items.map((it) => it.key));
  const bq = a.borrowerQuery.trim().toLowerCase();
  const tq = a.bookQuery.trim().toLowerCase();
  const borrowerSuggestions = !borrower && bq
    ? state.borrowers.filter((b) => `${b.name} ${b.email} ${b.group || ""}`.toLowerCase().includes(bq)).slice(0, 6)
    : [];
  const bookSuggestions = tq
    ? state.titles.filter((x) => !picked.has(x.key) && `${x.title} ${x.author}`.toLowerCase().includes(tq)).slice(0, 6)
    : [];
  const itemProblem = (it) => it.t.available < 1 ? "Every copy is on loan."
    : !(it.copies >= 1) ? "At least 1 copy."
    : it.copies > it.t.available ? `Only ${it.t.available} available.` : "";
  const totalCopies = items.reduce((n, it) => n + (it.copies || 0), 0);
  const badDates = a.dueDate < a.issued;
  const alreadyOut = borrower ? loansFor(borrower.userid).length : 0;
  const overLimit = borrower && alreadyOut + totalCopies > MAX_LOANS;
  const canSubmit = borrower && items.length && !items.some(itemProblem) && a.staff && a.dueDate && !badDates && !state.busy;

  return `
    ${pageHead("Checkout", "Assign Book",
      "Choose a borrower and one or more available titles, confirm the dates, then record the loan. The borrower gets one confirmation email.",
      `<button class="btn secondary" data-action="nav" data-page="${homePage()}">Back to ${isAdmin() ? "Dashboard" : "Library"}</button>`)}

    <section class="assignment-grid">
      <form class="form-shell" data-submit="submit-assign" novalidate>
        <section class="form-section">
          <h2>Borrower</h2>
          <div class="field autocomplete">
            <label for="as-borrower">Search borrower</label>
            <input id="as-borrower" data-bind="assign.borrowerQuery" data-rerender data-clear="assign.userid" value="${esc(a.borrowerQuery)}" placeholder="Type a name, email or group" autocomplete="off" />
            ${borrowerSuggestions.length ? `<div class="suggestions">${borrowerSuggestions.map((b) => `
              <button type="button" data-action="pick-borrower" data-id="${esc(b.userid)}">
                <span>${esc(b.name)}<br /><small>${esc(b.email)}</small></span>
                <span class="row-actions">${groupBadge(b.group)}<span class="badge ${b.overdue ? "red" : "green"}">${b.active} on loan</span></span>
              </button>`).join("")}</div>` : ""}
            ${borrower
              ? `<p class="helper">Selected: ${esc(borrower.name)} · ${esc(borrower.group || "no group")} · ${plural(borrower.active, "book")} on loan${borrower.overdue ? `, <strong style="color:var(--red-700)">${borrower.overdue} overdue</strong>` : ""}</p>`
              : bq && !borrowerSuggestions.length ? `<p class="validation">No borrower matches "${esc(a.borrowerQuery)}".</p>` : ""}
            ${borrower && alreadyOut ? `
              <ul class="helper" style="margin:6px 0 0;padding-left:18px;">
                ${loansFor(borrower.userid).map((l) => `<li>${esc(l.title)} · due ${formatDate(l.due)}${l.days_overdue ? ` <span class="badge red">${l.days_overdue}d late</span>` : ""}</li>`).join("")}
              </ul>` : ""}
            ${overLimit ? `<p class="validation">The limit is ${MAX_LOANS} books per borrower. ${esc(borrower.name)} already has ${alreadyOut}; this would make ${alreadyOut + totalCopies}.</p>` : ""}
          </div>
        </section>

        <section class="form-section">
          <h2>Books</h2>
          <div class="field autocomplete">
            <label for="as-book">${items.length ? "Add another book" : "Search book"}</label>
            <input id="as-book" data-bind="assign.bookQuery" data-rerender value="${esc(a.bookQuery)}" placeholder="Type a title or author" autocomplete="off" />
            ${bookSuggestions.length ? `<div class="suggestions">${bookSuggestions.map((x) => `
              <button type="button" data-action="pick-title" data-key="${esc(x.key)}" ${x.available ? "" : "disabled"}>
                <span>${esc(x.title)}<br /><small>${esc(x.author)}</small></span>${availabilityBadge(x)}
              </button>`).join("")}</div>` : ""}
            ${tq && !bookSuggestions.length ? `<p class="validation">No other title matches "${esc(a.bookQuery)}".</p>` : ""}
          </div>
          ${items.length ? `
            <div class="picked-list">
              ${items.map((it, i) => `
                <div class="picked-row">
                  <span>${esc(it.t.title)}<br /><small class="meta">${esc(it.t.author)} · ${it.t.available} of ${it.t.total} available</small>
                    ${itemProblem(it) ? `<span class="validation">${esc(itemProblem(it))}</span>` : ""}</span>
                  <label class="picked-copies">Copies
                    <input type="number" min="1" max="${Math.max(1, it.t.available)}" data-bind="assign.items.${i}.copies" data-number data-rerender value="${esc(it.copies)}" />
                  </label>
                  <button type="button" class="icon-button" title="Remove this book" data-action="remove-assign-item" data-key="${esc(it.key)}">${icons.x}</button>
                </div>`).join("")}
            </div>` : `<p class="helper">Pick as many titles as the borrower is taking today.</p>`}
        </section>

        <section class="form-section">
          <h2>Loan details</h2>
          <div class="field-grid">
            <div class="field">
              <label for="as-staff">Assigned by</label>
              ${isStaff()
                ? `<input id="as-staff" value="${esc(a.staff)}" disabled />`
                : `<select id="as-staff" data-bind="assign.staff" data-rerender>
                     ${(state.me.staff || []).map((s) => `<option ${a.staff === s ? "selected" : ""}>${esc(s)}</option>`).join("")}
                   </select>`}
            </div>
            <div class="field">
              <label for="as-issued">Assigned date</label>
              <input id="as-issued" type="date" data-bind="assign.issued" data-rerender value="${esc(a.issued)}" />
            </div>
            <div class="field">
              <label for="as-due">Due date</label>
              <input id="as-due" type="date" data-bind="assign.dueDate" data-rerender value="${esc(a.dueDate)}" />
              ${badDates ? `<div class="validation">Due date is before the assigned date.</div>` : `<p class="helper">Default loan period is ${DEFAULT_LOAN_DAYS} days.</p>`}
            </div>
          </div>
        </section>
      </form>

      <aside class="summary-card">
        <h2>Loan summary</h2>
        <div class="summary-list">
          ${summaryRow("Borrower", borrower?.name || "Not selected")}
          ${summaryRow("Group", borrower ? borrower.group || "Not set" : "-")}
          ${borrower ? summaryRow("Already on loan", `${alreadyOut} of ${MAX_LOANS}`) : ""}
          ${items.length
            ? items.map((it) => summaryRow(it.t.title, `× ${it.copies || 0}`)).join("")
            : summaryRow("Books", "Not selected")}
          ${items.length > 1 ? summaryRow("Total", plural(totalCopies, "book")) : ""}
          ${summaryRow("Assigned", formatDate(a.issued))}
          ${summaryRow("Due", formatDate(a.dueDate))}
          ${summaryRow("Staff", a.staff || "-")}
        </div>
        <button class="btn primary" style="width:100%;" data-action="submit-assign" ${canSubmit ? "" : "disabled"}>${state.busy ? "Saving..." : totalCopies > 1 ? `Assign ${totalCopies} Books` : "Assign Book"}</button>
      </aside>
    </section>`;
}

function summaryRow(label, value) {
  return `<div class="summary-row"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
}

function submitAssign() {
  const a = state.assign;
  const items = a.items
    .map((it) => ({ t: titleByKey(it.key), copies: it.copies }))
    .filter((it) => it.t)
    .map((it) => ({ title: it.t.title, author: it.t.author, copies: it.copies }));
  if (!items.length || !a.userid) return;
  mutate(() => api("/api/loans", {
    method: "POST",
    body: { userid: a.userid, items, issued: a.issued, due: a.dueDate, assigned_by: a.staff },
  }), { after: () => { resetAssign(); go(homePage()); } });
}

function renderBorrowers() {
  const q = state.borrowerSearch.trim().toLowerCase();
  const groupFilter = state.borrowerGroup;
  const list = state.borrowers.filter((b) => {
    const matchesSearch = !q || `${b.name} ${b.email} ${b.group || ""}`.toLowerCase().includes(q);
    const matchesGroup =
      groupFilter === "All groups" || (groupFilter === "No group" ? !b.group : b.group === groupFilter);
    return matchesSearch && matchesGroup;
  });
  const ungrouped = state.borrowers.filter((b) => !b.group).length;

  return `
    ${pageHead("Borrowers", "Borrower records",
      "Everyone who can borrow books from the library.",
      `<button class="btn primary" data-action="open-borrower-form">${icons.plus} Add Borrower</button>`)}

    <section class="toolbar compact">
      <div class="search-field">
        ${icons.search}
        <input type="search" data-bind="borrowerSearch" data-rerender value="${esc(state.borrowerSearch)}" placeholder="Search by name or email" />
      </div>
      <select data-bind="borrowerGroup" data-rerender aria-label="Group">
        ${["All groups", ...state.me.groups, "No group"].map((g) => `<option ${groupFilter === g ? "selected" : ""}>${esc(g)}</option>`).join("")}
      </select>
      <span class="badge ${ungrouped ? "amber" : "green"}">${ungrouped ? `${ungrouped} without a group` : "All grouped"}</span>
    </section>

    <p class="result-count">${plural(list.length, "borrower")}</p>

    <article class="panel borrower-table-panel">
      <div class="table-wrap">
        <table class="borrower-table">
          <thead><tr><th>Borrower</th><th>Group</th><th>Email</th><th>On loan</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            ${list.length ? list.map((b) => `
              <tr>
                <td>
                  <div class="borrower-top">
                    <div class="avatar">${esc(initials(b.name))}</div>
                    <button class="item-title" data-action="view-borrower" data-id="${esc(b.userid)}">${esc(b.name)}</button>
                    ${b.role === "staff" ? `<span class="badge amber">Staff</span>` : ""}
                  </div>
                </td>
                <td>${groupBadge(b.group)}</td>
                <td>${esc(b.email)}</td>
                <td><span class="badge blue">${b.active} on loan</span></td>
                <td><span class="badge ${b.overdue ? "red" : "green"}">${b.overdue ? `${b.overdue} overdue` : "On track"}</span></td>
                <td>
                  <div class="table-actions">
                    <button class="btn secondary small" data-action="view-borrower" data-id="${esc(b.userid)}">View</button>
                    <button class="btn text small" data-action="open-assign" data-id="${esc(b.userid)}">Assign</button>
                    <button class="btn text small" data-action="open-borrower-form" data-id="${esc(b.userid)}">Edit</button>
                  </div>
                </td>
              </tr>`).join("") : `<tr><td colspan="6"><div class="empty-inline">No borrowers match this search.</div></td></tr>`}
          </tbody>
        </table>
      </div>
    </article>`;
}

function renderBorrowerDetail() {
  const b = borrowerById(state.selectedBorrowerId);
  if (!b) return `<section class="empty-state"><h2>Borrower not found</h2></section>`;
  const loans = loansFor(b.userid);
  const labels = copyLabels(loans);
  const overdue = loans.filter((l) => l.days_overdue > 0).length;
  const history = state.borrowerHistory;

  return `
    ${pageHead(`Borrower · Library ID ${b.userid}`, b.name, `${b.group || "No group"} · ${b.email}`,
      `<button class="btn primary" data-action="open-assign" data-id="${esc(b.userid)}">${icons.plus} Assign Book</button>
       <button class="btn secondary" data-action="open-borrower-form" data-id="${esc(b.userid)}">${icons.edit} Edit</button>
       <button class="btn secondary" data-action="nav" data-page="borrowers">Back</button>`)}

    <section class="metrics-grid">
      ${metric("On loan", loans.length, "Physical copies", "blue", "Live")}
      ${metric("Overdue", overdue, overdue ? "Needs attention" : "Nothing overdue", overdue ? "red" : "green", overdue ? "Action" : "Clear")}
      ${metric("Group", b.group || "Not set", "Y1, Y2 or Faculty", b.group ? "green" : "amber", b.group ? "Set" : "Missing")}
      ${metric("Returned", history ? history.length : "...", "Books returned so far", "green", "History")}
    </section>

    <article class="panel">
      <div class="panel-header">
        <h2>Books on loan</h2>
        ${loans.length ? `<button class="btn secondary small" data-action="open-return" data-id="${esc(b.userid)}">${icons.check} Return books</button>` : ""}
      </div>
      <div class="borrowed-list">
        ${loans.length ? loans.map((loan, i) => `
          <div class="borrowed-row with-actions">
            ${cover(loan.title, loan.author, "cover-sm")}
            <div>
              ${titleLink(loan.title, loan.author)}
              <div class="meta">${labels[i]}Assigned ${formatDate(loan.issued)} by ${esc(loan.assigned_by || "-")} · Due ${formatDate(loan.due)}</div>
            </div>
            ${dueBadge(loan)}
            ${loanActions(loan)}
          </div>`).join("") : `<div class="empty-panel">No books on loan.</div>`}
      </div>
    </article>

    <article class="panel" style="margin-top:20px;">
      <div class="panel-header"><h2>Return history</h2></div>
      ${history === null ? `<div class="empty-panel">Loading...</div>`
        : history.length ? renderReturnsTable(history, false) : `<div class="empty-panel">No returns recorded yet.</div>`}
    </article>`;
}

function filteredLoans() {
  const q = state.loanSearch.trim().toLowerCase();
  return state.loans.filter((l) => {
    const matchesSearch = !q || `${l.title} ${l.borrower} ${l.assigned_by} ${l.group || ""}`.toLowerCase().includes(q);
    const s = state.loanStatus;
    const matchesStatus =
      s === "All loans" ||
      (s === "Overdue" && l.days_overdue > 0) ||
      (s === "Due in 7 days" && l.days_overdue === 0 && daysUntil(l.due) <= 7) ||
      (s === "On track" && l.days_overdue === 0);
    return matchesSearch && matchesStatus;
  });
}

function renderOperations() {
  const history = state.opsTab === "history";
  const loans = filteredLoans();
  const q = state.loanSearch.trim().toLowerCase();
  const returns = state.returns.filter((r) => !q || `${r.title} ${r.borrower} ${r.returned_by}`.toLowerCase().includes(q));

  return `
    ${pageHead("Operations", "Circulation", "Active loans with return and extend actions, plus the record of returned books.",
      `<button class="btn primary" data-action="open-assign">${icons.plus} Assign Book</button>`)}

    <div class="tabs" role="tablist">
      <button class="${history ? "" : "active"}" data-action="ops-tab" data-tab="active">Active loans (${state.loans.length})</button>
      <button class="${history ? "active" : ""}" data-action="ops-tab" data-tab="history">Return history</button>
    </div>

    <section class="toolbar compact">
      <div class="search-field">
        ${icons.search}
        <input type="search" data-bind="loanSearch" data-rerender value="${esc(state.loanSearch)}" placeholder="Search by title, borrower or staff" />
      </div>
      ${history ? "<span></span>" : `
        <select data-bind="loanStatus" data-rerender aria-label="Status">
          ${["All loans", "Overdue", "Due in 7 days", "On track"].map((s) => `<option ${state.loanStatus === s ? "selected" : ""}>${s}</option>`).join("")}
        </select>`}
      <span></span>
    </section>

    <article class="panel">
      ${history
        ? !state.returnsLoaded ? `<div class="empty-panel">Loading...</div>`
          : returns.length ? renderReturnsTable(returns, true) : `<div class="empty-panel">No returns found.</div>`
        : loans.length ? renderLoansTable(loans, true) : `<div class="empty-panel">No loans match.</div>`}
    </article>
    ${history && state.returnsLoaded ? `<p class="result-count" style="margin-top:12px;">Showing the latest ${state.returns.length} returns.</p>` : ""}`;
}

function loanCountMeta(loan) {
  const n = loansFor(loan.userid).length;
  const count = n >= MAX_LOANS ? `<span style="color:var(--red-700);font-weight:600;">${plural(n, "book")} out</span>` : `${plural(n, "book")} out`;
  return `<div class="meta">${loan.group ? `${esc(loan.group)} · ` : ""}${count}</div>`;
}

function renderStaffLoans() {
  const loans = filteredLoans();
  const atLimit = new Set(state.loans.map((l) => l.userid).filter((id) => loansFor(id).length >= MAX_LOANS)).size;
  return `
    ${pageHead("Circulation", "Books on loan",
      `Every book currently out. A student may hold at most ${MAX_LOANS} books; check here before assigning more.`,
      `<button class="btn secondary" data-action="open-return">${icons.check} Return Book</button>`)}

    <section class="toolbar compact">
      <div class="search-field">
        ${icons.search}
        <input type="search" data-bind="loanSearch" data-rerender value="${esc(state.loanSearch)}" placeholder="Search by title, borrower or staff" />
      </div>
      <select data-bind="loanStatus" data-rerender aria-label="Status">
        ${["All loans", "Overdue", "Due in 7 days", "On track"].map((s) => `<option ${state.loanStatus === s ? "selected" : ""}>${s}</option>`).join("")}
      </select>
      <span class="badge ${atLimit ? "red" : "green"}">${atLimit ? `${plural(atLimit, "borrower")} at the ${MAX_LOANS}-book limit` : "Nobody at the limit"}</span>
    </section>

    <p class="result-count">${plural(loans.length, "book")} on loan</p>

    <article class="panel">
      ${loans.length ? renderLoansTable(loans, true) : `<div class="empty-panel">No loans match.</div>`}
    </article>`;
}

function renderLoansTable(rows, withActions) {
  return `
    <div class="table-wrap">
      <table>
        <thead><tr><th>Book</th><th>Borrower</th><th>Assigned</th><th>Due</th><th>Assigned by</th><th>Status</th>${withActions ? "<th>Actions</th>" : ""}</tr></thead>
        <tbody>
          ${rows.map((loan) => `
            <tr>
              <td><div class="row-book">${cover(loan.title, loan.author, "cover-sm")}${titleLink(loan.title, loan.author)}</div></td>
              <td>${borrowerLink(loan.userid, loan.borrower)}${loanCountMeta(loan)}</td>
              <td>${formatDate(loan.issued)}</td>
              <td>${formatDate(loan.due)}</td>
              <td>${esc(loan.assigned_by || "-")}</td>
              <td>${dueBadge(loan)}</td>
              ${withActions ? `<td>${loanActions(loan)}</td>` : ""}
            </tr>`).join("")}
        </tbody>
      </table>
    </div>`;
}

function renderReturnsTable(rows, withBorrower, withStaff = true) {
  return `
    <div class="table-wrap">
      <table>
        <thead><tr><th>Book</th>${withBorrower ? "<th>Borrower</th>" : ""}<th>Borrowed</th><th>Returned</th>${withStaff ? "<th>Processed by</th>" : ""}</tr></thead>
        <tbody>
          ${rows.map((r) => `
            <tr>
              <td>${esc(r.title)}</td>
              ${withBorrower ? `<td>${borrowerById(r.userid) ? borrowerLink(r.userid, r.borrower) : esc(r.borrower)}</td>` : ""}
              <td>${formatDate(r.issued)}</td>
              <td>${formatDate(r.returned)}</td>
              ${withStaff ? `<td>${esc(r.returned_by || "-")}</td>` : ""}
            </tr>`).join("")}
        </tbody>
      </table>
    </div>`;
}

function renderMyBooks() {
  const { current, history } = state.myBooks;
  const overdue = current.filter((l) => l.days_overdue > 0).length;
  return `
    ${pageHead("My books", `Hello, ${state.me.name}`, "Your current loans and the books you have returned. Visit the library desk to borrow, return or extend a book.")}

    <section class="metrics-grid">
      ${metric("On loan", current.length, "Books you have now", "blue", "Now")}
      ${metric("Overdue", overdue, overdue ? "Please return these soon" : "You're all caught up", overdue ? "red" : "green", overdue ? "Action" : "Clear")}
      ${metric("Returned", history.length, "Books returned so far", "green", "History")}
      ${metric("Next due", current.length ? formatDate(current[0].due) : "-", current.length ? current[0].title : "Nothing to return", "amber", "Date")}
    </section>

    <article class="panel">
      <div class="panel-header"><h2>Books on loan</h2><span class="badge ${overdue ? "red" : "green"}">${current.length} on loan</span></div>
      <div class="borrowed-list">
        ${current.length ? current.map((loan) => `
          <div class="borrowed-row">
            ${cover(loan.title, loan.author, "cover-sm")}
            <div>
              <span class="item-title">${esc(loan.title)}</span>
              <div class="meta">${esc(loan.author)}<br />Borrowed ${formatDate(loan.issued)} · Due ${formatDate(loan.due)}</div>
            </div>
            ${dueBadge(loan)}
          </div>`).join("") : `<div class="empty-panel">You have no books on loan. Browse the library to find your next read.</div>`}
      </div>
    </article>

    <article class="panel" style="margin-top:20px;">
      <div class="panel-header"><h2>Returned books</h2></div>
      ${history.length ? renderReturnsTable(history, false, false) : `<div class="empty-panel">No returns yet.</div>`}
    </article>`;
}

const JSTOR_URL = "https://www.jstor.org";

function renderDigitalLibrary() {
  const steps = [
    `Go to <a href="${JSTOR_URL}" target="_blank" rel="noopener">www.jstor.org</a>`,
    `Click the <span class="jstor-login-chip">Log in</span> button in the top-right corner`,
    `Select <strong>"Continue with Google"</strong>`,
    `Log in using your AOA email (e.g. <strong>studentname@aoa.school</strong>)`,
  ];
  return `
    ${pageHead("AOA Digital Library · with JSTOR", "Explore the world's knowledge, cultures, and ideas",
      "Read journals, books and primary sources online through JSTOR, using your AOA Google account.",
      `<a class="btn primary" href="${JSTOR_URL}" target="_blank" rel="noopener">Open JSTOR ${icons.arrow}</a>`)}

    <section class="digital-grid">
      <article class="panel">
        <div class="panel-header"><h2>How to log in</h2></div>
        <ol class="login-steps">
          ${steps.map((step, i) => `<li><span class="step-number">${i + 1}</span><span>${step}</span></li>`).join("")}
        </ol>
      </article>
      <aside class="panel digital-note">
        <h2>Good to know</h2>
        <p>Use your school Google account, the same one you use for this library.</p>
        <p>The digital library is available anywhere, at any time. Physical books are still borrowed in person at the library desk.</p>
        <a class="btn secondary" href="${JSTOR_URL}" target="_blank" rel="noopener">Go to www.jstor.org</a>
      </aside>
    </section>`;
}

function modalShell(label, body, { small = false } = {}) {
  return `
    <div class="modal-backdrop" data-action="backdrop">
      <article class="modal ${small ? "small-modal" : ""}" role="dialog" aria-modal="true" aria-label="${esc(label)}">
        ${body}
      </article>
    </div>`;
}

function modalTop(eyebrow, title, lead = "") {
  return `
    <div class="modal-top">
      <div>
        <p class="eyebrow">${esc(eyebrow)}</p>
        <h1>${esc(title)}</h1>
        ${lead ? `<p class="lead">${esc(lead)}</p>` : ""}
      </div>
      <button class="icon-button" data-action="close-modal" title="Close">${icons.x}</button>
    </div>`;
}

function renderModal() {
  const m = state.modal;
  if (m.type === "title") return renderTitleModal(m);
  if (m.type === "borrower-form") return renderBorrowerFormModal(m);
  if (m.type === "return") return renderReturnModal(m);
  if (m.type === "extend") return renderExtendModal(m);
  if (m.type === "confirm") {
    return modalShell(m.title, `
      ${modalTop("Please confirm", m.title)}
      <p class="confirm-text">${esc(m.message)}</p>
      <div class="button-row">
        <button class="btn danger-solid" data-action="confirm-yes" ${state.busy ? "disabled" : ""}>${esc(m.confirmLabel || "Confirm")}</button>
        <button class="btn secondary" data-action="close-modal">Cancel</button>
      </div>`, { small: true });
  }
  return "";
}

function renderTitleModal(m) {
  const t = titleByKey(m.key);
  if (!t) return "";
  const admin = isAdmin();
  const copies = m.copies;
  return modalShell(`${t.title} details`, `
    ${modalTop("Book details", t.title)}
    <div class="details-layout">
      ${cover(t.title, t.author, "cover-lg")}
      <div>
        <p class="lead">${esc(t.author)}</p>
        <div class="button-row" style="margin-top:12px;"><span class="badge blue">${esc(t.category)}</span>${deweyBadge(t)}${availabilityBadge(t)}</div>
        <div class="details-meta">
          <div class="mini-stat"><strong>${t.total}</strong><span>Total copies</span></div>
          <div class="mini-stat"><strong>${t.available}</strong><span>Available</span></div>
          <div class="mini-stat"><strong>${t.total - t.available}</strong><span>On loan</span></div>
        </div>
        ${admin ? `
          <div class="button-row" style="margin-bottom:16px;">
            <button class="btn primary" data-action="open-assign" data-key="${esc(t.key)}" ${t.available ? "" : "disabled"}>${icons.plus} Assign</button>
            <button class="btn secondary" data-action="open-book-form" data-mode="edit" data-key="${esc(t.key)}">${icons.edit} Edit title</button>
            <button class="btn secondary" data-action="add-copy" data-key="${esc(t.key)}" ${state.busy ? "disabled" : ""}>${icons.plus} Add a copy</button>
          </div>
          <h3>Copies</h3>
          ${copies === null ? `<div class="empty-panel">Loading copies...</div>` : `
            <div class="table-wrap">
              <table class="copies-table">
                <thead><tr><th>Copy</th><th>Status</th><th>Due</th><th></th></tr></thead>
                <tbody>
                  ${copies.map((c, i) => `
                    <tr>
                      <td><strong>Copy ${i + 1}</strong></td>
                      <td>${c.available ? `<span class="badge green">On shelf</span>` : `On loan to ${borrowerLink(c.userid, c.borrower || "unknown")}`}</td>
                      <td>${c.available ? "-" : `${formatDate(c.due)}${c.days_overdue ? ` <span class="badge red">${c.days_overdue}d late</span>` : ""}`}</td>
                      <td>${c.available
                        ? `<button class="btn text danger small" data-action="confirm-delete-copy" data-book="${esc(c.book_id)}" data-copy="${i + 1}" data-key="${esc(t.key)}">Delete</button>`
                        : `<button class="btn text small" data-action="open-return" data-id="${esc(c.userid)}" data-book="${esc(c.book_id)}">Return</button>`}</td>
                    </tr>`).join("")}
                </tbody>
              </table>
            </div>`}`
        : isStaff()
          ? `<div class="button-row" style="margin-bottom:16px;"><button class="btn primary" data-action="open-assign" data-key="${esc(t.key)}" ${t.available ? "" : "disabled"}>${icons.plus} Assign to a student</button></div>
             ${renderStaffLoansForTitle(t)}`
          : `<p class="helper">${t.available ? "Visit the library desk to borrow an available copy." : "All copies are on loan right now. Check back soon."}</p>`}
      </div>
    </div>`);
}

function renderStaffLoansForTitle(t) {
  const loans = state.loans.filter((l) => l.title.toLowerCase() === t.title.toLowerCase()
    && l.author.toLowerCase() === t.author.toLowerCase());
  if (!loans.length) return "";
  return `
    <h3>On loan</h3>
    <div class="table-wrap">
      <table class="copies-table">
        <thead><tr><th>Borrower</th><th>Due</th><th></th></tr></thead>
        <tbody>
          ${loans.map((l) => `
            <tr>
              <td>${esc(l.borrower)}</td>
              <td>${formatDate(l.due)}${l.days_overdue ? ` <span class="badge red">${l.days_overdue}d late</span>` : ""}</td>
              <td><button class="btn text small" data-action="open-return" data-id="${esc(l.userid)}" data-book="${esc(l.book_id)}">Return</button></td>
            </tr>`).join("")}
        </tbody>
      </table>
    </div>`;
}

function renderBorrowerFormModal(m) {
  const f = m.form;
  const err = (cond, msg) => (f.touched && cond ? `<div class="validation">${msg}</div>` : "");
  const editing = Boolean(m.userid);
  const b = editing ? borrowerById(m.userid) : null;
  return modalShell(editing ? "Edit borrower" : "Add borrower", `
    ${modalTop(editing ? "Edit borrower" : "Borrower registration", editing ? b?.name || "Borrower" : "Add Borrower",
      "Loan and return emails are sent to this address.")}
    <form data-submit="save-borrower" novalidate>
      <div class="field">
        <label for="bw-name">Full name</label>
        <input id="bw-name" data-bind="modal.form.name" value="${esc(f.name)}" placeholder="e.g. Akua Danquah" />
        ${err(!f.name.trim(), "Name is required.")}
      </div>
      <div class="field-grid">
        <div class="field">
          <label for="bw-group">Group</label>
          <select id="bw-group" data-bind="modal.form.group">
            ${editing && !f.group ? `<option value="" selected>Not set</option>` : ""}
            ${state.me.groups.map((g) => `<option ${f.group === g ? "selected" : ""}>${esc(g)}</option>`).join("")}
          </select>
        </div>
        <div class="field">
          <label for="bw-email">Email</label>
          <input id="bw-email" type="email" data-bind="modal.form.email" value="${esc(f.email)}" placeholder="name@aoa.school" />
          ${err(!/^\S+@\S+\.\S+$/.test(f.email.trim()), "A valid email is required.")}
        </div>
      </div>
      <div class="field">
        <label for="bw-role">Role</label>
        <select id="bw-role" data-bind="modal.form.role">
          <option value="borrower" ${f.role !== "staff" ? "selected" : ""}>Borrower: sees the library and their own books</option>
          <option value="staff" ${f.role === "staff" ? "selected" : ""}>Staff: can also assign and return books</option>
        </select>
      </div>
      <div class="button-row">
        <button class="btn primary" type="submit" ${state.busy ? "disabled" : ""}>${editing ? "Save Changes" : "Add Borrower"}</button>
        <button class="btn secondary" type="button" data-action="close-modal">Cancel</button>
        ${editing ? `<button class="btn text danger" type="button" data-action="confirm-delete-borrower" data-id="${esc(m.userid)}" style="margin-left:auto;">Delete borrower</button>` : ""}
      </div>
    </form>`, { small: true });
}

function renderReturnModal(m) {
  const b = borrowerById(m.userid);
  const loans = m.userid ? loansFor(m.userid) : [];
  const labels = copyLabels(loans);
  const selected = new Set(m.selected);
  const withLoans = m.pickBorrower
    ? state.borrowers.filter((x) => state.loans.some((l) => l.userid === x.userid))
    : [];
  return modalShell("Return books", `
    ${modalTop("Return books", b?.name || "Choose a borrower", "Tick every book being handed back. The borrower gets a thank-you email.")}
    <form data-submit="submit-return" novalidate>
      ${m.pickBorrower ? `
        <div class="field">
          <label for="rt-borrower">Borrower</label>
          <select id="rt-borrower" data-bind="modal.userid" data-reset-return data-rerender>
            <option value="" ${m.userid ? "" : "selected"}>Select a borrower...</option>
            ${withLoans.map((x) => `<option value="${esc(x.userid)}" ${m.userid === x.userid ? "selected" : ""}>${esc(x.name)} (${plural(loansFor(x.userid).length, "book")})</option>`).join("")}
          </select>
        </div>` : ""}
      ${loans.length > 1 ? `
        <div class="check-all">
          <button class="btn text small" type="button" data-action="toggle-return-all">
            ${selected.size === loans.length ? "Clear selection" : `Select all ${loans.length}`}
          </button>
        </div>` : ""}
      <div class="check-list">
        ${loans.length ? loans.map((loan, i) => `
          <label class="check-row ${selected.has(loan.book_id) ? "selected" : ""}">
            <input type="checkbox" data-action="toggle-return" data-book="${esc(loan.book_id)}" ${selected.has(loan.book_id) ? "checked" : ""} />
            <span>${esc(loan.title)}<br /><small class="meta">${labels[i]}Due ${formatDate(loan.due)}</small></span>
            ${dueBadge(loan)}
          </label>`).join("") : m.userid ? `<div class="empty-panel">This borrower has no books on loan.</div>` : ""}
      </div>
      <div class="field-grid">
        <div class="field">
          <label for="rt-by">Returned to</label>
          ${isStaff()
            ? `<input id="rt-by" value="${esc(m.returnedBy)}" disabled />`
            : `<select id="rt-by" data-bind="modal.returnedBy">
                 ${state.me.staff.map((s) => `<option ${m.returnedBy === s ? "selected" : ""}>${esc(s)}</option>`).join("")}
               </select>`}
        </div>
        <div class="field">
          <label for="rt-date">Return date</label>
          <input id="rt-date" type="date" data-bind="modal.returned" value="${esc(m.returned)}" />
        </div>
      </div>
      <div class="button-row">
        <button class="btn primary" type="submit" ${selected.size && !state.busy ? "" : "disabled"}>Return ${plural(selected.size, "book")}</button>
        <button class="btn secondary" type="button" data-action="close-modal">Cancel</button>
      </div>
    </form>`, { small: true });
}

function renderExtendModal(m) {
  const loan = state.loans.find((l) => l.userid === m.userid && l.book_id === m.bookId);
  if (!loan) return "";
  return modalShell("Extend due date", `
    ${modalTop("Extend due date", loan.title, `${loan.borrower} · currently due ${formatDate(loan.due)}`)}
    <form data-submit="submit-extend" novalidate>
      <div class="field">
        <label for="ex-due">New due date</label>
        <input id="ex-due" type="date" data-bind="modal.due" value="${esc(m.due)}" />
        <div class="button-row" style="margin-top:8px;">
          ${[7, 14].map((d) => `<button class="btn text small" type="button" data-action="extend-by" data-days="${d}">+${d} days from today</button>`).join("")}
        </div>
      </div>
      <div class="button-row">
        <button class="btn primary" type="submit" ${m.due && !state.busy ? "" : "disabled"}>Save new due date</button>
        <button class="btn secondary" type="button" data-action="close-modal">Cancel</button>
      </div>
    </form>`, { small: true });
}

async function openTitleModal(key) {
  state.openMenuKey = null;
  const t = titleByKey(key);
  if (!t) return;
  state.modal = { type: "title", key, copies: isAdmin() ? null : [] };
  render();
  if (!isAdmin()) return;
  try {
    const data = await api(`/api/copies?title=${encodeURIComponent(t.title)}&author=${encodeURIComponent(t.author)}`);
    if (state.modal?.type === "title" && state.modal.key === key) {
      state.modal.copies = data.copies;
      render();
    }
  } catch (err) {
    showToast(err.message, "error");
  }
}

function openReturnModal(userid, bookId) {
  state.modal = {
    type: "return",
    userid: userid ? String(userid) : "",
    pickBorrower: !userid,
    selected: bookId ? [String(bookId)] : userid ? loansFor(userid).map((l) => l.book_id) : [],
    returnedBy: isStaff() ? state.me.name : state.me.staff[0],
    returned: todayISO(),
  };
  render();
}

function openConfirm(title, message, confirmLabel, onConfirm) {
  state.openMenuKey = null;
  state.modal = { type: "confirm", title, message, confirmLabel, onConfirm };
  render();
}

const actions = {
  nav: (d) => go(d.page),
  "open-assign": (d) => {
    const t = d.key ? titleByKey(d.key) : null;
    const b = d.id ? borrowerById(d.id) : null;
    resetAssign(t, b);
    go("assign");
  },
  "open-book-form": (d) => {
    resetBookForm(d.mode || "add", d.key ? titleByKey(d.key) : null);
    go("book-form");
  },
  "view-title": (d) => openTitleModal(d.key),
  "view-borrower": (d) => go("borrower", d.id),
  "toggle-menu": (d) => {
    state.openMenuKey = state.openMenuKey === d.key ? null : d.key;
    render();
  },
  "set-view": (d) => {
    state.catalogueView = d.view;
    state.openMenuKey = null;
    render();
  },
  "reset-filters": () => {
    state.filters = { search: "", category: "All categories", dewey: "All Dewey classes", availability: "All availability" };
    state.catalogueLimit = PAGE_SIZE;
    render();
  },
  "show-more": () => {
    state.catalogueLimit += PAGE_SIZE;
    render();
  },
  "pick-borrower": (d) => {
    const b = borrowerById(d.id);
    state.assign.userid = b.userid;
    state.assign.borrowerQuery = b.name;
    render();
  },
  "pick-title": (d) => {
    const t = titleByKey(d.key);
    if (!state.assign.items.some((it) => it.key === t.key)) state.assign.items.push({ key: t.key, copies: 1 });
    state.assign.bookQuery = "";
    render();
    document.getElementById("as-book")?.focus();
  },
  "remove-assign-item": (d) => {
    state.assign.items = state.assign.items.filter((it) => it.key !== d.key);
    render();
  },
  "submit-assign": () => submitAssign(),
  "add-copy": (d) => {
    const t = titleByKey(d.key);
    state.openMenuKey = null;
    const reopen = state.modal?.type === "title";
    mutate(() => api("/api/copies", { method: "POST", body: { title: t.title, author: t.author } }), {
      after: () => { if (reopen) openTitleModal(t.key); },
    });
  },
  "confirm-delete-title": (d) => {
    const t = titleByKey(d.key);
    openConfirm("Delete this title?", `All ${plural(t.total, "copy", "copies")} of "${t.title}" will be removed from the catalogue and kept in the deleted-books record. This only works when no copy is on loan.`,
      "Delete title", () => mutate(() => api("/api/titles", { method: "DELETE", body: { title: t.title, author: t.author } })));
  },
  "confirm-delete-copy": (d) => {
    const t = titleByKey(d.key);
    openConfirm("Delete this copy?", `Copy ${d.copy} of "${t.title}" will be removed from the catalogue.`, "Delete copy",
      () => mutate(() => api(`/api/copies/${encodeURIComponent(d.book)}`, { method: "DELETE" }), {
        after: () => { if (titleByKey(d.key)) openTitleModal(d.key); },
      }));
  },
  "open-borrower-form": (d) => {
    const b = d.id ? borrowerById(d.id) : null;
    state.modal = {
      type: "borrower-form",
      userid: b?.userid || null,
      form: { name: b?.name || "", email: b?.email || "", group: b ? b.group || "" : state.me.groups[0], role: b?.role || "borrower", touched: false },
    };
    render();
  },
  "confirm-delete-borrower": (d) => {
    const b = borrowerById(d.id);
    openConfirm("Delete this borrower?", `${b.name} (${b.email}) will be removed and will no longer be able to sign in. This only works when they have no books on loan.`,
      "Delete borrower", () => mutate(() => api(`/api/borrowers/${encodeURIComponent(b.userid)}`, { method: "DELETE" }), {
        after: () => { if (state.page === "borrower-detail") go("borrowers"); },
      }));
  },
  "open-return": (d) => openReturnModal(d.id, d.book),
  "toggle-return": (d, el) => {
    const set = new Set(state.modal.selected);
    if (el.checked) set.add(d.book);
    else set.delete(d.book);
    state.modal.selected = [...set];
    render();
  },
  "toggle-return-all": () => {
    const loans = loansFor(state.modal.userid);
    state.modal.selected = state.modal.selected.length === loans.length ? [] : loans.map((l) => l.book_id);
    render();
  },
  "open-extend": (d) => {
    const loan = state.loans.find((l) => l.userid === d.id && l.book_id === d.book);
    if (!loan) return;
    const base = loan.due > todayISO() ? loan.due : todayISO();
    state.modal = { type: "extend", userid: d.id, bookId: d.book, due: addDaysISO(base, 7) };
    render();
  },
  "extend-by": (d) => {
    state.modal.due = addDaysISO(todayISO(), Number(d.days));
    render();
  },
  "ops-tab": (d) => {
    state.opsTab = d.tab;
    render();
    if (d.tab === "history" && !state.returnsLoaded) {
      loadReturns().then(render).catch((err) => showToast(err.message, "error"));
    }
  },
  "ops-filter": (d) => {
    state.opsTab = "active";
    state.loanStatus = d.status;
    go("operations");
  },
  "confirm-yes": () => state.modal?.onConfirm?.(),
  "close-modal": () => {
    state.modal = null;
    render();
  },
};

const submits = {
  "save-book": () => saveBook(),
  "submit-assign": () => submitAssign(),
  "save-borrower": () => {
    const m = state.modal;
    const f = m.form;
    f.touched = true;
    if (!f.name.trim() || !/^\S+@\S+\.\S+$/.test(f.email.trim())) {
      render();
      return;
    }
    const body = { name: f.name, email: f.email, group: f.group, role: f.role };
    mutate(() => m.userid
      ? api(`/api/borrowers/${encodeURIComponent(m.userid)}`, { method: "PUT", body })
      : api("/api/borrowers", { method: "POST", body }));
  },
  "submit-return": () => {
    const m = state.modal;
    if (!m.selected.length) return;
    mutate(() => api("/api/loans/return", {
      method: "POST",
      body: { userid: m.userid, book_ids: m.selected, returned_by: m.returnedBy, returned: m.returned },
    }));
  },
  "submit-extend": () => {
    const m = state.modal;
    mutate(() => api("/api/loans/extend", { method: "POST", body: { userid: m.userid, book_id: m.bookId, due: m.due } }));
  },
};

function setPath(path, value) {
  const keys = path.split(".");
  let target = state;
  for (const key of keys.slice(0, -1)) target = target[key];
  target[keys[keys.length - 1]] = value;
}

ROOT.addEventListener("click", (event) => {
  const el = event.target.closest("[data-action]");
  if (!el || !ROOT.contains(el)) {
    if (state.openMenuKey && !event.target.closest(".overflow-wrap")) {
      state.openMenuKey = null;
      render();
    }
    return;
  }
  if (el.dataset.action === "backdrop") {
    if (event.target === el) actions["close-modal"]();
    return;
  }
  const handler = actions[el.dataset.action];
  if (!handler || el.disabled) return;
  if (el.tagName === "BUTTON" || el.tagName === "A") event.preventDefault();
  handler(el.dataset, el, event);
});

ROOT.addEventListener("input", (event) => {
  const el = event.target;
  if (!el.dataset.bind || el.type === "checkbox") return;
  setPath(el.dataset.bind, "number" in el.dataset ? Number(el.value) : el.value);
  if ("clear" in el.dataset) setPath(el.dataset.clear, "");
  if ("resetLimit" in el.dataset) state.catalogueLimit = PAGE_SIZE;
  if ("resetReturn" in el.dataset) state.modal.selected = loansFor(el.value).map((l) => l.book_id);
  if ("rerender" in el.dataset) renderKeepingFocus(el);
});

ROOT.addEventListener("change", (event) => {
  if ("viewAs" in event.target.dataset) switchView(event.target.value);
});

ROOT.addEventListener("submit", (event) => {
  event.preventDefault();
  const handler = submits[event.target.dataset.submit];
  if (handler && !state.busy) handler(event.target);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && (state.modal || state.openMenuKey)) {
    state.modal = null;
    state.openMenuKey = null;
    render();
  }
});

render();
boot();
