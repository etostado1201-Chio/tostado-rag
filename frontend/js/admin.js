/* Tostado Restaurant Group — admin console (full CRUD)
 *
 * Architecture
 * ------------
 *   - One auth flow that mints a JWT and stores it in sessionStorage.
 *   - One tab bar that toggles which resource is being managed.
 *   - One "stores tab" with a hybrid form (visual fields + advanced JSON).
 *   - One reusable JSON editor wired to vendors / brands / employees / departments.
 *
 *   The hybrid form keeps a single state object `storeState` that both modes
 *   read from and write to, so toggling between modes never loses input.
 */

const $  = (id) => document.getElementById(id);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));


/* ---------------------------------------------------------------- */
/* HTTP helpers                                                     */
/* ---------------------------------------------------------------- */

function getToken() {
  const session = JSON.parse(sessionStorage.getItem("tostado_admin") || "{}");
  return session.token || null;
}

async function api(method, path, body = null) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers["Authorization"] = "Bearer " + token;

  const init = { method, headers };
  if (body !== null) init.body = JSON.stringify(body);

  const res  = await fetch(path, init);
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}


/* ---------------------------------------------------------------- */
/* Status banners                                                   */
/* ---------------------------------------------------------------- */

function setStatus(el, msg, ok) {
  if (!el) return;
  el.textContent = msg;
  el.className = "status " + (ok ? "status--ok" : "status--err");
}
function clearStatus(el) {
  if (!el) return;
  el.textContent = "";
  el.className = "status";
}


/* ---------------------------------------------------------------- */
/* Auth                                                             */
/* ---------------------------------------------------------------- */

const loginCard    = $("loginCard");
const consoleCard  = $("consoleCard");
const loginStatus  = $("loginStatus");
const signedLabel  = $("signedInLabel");

function showAuthenticated(payload) {
  loginCard.classList.add("hidden");
  consoleCard.classList.remove("hidden");
  signedLabel.textContent = `Signed in as ${payload.username} (${payload.department})`;

  // Lazy-load the active tab's data on sign-in.
  showTab("stores");
}
function showAnonymous() {
  loginCard.classList.remove("hidden");
  consoleCard.classList.add("hidden");
}

const stored = sessionStorage.getItem("tostado_admin");
if (stored) {
  try { showAuthenticated(JSON.parse(stored)); } catch { showAnonymous(); }
}

$("loginBtn").addEventListener("click", async () => {
  const username = $("user").value.trim();
  const password = $("pass").value;
  if (!username || !password) {
    setStatus(loginStatus, "Email and password are required.", false);
    return;
  }
  const { ok, data } = await api("POST", "/api/login", { username, password });
  if (!ok) {
    setStatus(loginStatus, data.error || "Login failed.", false);
    return;
  }
  sessionStorage.setItem("tostado_admin", JSON.stringify(data));
  showAuthenticated(data);
});

$("logoutBtn").addEventListener("click", () => {
  sessionStorage.removeItem("tostado_admin");
  showAnonymous();
  setStatus(loginStatus, "Signed out.", true);
});


/* ---------------------------------------------------------------- */
/* Tabs                                                             */
/* ---------------------------------------------------------------- */

function showTab(name) {
  $$(".tab").forEach((t)      => t.classList.toggle("is-active", t.dataset.tab   === name));
  $$(".tabpanel").forEach((p) => p.classList.toggle("is-active", p.dataset.panel === name));

  // Auto-load the dataset on first tab activation.
  if (name === "stores") loadStores();
  else                   loadJsonDataset(name);
}
$$(".tab").forEach((t) => t.addEventListener("click", () => showTab(t.dataset.tab)));


/* ================================================================ */
/* STORES — hybrid form (visual + JSON)                             */
/* ================================================================ */

const storesList    = $("storesList");
const storeFilter   = $("storeFilter");
const storeEditor   = $("storeEditor");
const storeEditorTitle  = $("storeEditorTitle");
const storeEditorStatus = $("storeEditorStatus");
const storeJsonEl   = $("storeJsonTextarea");
const storeDeleteBtn = $("storeDeleteBtn");
const autogenInfo   = $("autogenInfo");

let allStores  = [];
let storeMode  = "visual";   // "visual" | "json"
let storeState = null;       // current record being edited (or null = creating)
let isEditingExistingStore = false;
let cachedBrands = [];

function emptyStore() {
  return {
    brand_id:  cachedBrands[0]?.id || "",
    status:    "active",
    address:   { street: "", city: "", state: "", zipcode: "" },
    phone:     "",
    opened_on: new Date().toISOString().slice(0, 10),
    manager:   { full_name: "", phone: "", email: "" },
  };
}

/* ---------- Load + render the store list ---------- */

async function loadStores() {
  const [storesRes, brandsRes] = await Promise.all([
    api("GET", "/api/admin/stores"),
    api("GET", "/api/admin/brands"),
  ]);
  if (!storesRes.ok) {
    storesList.textContent = storesRes.data.error || "Failed to load stores.";
    return;
  }
  allStores    = storesRes.data.records || [];
  cachedBrands = brandsRes.ok ? (brandsRes.data.records || []) : [];
  populateBrandSelect();
  renderStoreList();
}

function renderStoreList() {
  const q = (storeFilter.value || "").toLowerCase();
  const filtered = allStores.filter((s) => {
    if (!q) return true;
    const blob = `${s.store_id} ${s.brand_name} ${s.address?.city} ${s.status}`.toLowerCase();
    return blob.includes(q);
  });

  storesList.innerHTML = "";
  filtered.slice(0, 200).forEach((s) => {
    const row = document.createElement("div");
    row.className = "record-row";
    row.innerHTML = `
      <div>
        <span class="record-row__id">${s.store_id}</span>
        <span class="record-row__badge record-row__badge--${badgeClassForStatus(s.status)}">${s.status || "active"}</span>
      </div>
      <div class="record-row__meta">${s.brand_name} · ${s.address?.city || ""}, ${s.address?.state || ""}</div>
    `;
    row.addEventListener("click", () => openStoreEditor(s));
    storesList.appendChild(row);
  });

  if (filtered.length > 200) {
    const note = document.createElement("div");
    note.className = "record-row";
    note.innerHTML = `<em style="color: var(--ink-soft); font-size: 12px;">Showing 200 of ${filtered.length}. Filter to narrow.</em>`;
    storesList.appendChild(note);
  }
}

function badgeClassForStatus(status) {
  if (!status || status === "active") return "active";
  if (status === "closed")             return "closed";
  return "inactive";
}

storeFilter.addEventListener("input", renderStoreList);
$("storesRefreshBtn").addEventListener("click", loadStores);


/* ---------- Open the editor ---------- */

function populateBrandSelect() {
  const select = $("sf_brand");
  select.innerHTML = "";
  cachedBrands
    .filter((b) => (b.status || "active") === "active")
    .forEach((b) => {
      const opt = document.createElement("option");
      opt.value = b.id;
      opt.textContent = `${b.name} (${b.category})`;
      select.appendChild(opt);
    });
}

$("storesNewBtn").addEventListener("click", () => {
  if (!cachedBrands.length) {
    alert("Add at least one brand before opening a store.");
    return;
  }
  isEditingExistingStore = false;
  storeState = emptyStore();
  storeEditorTitle.textContent = "Open new store";
  storeDeleteBtn.classList.add("hidden");
  autogenInfo.textContent =
    "On save, the system will:\n" +
    "  ✓ Generate a fresh store_id like " + cachedBrands[0].id.toUpperCase() + "-####\n" +
    "  ✓ Create a Phone vendor account (placeholder values)\n" +
    "  ✓ Create an Internet vendor account (placeholder values)";
  showStoreEditor();
});

function openStoreEditor(record) {
  isEditingExistingStore = true;
  // Clone so edits don't mutate the cached list.
  storeState = JSON.parse(JSON.stringify(record));
  storeEditorTitle.textContent = `Edit store ${record.store_id}`;
  storeDeleteBtn.classList.remove("hidden");
  storeDeleteBtn.textContent = (record.status === "closed")
    ? "Hard delete (irreversible)"
    : "Close store (soft delete)";
  autogenInfo.textContent = "";
  showStoreEditor();
}

function showStoreEditor() {
  clearStatus(storeEditorStatus);
  setStoreMode("visual");
  syncStateToVisual();
  syncStateToJson();
  storeEditor.classList.remove("hidden");
  storeEditor.scrollIntoView({ behavior: "smooth", block: "start" });
}

$("storeEditorCloseBtn").addEventListener("click", closeStoreEditor);
$("storeCancelBtn").addEventListener("click", closeStoreEditor);
function closeStoreEditor() {
  storeEditor.classList.add("hidden");
  storeState = null;
}


/* ---------- Mode toggle ---------- */

function setStoreMode(mode) {
  storeMode = mode;
  $$(".mode-toggle__btn").forEach((b) => b.classList.toggle("is-active", b.dataset.mode === mode));
  $("storeVisual").classList.toggle("is-active", mode === "visual");
  $("storeJson").classList.toggle("is-active",   mode === "json");
}

$$(".mode-toggle__btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (storeMode === btn.dataset.mode) return;
    if (storeMode === "visual") syncVisualToState();
    else                        syncJsonToState();
    setStoreMode(btn.dataset.mode);
    if (btn.dataset.mode === "visual") syncStateToVisual();
    else                               syncStateToJson();
  });
});


/* ---------- State <-> visual fields sync ---------- */

function syncStateToVisual() {
  if (!storeState) return;
  $("sf_brand").value     = storeState.brand_id || "";
  $("sf_status").value    = storeState.status   || "active";
  $("sf_street").value    = storeState.address?.street  || "";
  $("sf_city").value      = storeState.address?.city    || "";
  $("sf_state").value     = storeState.address?.state   || "";
  $("sf_zip").value       = storeState.address?.zipcode || "";
  $("sf_phone").value     = storeState.phone     || "";
  $("sf_opened").value    = storeState.opened_on || "";
  $("sf_mgr_name").value  = storeState.manager?.full_name || "";
  $("sf_mgr_phone").value = storeState.manager?.phone     || "";
  $("sf_mgr_email").value = storeState.manager?.email     || "";
}

function syncVisualToState() {
  if (!storeState) return;
  storeState.brand_id  = $("sf_brand").value;
  storeState.status    = $("sf_status").value;
  storeState.address   = {
    street:  $("sf_street").value.trim(),
    city:    $("sf_city").value.trim(),
    state:   $("sf_state").value.trim().toUpperCase(),
    zipcode: $("sf_zip").value.trim(),
  };
  storeState.phone     = $("sf_phone").value.trim();
  storeState.opened_on = $("sf_opened").value || null;
  storeState.manager   = {
    full_name: $("sf_mgr_name").value.trim(),
    phone:     $("sf_mgr_phone").value.trim(),
    email:     $("sf_mgr_email").value.trim(),
  };
}


/* ---------- State <-> JSON sync ---------- */

function syncStateToJson() {
  storeJsonEl.value = JSON.stringify(storeState, null, 2);
}

function syncJsonToState() {
  try {
    storeState = JSON.parse(storeJsonEl.value);
    return true;
  } catch (e) {
    setStatus(storeEditorStatus, "Invalid JSON: " + e.message, false);
    return false;
  }
}


/* ---------- Save ---------- */

$("storeSaveBtn").addEventListener("click", async () => {
  if (storeMode === "visual") syncVisualToState();
  else if (!syncJsonToState()) return;

  // Cheap front-end validation — the backend re-validates anyway.
  if (!storeState.brand_id) {
    setStatus(storeEditorStatus, "Brand is required.", false);
    return;
  }

  let ok, data;
  if (isEditingExistingStore) {
    const id = storeState.store_id;
    ({ ok, data } = await api("PATCH", `/api/admin/stores/${encodeURIComponent(id)}`, {
      patch: storeState,
    }));
  } else {
    ({ ok, data } = await api("POST", "/api/admin/stores", storeState));
  }

  if (!ok) {
    setStatus(storeEditorStatus, data.error || "Save failed.", false);
    return;
  }
  setStatus(storeEditorStatus,
    isEditingExistingStore
      ? `Saved. Store ${storeState.store_id} updated and index rebuilt.`
      : `Created ${data.record?.store_id}. Phone + internet accounts auto-created. Index rebuilt.`,
    true);
  await loadStores();
  if (!isEditingExistingStore) {
    closeStoreEditor();
  } else {
    storeState = data.record;     // adopt server-canonical version
    syncStateToVisual();
    syncStateToJson();
  }
});


/* ---------- Delete (soft / hard) ---------- */

storeDeleteBtn.addEventListener("click", async () => {
  if (!storeState?.store_id) return;
  const id = storeState.store_id;

  const isAlreadyClosed = storeState.status === "closed";

  if (!isAlreadyClosed) {
    if (!confirm(`Close ${id}? It stays in records (auditable, reopenable). The chatbot will hide it from default queries.`)) return;
    const closedOn = new Date().toISOString().slice(0, 10);
    const { ok, data } = await api("DELETE",
      `/api/admin/stores/${encodeURIComponent(id)}?closed_on=${closedOn}`);
    if (!ok) { setStatus(storeEditorStatus, data.error || "Failed.", false); return; }
    setStatus(storeEditorStatus, `Closed ${id}.`, true);
  } else {
    const typed = prompt(`Hard delete is irreversible. Type ${id} to confirm:`);
    if (typed !== id) {
      setStatus(storeEditorStatus, "Confirmation didn't match. Nothing deleted.", false);
      return;
    }
    const { ok, data } = await api("DELETE",
      `/api/admin/stores/${encodeURIComponent(id)}?hard=true&confirm=${encodeURIComponent(id)}`);
    if (!ok) { setStatus(storeEditorStatus, data.error || "Failed.", false); return; }
    setStatus(storeEditorStatus, `Hard-deleted ${id}.`, true);
  }
  await loadStores();
  closeStoreEditor();
});


/* ================================================================ */
/* GENERIC JSON EDITOR (vendors / brands / employees / departments) */
/* ================================================================ */

const TEMPLATES = {
  vendors: {
    vendor_account_id: "PHONE-NEW_STORE_ID",
    store_id: "NEW_STORE_ID",
    service: "Phone",
    provider: "TBD",
    account_number: "TBD",
    monthly_cost: 0,
    support_phone: "",
    portal_url: "",
    login: { username: "", password: "" },
  },
  brands: {
    id: "new_brand",
    name: "New Brand",
    category: "Category",
    status: "active",
  },
  employees: {
    id: "EMP-DP-001",
    full_name: "First Last",
    first_name: "First",
    last_name: "Last",
    email: "first.last@tostadogroup.com",
    phone: "",
    title: "Job Title",
    department: "IT",
  },
  departments: {
    name: "New Department",
    description: "",
    head: { id: "", name: "", email: "", phone: "" },
    admin_contact: { id: "", name: "", email: "", phone: "" },
    team_member_ids: [],
  },
};

const RECORD_LABEL = {
  vendors:     (r) => `${r.vendor_account_id} — ${r.service} · ${r.provider}`,
  brands:      (r) => `${r.id} — ${r.name} (${r.category})`,
  employees:   (r) => `${r.id} — ${r.full_name} · ${r.department || ""}`,
  departments: (r) => `${r.name}`,
};

const RECORD_STATUS = {
  brands: (r) => r.status || "active",
  vendors: () => "active",
  employees: () => "active",
  departments: () => "active",
};

const cache = {};   // dataset name -> { records: [...], filter: '' }


function dom(dataset, action) {
  return document.querySelector(`.json-tab[data-dataset="${dataset}"] [data-action="${action}"]`);
}

function editorPane(dataset) {
  return document.querySelector(`.json-tab[data-dataset="${dataset}"] .json-editor`);
}

async function loadJsonDataset(dataset) {
  const list = dom(dataset, "list");
  const { ok, data } = await api("GET", `/api/admin/${dataset}`);
  if (!ok) {
    list.innerHTML = `<div class="record-row"><em>${data.error || "Failed to load."}</em></div>`;
    return;
  }
  cache[dataset] = { records: data.records || [], filter: cache[dataset]?.filter || "" };
  renderJsonList(dataset);
}

function renderJsonList(dataset) {
  const list = dom(dataset, "list");
  const { records, filter } = cache[dataset];
  const q = filter.toLowerCase();
  const filtered = records.filter((r) => {
    if (!q) return true;
    return RECORD_LABEL[dataset](r).toLowerCase().includes(q);
  });

  list.innerHTML = "";
  filtered.slice(0, 200).forEach((r) => {
    const row = document.createElement("div");
    row.className = "record-row";
    const status = RECORD_STATUS[dataset](r);
    row.innerHTML = `
      <div>
        <span class="record-row__id">${escapeHtml(RECORD_LABEL[dataset](r))}</span>
        ${dataset === "brands" ? `<span class="record-row__badge record-row__badge--${badgeClassForStatus(status)}">${status}</span>` : ""}
      </div>
    `;
    row.addEventListener("click", () => openJsonEditor(dataset, r, false));
    list.appendChild(row);
  });
  if (filtered.length > 200) {
    const note = document.createElement("div");
    note.className = "record-row";
    note.innerHTML = `<em style="color:var(--ink-soft);font-size:12px;">Showing 200 of ${filtered.length}.</em>`;
    list.appendChild(note);
  }
}

/* Wire each JSON tab's controls */
$$(".json-tab").forEach((tab) => {
  const dataset = tab.dataset.dataset;
  cache[dataset] = { records: [], filter: "" };

  tab.querySelector('[data-action="refresh"]')
     .addEventListener("click", () => loadJsonDataset(dataset));

  tab.querySelector('[data-action="filter"]')
     .addEventListener("input", (e) => {
       cache[dataset].filter = e.target.value;
       renderJsonList(dataset);
     });

  tab.querySelector('[data-action="new"]')
     .addEventListener("click", () => openJsonEditor(dataset, TEMPLATES[dataset], true));

  tab.querySelector('[data-action="cancel"]')
     .addEventListener("click", () => editorPane(dataset).classList.add("hidden"));

  tab.querySelector('[data-action="save"]')
     .addEventListener("click", () => saveJsonRecord(dataset));

  tab.querySelector('[data-action="delete"]')
     .addEventListener("click", () => deleteJsonRecord(dataset));
});

let editorContext = {};        // { dataset, isNew, originalId }

function openJsonEditor(dataset, record, isNew) {
  editorContext = { dataset, isNew, originalId: isNew ? null : record[primaryKeyOf(dataset)] };

  const pane     = editorPane(dataset);
  const titleEl  = dom(dataset, "title");
  const jsonEl   = dom(dataset, "json");
  const deleteBt = dom(dataset, "delete");
  const statusEl = dom(dataset, "status");

  titleEl.textContent = isNew
    ? `New ${dataset.slice(0, -1)}`
    : `Edit ${dataset.slice(0, -1)} — ${RECORD_LABEL[dataset](record)}`;

  jsonEl.value = JSON.stringify(record, null, 2);
  deleteBt.classList.toggle("hidden", isNew);
  if (!isNew && dataset === "brands") {
    deleteBt.textContent = "Close brand (soft delete)";
  } else if (!isNew) {
    deleteBt.textContent = "Hard delete (irreversible)";
  }
  clearStatus(statusEl);
  pane.classList.remove("hidden");
  pane.scrollIntoView({ behavior: "smooth", block: "start" });
}

function primaryKeyOf(dataset) {
  return ({
    vendors:     "vendor_account_id",
    brands:      "id",
    employees:   "id",
    departments: "name",
  })[dataset];
}

async function saveJsonRecord(dataset) {
  const { isNew, originalId } = editorContext;
  const statusEl = dom(dataset, "status");

  let payload;
  try {
    payload = JSON.parse(dom(dataset, "json").value);
  } catch (e) {
    setStatus(statusEl, "Invalid JSON: " + e.message, false);
    return;
  }

  let ok, data;
  if (isNew) {
    ({ ok, data } = await api("POST", `/api/admin/${dataset}`, payload));
  } else {
    ({ ok, data } = await api("PATCH",
      `/api/admin/${dataset}/${encodeURIComponent(originalId)}`,
      { patch: payload }));
  }

  if (!ok) { setStatus(statusEl, data.error || "Save failed.", false); return; }
  setStatus(statusEl, isNew ? "Created and index rebuilt." : "Updated and index rebuilt.", true);
  await loadJsonDataset(dataset);
}

async function deleteJsonRecord(dataset) {
  const { originalId } = editorContext;
  if (!originalId) return;
  const statusEl = dom(dataset, "status");

  if (dataset === "brands") {
    if (!confirm(`Close brand "${originalId}"? Brands with active stores cannot be closed.`)) return;
    const { ok, data } = await api("DELETE", `/api/admin/brands/${encodeURIComponent(originalId)}`);
    if (!ok) { setStatus(statusEl, data.error || "Failed.", false); return; }
    setStatus(statusEl, `Closed brand ${originalId}.`, true);
  } else {
    const typed = prompt(`Hard delete is irreversible. Type ${originalId} to confirm:`);
    if (typed !== originalId) {
      setStatus(statusEl, "Confirmation didn't match.", false);
      return;
    }
    const { ok, data } = await api("DELETE",
      `/api/admin/${dataset}/${encodeURIComponent(originalId)}?hard=true&confirm=${encodeURIComponent(originalId)}`);
    if (!ok) { setStatus(statusEl, data.error || "Failed.", false); return; }
    setStatus(statusEl, `Hard-deleted ${originalId}.`, true);
  }
  await loadJsonDataset(dataset);
}


/* ---------------------------------------------------------------- */
/* Tiny utility                                                     */
/* ---------------------------------------------------------------- */

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
