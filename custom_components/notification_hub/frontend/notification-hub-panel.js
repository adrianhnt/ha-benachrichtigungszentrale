// Benachrichtigungszentrale – Seite „Benachrichtigungen“
// Einfache Web-Komponente ohne Build-Schritt; spricht über WebSocket mit der Integration.

const DOMAIN = "notification_hub";
const PRIO = {
  passive: "Leise",
  active: "Standard",
  "time-sensitive": "Zeitkritisch",
  critical: "Kritisch",
};

const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const hlVars = (t) => esc(t).replace(/\{\{\s*([\w.]+)\s*\}\}/g, "<code>{{ $1 }}</code>");
const varsIn = (...texts) => {
  const out = new Set();
  for (const t of texts) for (const m of String(t || "").matchAll(/\{\{\s*([A-Za-z_]\w*)/g)) out.add(m[1]);
  return [...out];
};
const slugOk = (s) => /^[a-z0-9_]+$/.test(s);

const STYLE = `
  :host { display:block; min-height:100vh; background:var(--primary-background-color,#fafafa); color:var(--primary-text-color,#212121);
    font-family:var(--paper-font-body1_-_font-family, Roboto, sans-serif); font-size:14px; }
  * { box-sizing:border-box; }
  .top { position:sticky; top:0; z-index:2; background:var(--app-header-background-color, var(--primary-color, #03a9f4)); color:var(--app-header-text-color,#fff); }
  .bar { height:56px; display:flex; align-items:center; gap:8px; padding:0 12px; }
  .bar h1 { flex:1; margin:0 0 0 4px; font-size:20px; font-weight:400; }
  .menu { background:none; border:0; color:inherit; font-size:22px; cursor:pointer; padding:8px; }
  .dnd { font-size:12px; background:rgba(255,255,255,.2); padding:3px 10px; border-radius:12px; }
  .tabs { display:flex; padding:0 8px; overflow-x:auto; }
  .tab { padding:12px 16px; cursor:pointer; opacity:.75; border-bottom:2px solid transparent; white-space:nowrap; }
  .tab.active { opacity:1; border-color:currentColor; }
  .content { padding:16px; max-width:1500px; margin:0 auto; }
  .toolbar { display:flex; gap:8px; align-items:center; margin-bottom:12px; flex-wrap:wrap; }
  input, select, textarea { font:inherit; color:var(--primary-text-color); background:var(--card-background-color,#fff);
    border:1px solid var(--divider-color,#e0e0e0); border-radius:8px; padding:8px 10px; width:100%; }
  textarea { resize:vertical; }
  .search { flex:1; min-width:180px; width:auto; }
  .toolbar select { width:auto; }
  .btn { border:0; border-radius:18px; padding:8px 16px; font:inherit; font-weight:500; cursor:pointer; background:var(--primary-color,#03a9f4); color:var(--text-primary-color,#fff); white-space:nowrap; }
  .btn.flat { background:transparent; color:var(--primary-color,#03a9f4); }
  .btn.danger { background:transparent; color:var(--error-color,#db4437); }
  .btn:disabled { opacity:.5; cursor:default; }
  .card { background:var(--card-background-color,#fff); border-radius:var(--ha-card-border-radius,12px); border:1px solid var(--divider-color,#e0e0e0); overflow:auto; }
  table { width:100%; border-collapse:collapse; }
  th { text-align:left; font-weight:500; color:var(--secondary-text-color); font-size:12px; padding:10px 12px; border-bottom:1px solid var(--divider-color,#e0e0e0); white-space:nowrap; }
  th[data-sort] { cursor:pointer; user-select:none; }
  td { padding:10px 12px; border-bottom:1px solid var(--divider-color,#e0e0e0); vertical-align:top; }
  tbody tr:last-child td { border-bottom:0; }
  tbody tr:hover { background:var(--secondary-background-color,rgba(0,0,0,.03)); }
  code { font-family:var(--code-font-family, ui-monospace, Menlo, monospace); font-size:12.5px; }
  .muted { color:var(--secondary-text-color); font-size:12.5px; }
  .chip { display:inline-block; padding:2px 8px; border-radius:10px; background:rgba(var(--rgb-primary-color,3,169,244),.12); color:var(--primary-color); font-size:12px; margin:1px 3px 1px 0; white-space:nowrap; }
  .prio { display:inline-flex; align-items:center; gap:6px; white-space:nowrap; }
  .dot { width:8px; height:8px; border-radius:50%; background:var(--secondary-text-color); }
  .dot.active { background:var(--primary-color); } .dot.time-sensitive { background:var(--warning-color,#ff9800); } .dot.critical { background:var(--error-color,#db4437); }
  .msg { min-width:220px; max-width:340px; }
  .note { min-width:160px; max-width:260px; font-size:12.5px; color:var(--secondary-text-color); font-style:italic; }
  .unused { color:var(--error-color,#db4437); font-size:12.5px; }
  .link { color:var(--primary-color); cursor:pointer; text-decoration:none; display:block; }
  .link.off { color:var(--secondary-text-color); }
  .acts { white-space:nowrap; text-align:right; position:sticky; right:0; background:var(--card-background-color,#fff); box-shadow:-6px 0 6px -6px rgba(0,0,0,.25); }
  th.actsh { position:sticky; right:0; background:var(--card-background-color,#fff); }
  .ib { border:0; background:transparent; cursor:pointer; font-size:16px; padding:4px 6px; border-radius:6px; }
  .ib:hover { background:var(--divider-color,#e0e0e0); }
  .switch { position:relative; width:34px; height:18px; display:inline-block; }
  .switch input { display:none; }
  .switch span { position:absolute; inset:0; background:var(--divider-color,#ccc); border-radius:9px; cursor:pointer; transition:.15s; }
  .switch span::after { content:""; position:absolute; width:14px; height:14px; top:2px; left:2px; border-radius:50%; background:#fff; transition:.15s; }
  .switch input:checked + span { background:var(--primary-color); }
  .switch input:checked + span::after { left:18px; }
  .info { margin-top:12px; font-size:12.5px; color:var(--secondary-text-color); }
  .error { color:var(--error-color,#db4437); padding:16px; }
  dialog { border:0; border-radius:16px; padding:0; width:min(680px,95vw); background:var(--card-background-color,#fff); color:var(--primary-text-color); box-shadow:0 10px 40px rgba(0,0,0,.35); }
  dialog::backdrop { background:rgba(0,0,0,.4); }
  .dh { padding:18px 20px 6px; font-size:20px; }
  .db { padding:8px 20px; display:grid; grid-template-columns:1fr 1fr; gap:12px 14px; max-height:70vh; overflow:auto; }
  .db label { display:flex; flex-direction:column; gap:4px; font-size:12px; color:var(--secondary-text-color); }
  .db .full { grid-column:1 / -1; }
  .hint { font-size:11.5px; color:var(--secondary-text-color); }
  .derr { grid-column:1 / -1; color:var(--error-color,#db4437); font-size:13px; }
  .pick { display:flex; flex-wrap:wrap; gap:6px; }
  .pick label { flex-direction:row; align-items:center; gap:6px; font-size:13px; color:var(--primary-text-color); border:1px solid var(--divider-color,#e0e0e0); border-radius:16px; padding:4px 10px; cursor:pointer; }
  .pick input { width:auto; }
  .sub { font-size:12px; color:var(--secondary-text-color); margin-bottom:4px; }
  .step { border:1px solid var(--divider-color,#e0e0e0); border-radius:10px; padding:10px 12px; margin-bottom:10px; display:flex; flex-direction:column; }
  .stephead { display:flex; align-items:center; justify-content:space-between; margin-bottom:6px; font-size:13px; }
  .stepbtns .ib[disabled] { opacity:.3; cursor:default; }
  .step details { margin-top:8px; font-size:12px; }
  .df { display:flex; justify-content:flex-end; gap:8px; padding:12px 20px 18px; }
  .df .left { margin-right:auto; }
  details summary { cursor:pointer; font-size:12px; color:var(--secondary-text-color); }
  @media (max-width:700px) { .db { grid-template-columns:1fr; } .content { padding:8px; } }
`;

class NotificationHubPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "notifications";
    this._query = "";
    this._cat = "";
    this._sort = { col: "category", dir: 1 };
    this._data = null;
    this._error = null;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (this._menuBtn) this._menuBtn.hass = hass;
    if (first) {
      this._build();
      this._load();
    }
  }
  get hass() { return this._hass; }
  set narrow(v) { this._narrow = v; if (this._menuBtn) this._menuBtn.narrow = v; }
  set panel(v) { this._panel = v; }

  // ------------------------------------------------------------------ Aufbau

  _build() {
    const root = this.shadowRoot;
    root.innerHTML = `<style>${STYLE}</style>
      <div class="top">
        <div class="bar"><span id="menu"></span><h1>Benachrichtigungen</h1><span id="dnd"></span>
          <button class="menu" title="Aktualisieren" data-act="reload">⟳</button></div>
        <div class="tabs">
          <div class="tab" data-tab="notifications">Benachrichtigungen</div>
          <div class="tab" data-tab="buttons">Knöpfe</div>
          <div class="tab" data-tab="categories">Kategorien</div>
          <div class="tab" data-tab="devices">Geräte</div>
        </div>
      </div>
      <div class="content" id="content"><div class="muted">Lade …</div></div>
      <dialog id="dlg"></dialog>
      <datalist id="dl-services"></datalist>
      <datalist id="dl-entities"></datalist>`;

    const menu = root.getElementById("menu");
    if (customElements.get("ha-menu-button")) {
      this._menuBtn = document.createElement("ha-menu-button");
      this._menuBtn.hass = this._hass;
      this._menuBtn.narrow = this._narrow;
      menu.appendChild(this._menuBtn);
    } else {
      menu.innerHTML = `<button class="menu" data-act="menu">☰</button>`;
    }

    root.addEventListener("click", (e) => this._onClick(e));
    root.addEventListener("input", (e) => {
      if (e.target.id === "q") {
        this._query = e.target.value;
        const pos = e.target.selectionStart;
        this._render();
        const q = this.shadowRoot.getElementById("q");
        q.focus();
        q.setSelectionRange(pos, pos);
      }
    });
    root.addEventListener("change", (e) => {
      if (e.target.id === "catf") { this._cat = e.target.value; this._render(); }
      if (e.target.dataset.mute) this._toggleMute(e.target.dataset.mute, e.target.checked);
      if (e.target.dataset.vol) this._setVolume(e.target.dataset.vol, Number(e.target.value));
    });
    root.addEventListener("input", (e) => {
      if (e.target.dataset.vol) {
        const out = e.target.parentElement.querySelector("output");
        if (out) out.textContent = `${e.target.value} %`;
      }
    });
  }

  async _load(retries = 6) {
    try {
      this._data = await this._hass.callWS({ type: `${DOMAIN}/data` });
      this._error = null;
    } catch (err) {
      if (retries > 0) {
        await new Promise((r) => setTimeout(r, 700));
        return this._load(retries - 1);
      }
      this._error = err.message || String(err);
    }
    this._render();
  }

  _toast(message) {
    this.dispatchEvent(new CustomEvent("hass-notification", { detail: { message }, bubbles: true, composed: true }));
  }

  _navigate(path) {
    history.pushState(null, "", path);
    window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
  }

  // ------------------------------------------------------------------ Hilfen

  get _cats() { return this._data?.categories || []; }
  get _buttons() { return this._data?.buttons || []; }
  get _notifs() { return this._data?.notifications || []; }
  _catTitle(key) { return this._cats.find((c) => c.key === key)?.title ?? key; }
  _button(key) { return this._buttons.find((b) => b.key === key); }
  _personName(id) { return this._data.persons.find((p) => p.entity_id === id)?.name ?? id; }
  _deviceName(id) { return this._data.targets.find((t) => t.device_id === id)?.name ?? "unbekanntes Gerät"; }
  _entityName(id) { return this._hass.states[id]?.attributes?.friendly_name ?? id; }

  _refs(list) {
    if (!list?.length) return "";
    return list
      .map((r) => `<a class="link ${r.enabled ? "" : "off"}" data-nav="${esc(r.url || "")}" title="${esc(r.entity_id)}${r.enabled ? "" : " (deaktiviert)"}">${r.kind === "script" ? "📜 " : ""}${esc(r.name)}${r.enabled ? "" : " (aus)"}</a>`)
      .join("");
  }

  _matches(obj) {
    if (!this._query) return true;
    return JSON.stringify(obj).toLowerCase().includes(this._query.toLowerCase());
  }

  // ------------------------------------------------------------------ Darstellung

  _render() {
    const root = this.shadowRoot;
    root.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === this._tab));
    const content = root.getElementById("content");
    if (this._error) {
      content.innerHTML = `<div class="error">Fehler: ${esc(this._error)}</div>`;
      return;
    }
    if (!this._data) return;
    root.getElementById("dnd").innerHTML = this._data.do_not_disturb ? `<span class="dnd">Nicht stören aktiv</span>` : "";
    if (this._tab === "notifications") content.innerHTML = this._renderNotifications();
    if (this._tab === "buttons") content.innerHTML = this._renderButtons();
    if (this._tab === "categories") content.innerHTML = this._renderCategories();
    if (this._tab === "devices") content.innerHTML = this._renderDevices();
  }

  _renderNotifications() {
    const usage = this._data.usage.notifications;
    const val = (n, col) => {
      if (col === "category") return (this._catTitle(n.category) + " " + n.id).toLowerCase();
      if (col === "priority") return this._data.priorities.indexOf(n.priority);
      if (col === "usage") return (usage[n.id] || []).length;
      return String(n[col] ?? "").toLowerCase();
    };
    const rows = this._notifs
      .filter((n) => (!this._cat || n.category === this._cat) && this._matches(n))
      .sort((a, b) => (val(a, this._sort.col) > val(b, this._sort.col) ? 1 : -1) * this._sort.dir);
    const th = (col, label) =>
      `<th data-sort="${col}">${label}${this._sort.col === col ? (this._sort.dir > 0 ? " ▲" : " ▼") : ""}</th>`;
    const dynamic = this._data.usage.dynamic;
    return `
      <div class="toolbar">
        <input class="search" id="q" placeholder="🔍 Suchen …" value="${esc(this._query)}">
        <select id="catf"><option value="">Alle Kategorien</option>${this._cats
          .map((c) => `<option value="${esc(c.key)}" ${c.key === this._cat ? "selected" : ""}>${esc(c.title)}</option>`)
          .join("")}</select>
        <button class="btn" data-act="new-notification" ${this._cats.length ? "" : "disabled"}>＋ Benachrichtigung</button>
      </div>
      ${this._cats.length ? "" : `<div class="info">Lege zuerst unter „Kategorien“ eine Kategorie an.</div>`}
      <div class="card"><table>
        <thead><tr>${th("id", "ID")}${th("category", "Kategorie")}${th("title", "Titel")}<th>Text</th>${th("priority", "Dringlichkeit")}<th>Empfänger</th><th>Knöpfe</th>${th("usage", "Verwendet in")}<th>Notiz</th><th class="actsh"></th></tr></thead>
        <tbody>${rows
          .map((n) => {
            const recips = [...n.persons.map((p) => "👤 " + this._personName(p)), ...n.devices.map((d) => "📱 " + this._deviceName(d))];
            return `<tr>
              <td><code>${esc(n.id)}</code></td>
              <td>${esc(this._catTitle(n.category))}</td>
              <td>${n.title ? hlVars(n.title) : `<span class="muted">${esc(this._catTitle(n.category))}</span>`}</td>
              <td class="msg">${hlVars(n.message)}</td>
              <td><span class="prio"><span class="dot ${esc(n.priority)}"></span>${PRIO[n.priority] || esc(n.priority)}</span></td>
              <td>${recips.length ? recips.map((r) => `<span class="chip">${esc(r)}</span>`).join("") : `<span class="muted">alle</span>`}</td>
              <td>${n.actions.map((k) => `<span class="chip">🔘 ${esc(this._button(k)?.button_title ?? k)}</span>`).join("") || `<span class="muted">–</span>`}</td>
              <td>${this._refs(usage[n.id]) || `<span class="unused">nirgends</span>`}</td>
              <td class="note">${esc(n.note)}</td>
              <td class="acts">
                <button class="ib" title="Aufruf für Automation kopieren" data-act="copy" data-id="${esc(n.id)}">📋</button>
                <button class="ib" title="Test senden" data-act="test" data-id="${esc(n.id)}">▶️</button>
                <button class="ib" title="Bearbeiten" data-act="edit-notification" data-id="${esc(n.id)}">✏️</button>
              </td></tr>`;
          })
          .join("") || `<tr><td colspan="10" class="muted">Keine Benachrichtigungen${this._query || this._cat ? " für diese Suche" : ""}.</td></tr>`}
        </tbody></table></div>
      ${dynamic.length ? `<div class="info">Mit berechneter ID (nicht zuordenbar): ${this._refs(dynamic).replace(/<a /g, "<a style='display:inline;margin-right:8px' ")}</div>` : ""}
      <div class="info">In einer Automation: <code>action: notification_hub.send</code> · <code>data: { id: … }</code> – Personen/Geräte im Aufruf ersetzen die Standard-Empfänger. 📋 kopiert den fertigen Aufruf.</div>`;
  }

  _renderButtons() {
    const direct = this._data.usage.buttons;
    const rows = this._buttons.filter((b) => this._matches(b));
    return `
      <div class="toolbar">
        <input class="search" id="q" placeholder="🔍 Suchen …" value="${esc(this._query)}">
        <button class="btn" data-act="new-button">＋ Knopf</button>
      </div>
      <div class="card"><table>
        <thead><tr><th>Kennung</th><th>Knopftext</th><th>Symbol</th><th>Beim Tippen</th><th>Gültigkeit</th><th>Face ID</th><th>Rot</th><th>Verwendet in</th><th class="actsh"></th></tr></thead>
        <tbody>${rows
          .map((b) => {
            const inNotifs = this._notifs.filter((n) => n.actions.includes(b.key)).map((n) => `<span class="chip">${esc(n.id)}</span>`).join("");
            const used = inNotifs + this._refs(direct[b.key]);
            return `<tr>
              <td><code>${esc(b.key)}</code></td>
              <td>${esc(b.button_title)}</td>
              <td>${b.icon ? `<code>${esc(b.icon)}</code>` : `<span class="muted">–</span>`}</td>
              <td>${(b.steps || []).map((st, i) => `<div${i ? ' style="margin-top:4px"' : ""}>${b.steps.length > 1 ? `<span class="muted">${i + 1}.</span> ` : ""}<code>${esc(st.service)}</code>${(st.target_entities || []).length ? `<span class="muted"> → ${st.target_entities.map((e) => esc(this._entityName(e))).join(", ")}</span>` : ""}</div>`).join("") || `<span class="muted">–</span>`}</td>
              <td>${b.expiry_minutes ? esc(b.expiry_minutes) + " min" : "unbegrenzt"}</td>
              <td>${b.authentication_required ? "✓" : ""}</td>
              <td>${b.destructive ? "✓" : ""}</td>
              <td>${used || `<span class="unused">nirgends</span>`}</td>
              <td class="acts"><button class="ib" title="Bearbeiten" data-act="edit-button" data-id="${esc(b.subentry_id)}">✏️</button></td>
            </tr>`;
          })
          .join("") || `<tr><td colspan="9" class="muted">Keine Knöpfe.</td></tr>`}
        </tbody></table></div>
      <div class="info">Symbole sind Apple-SF-Symbols (Namen z. B. aus der App „SF Symbols“). Eine Vorschau gibt es nur auf dem iPhone.</div>`;
  }

  _renderCategories() {
    const direct = this._data.usage.categories;
    return `
      <div class="toolbar">
        <div class="muted" style="flex:1">Kategorien ordnen Benachrichtigungen, stapeln sie auf dem iPhone und lassen sich gemeinsam stummschalten – kritische kommen immer durch.</div>
        <button class="btn" data-act="new-category">＋ Kategorie</button>
      </div>
      <div class="card"><table>
        <thead><tr><th>Kennung</th><th>Name</th><th>Gruppierung</th><th>Benachrichtigungen</th><th>Direkt verwendet in</th><th>Stumm</th><th class="actsh"></th></tr></thead>
        <tbody>${this._cats
          .map((c) => {
            const count = this._notifs.filter((n) => n.category === c.key).length;
            return `<tr>
              <td><code>${esc(c.key)}</code></td>
              <td>${esc(c.title)}</td>
              <td>${c.group ? esc(c.group) : `<span class="muted">${esc(c.key)}</span>`}</td>
              <td>${count}</td>
              <td>${this._refs(direct[c.key]) || `<span class="muted">–</span>`}</td>
              <td>${c.mute_entity_id ? `<label class="switch"><input type="checkbox" data-mute="${esc(c.mute_entity_id)}" ${c.muted ? "checked" : ""}><span></span></label>` : ""}</td>
              <td class="acts"><button class="ib" title="Bearbeiten" data-act="edit-category" data-id="${esc(c.subentry_id)}">✏️</button></td>
            </tr>`;
          })
          .join("") || `<tr><td colspan="7" class="muted">Keine Kategorien.</td></tr>`}
        </tbody></table></div>
      <div class="info">„Direkt verwendet in“: Automationen, die noch die bisherige Variante (Typ + Text im Aufruf) nutzen.</div>`;
  }

  _renderDevices() {
    const targets = this._data.targets || [];
    return `
      <div class="toolbar">
        <div class="muted" style="flex:1">Lautstärke, mit der kritische Benachrichtigungen auf dem jeweiligen Gerät klingeln – auch bei Lautlos und „Nicht stören“. 0 % = stumm, wird aber angezeigt.</div>
      </div>
      <div class="card"><table>
        <thead><tr><th>Gerät</th><th>Kritische Lautstärke</th><th>Entität</th></tr></thead>
        <tbody>${targets
          .map((t) => `<tr>
              <td>${esc(t.name)}</td>
              <td>${t.volume_entity_id
                ? `<span style="display:inline-flex;align-items:center;gap:10px"><input type="range" min="0" max="100" step="5" value="${Number(t.critical_volume)}" data-vol="${esc(t.volume_entity_id)}" style="width:180px"><output>${Math.round(t.critical_volume)} %</output></span>`
                : `<span class="muted">${Math.round(t.critical_volume)} % (Regler erscheint nach dem Neuladen der Integration)</span>`}</td>
              <td>${t.volume_entity_id ? `<code>${esc(t.volume_entity_id)}</code>` : `<span class="muted">–</span>`}</td>
            </tr>`)
          .join("") || `<tr><td colspan="3" class="muted">Keine Geräte mit der Home-Assistant-App gefunden.</td></tr>`}
        </tbody></table></div>
      <div class="info">Die Regler sind normale Entitäten – die Lautstärke lässt sich also auch per Automation ändern (z. B. nachts leiser).</div>`;
  }

  // ------------------------------------------------------------------ Klicks

  _onClick(e) {
    const tab = e.target.closest("[data-tab]");
    if (tab) { this._tab = tab.dataset.tab; this._query = ""; this._render(); return; }
    const sort = e.target.closest("th[data-sort]");
    if (sort) {
      const col = sort.dataset.sort;
      this._sort = { col, dir: this._sort.col === col ? -this._sort.dir : 1 };
      this._render();
      return;
    }
    const nav = e.target.closest("[data-nav]");
    if (nav && nav.dataset.nav) { e.preventDefault(); this._navigate(nav.dataset.nav); return; }
    const el = e.target.closest("[data-act]");
    if (!el) return;
    const id = el.dataset.id;
    switch (el.dataset.act) {
      case "menu": this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true })); break;
      case "reload": this._load(); break;
      case "new-notification": this._notificationDialog(null); break;
      case "edit-notification": this._notificationDialog(this._notifs.find((n) => n.id === id)); break;
      case "test": this._test(id); break;
      case "copy": this._copy(id); break;
      case "new-button": this._buttonDialog(null); break;
      case "edit-button": this._buttonDialog(this._buttons.find((b) => b.subentry_id === id)); break;
      case "new-category": this._categoryDialog(null); break;
      case "edit-category": this._categoryDialog(this._cats.find((c) => c.subentry_id === id)); break;
    }
  }

  async _toggleMute(entityId, on) {
    try {
      await this._hass.callService("switch", on ? "turn_on" : "turn_off", { entity_id: entityId });
    } catch (err) {
      this._toast(`Fehler: ${err.message || err}`);
    }
  }

  async _setVolume(entityId, value) {
    try {
      await this._hass.callService("number", "set_value", { entity_id: entityId, value });
      const t = (this._data.targets || []).find((x) => x.volume_entity_id === entityId);
      if (t) t.critical_volume = value;
    } catch (err) {
      this._toast(`Fehler: ${err.message || err}`);
    }
  }

  async _test(id) {
    const n = this._notifs.find((x) => x.id === id);
    const hasButtons = n?.actions?.length;
    const msg =
      `Test „${id}“ an die Standard-Empfänger senden?` +
      (hasButtons ? "\n\nDie Knöpfe sind echt: Antippen führt die Aktion wirklich aus." : "") +
      (n?.priority === "critical" ? "\n\nAchtung: Kritisch – klingelt mit Alarmton, auch bei Lautlos und „Nicht stören“." : "") +
      (this._data?.do_not_disturb && n?.priority !== "critical" ? "\n\n„Nicht stören“ ist aktiv – der Test wird deshalb nicht zugestellt." : "");
    if (!confirm(msg)) return;
    try {
      const res = await this._hass.callWS({ type: `${DOMAIN}/notification/test`, notification_id: id });
      this._toast(res.sent ? `Test gesendet an ${res.recipients.join(", ")}` : `Nicht gesendet: ${({ do_not_disturb: "„Nicht stören“ ist aktiv", muted: "Kategorie ist stummgeschaltet" })[res.reason] || res.reason}`);
    } catch (err) {
      this._toast(`Fehler: ${err.message || err}`);
    }
  }

  async _copy(id) {
    const n = this._notifs.find((x) => x.id === id);
    const vars = varsIn(n?.title, n?.message);
    let yaml = `action: notification_hub.send\ndata:\n  id: ${id}\n`;
    if (vars.length) yaml += `  variables:\n${vars.map((v) => `    ${v}: ""`).join("\n")}\n`;
    try {
      await navigator.clipboard.writeText(yaml);
    } catch (_) {
      const ta = document.createElement("textarea");
      ta.value = yaml;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    this._toast("Aufruf kopiert – in der Automation als YAML einfügen");
  }

  // ------------------------------------------------------------------ Dialoge

  _openDialog(html, onSave, onDelete) {
    const d = this.shadowRoot.getElementById("dlg");
    d.innerHTML = html;
    d.showModal();
    const err = d.querySelector(".derr");
    d.querySelectorAll("[data-close]").forEach((b) => (b.onclick = () => d.close()));
    const run = async (fn, btn) => {
      err.textContent = "";
      btn.disabled = true;
      try {
        await fn(d);
        d.close();
      } catch (e) {
        err.textContent = e.message || String(e);
      } finally {
        btn.disabled = false;
      }
    };
    const save = d.querySelector("[data-save]");
    save.onclick = () => run(onSave, save);
    const del = d.querySelector("[data-delete]");
    if (del && onDelete) del.onclick = () => run(onDelete, del);
    return d;
  }

  _notificationDialog(n) {
    const isNew = !n;
    n = n || { id: "", category: this._cat || this._cats[0]?.key, title: "", message: "", priority: "active", persons: [], devices: [], actions: [], url: "", note: "" };
    const used = (this._data.usage.notifications[n.id] || []).length;
    const html = `
      <div class="dh">${isNew ? "Neue Benachrichtigung" : `Benachrichtigung <code>${esc(n.id)}</code>`}</div>
      <div class="db">
        ${isNew ? `<label>ID<input name="id" placeholder="z. B. waesche_fertig" autocomplete="off"><span class="hint">Nur a–z, 0–9 und _. Wird in Automationen verwendet und ist danach fest.</span></label>` : ""}
        <label ${isNew ? "" : 'class="full"'}>Kategorie<select name="category">${this._cats
          .map((c) => `<option value="${esc(c.key)}" ${c.key === n.category ? "selected" : ""}>${esc(c.title)}</option>`)
          .join("")}</select></label>
        <label class="full">Titel<input name="title" value="${esc(n.title)}" placeholder="leer = Name der Kategorie"><span class="hint">Emojis erlaubt, z. B. 🧺 Waschmaschine.</span></label>
        <label class="full">Text<textarea name="message" rows="3">${esc(n.message)}</textarea><span class="hint">Platzhalter wie <code>{{ dauer }}</code> füllt die Automation über <code>variables</code>.</span></label>
        <label>Dringlichkeit<select name="priority">${this._data.priorities
          .map((p) => `<option value="${p}" ${p === n.priority ? "selected" : ""}>${PRIO[p] || p}</option>`)
          .join("")}</select></label>
        <label>Beim Antippen öffnen (optional)<input name="url" value="${esc(n.url)}" placeholder="/lovelace/0"></label>
        <div class="full"><div class="sub">Standard-Empfänger – leer = alle Geräte</div><div class="pick">
          ${this._data.persons.map((p) => `<label><input type="checkbox" name="persons" value="${esc(p.entity_id)}" ${n.persons.includes(p.entity_id) ? "checked" : ""}>👤 ${esc(p.name)}</label>`).join("")}
          ${this._data.targets.map((t) => `<label><input type="checkbox" name="devices" value="${esc(t.device_id)}" ${n.devices.includes(t.device_id) ? "checked" : ""}>📱 ${esc(t.name)}</label>`).join("")}
        </div></div>
        <div class="full"><div class="sub">Knöpfe</div><div class="pick">
          ${this._buttons.map((b) => `<label><input type="checkbox" name="actions" value="${esc(b.key)}" ${n.actions.includes(b.key) ? "checked" : ""}>🔘 ${esc(b.button_title)}</label>`).join("") || `<span class="muted">Noch keine Knöpfe angelegt.</span>`}
        </div></div>
        <label class="full">Notiz (nur Doku, wird nicht gesendet)<textarea name="note" rows="2">${esc(n.note)}</textarea></label>
        <div class="derr"></div>
      </div>
      <div class="df">
        ${isNew ? "" : `<button class="btn danger left" data-delete>Löschen</button>`}
        <button class="btn flat" data-close>Abbrechen</button><button class="btn" data-save>Speichern</button>
      </div>`;

    const collect = (d) => {
      const f = (name) => d.querySelector(`[name="${name}"]`)?.value ?? "";
      const checked = (name) => [...d.querySelectorAll(`input[name="${name}"]:checked`)].map((i) => i.value);
      // Knöpfe in der Reihenfolge der bisherigen Auswahl, neue hinten
      const sel = checked("actions");
      const actions = [...n.actions.filter((a) => sel.includes(a)), ...sel.filter((a) => !n.actions.includes(a))];
      const out = {
        id: isNew ? f("id").trim() : n.id,
        category: f("category"),
        title: f("title"),
        message: f("message"),
        priority: f("priority"),
        url: f("url"),
        note: f("note"),
        persons: checked("persons"),
        devices: checked("devices"),
        actions,
      };
      if (isNew && !slugOk(out.id)) throw new Error("Die ID darf nur Kleinbuchstaben, Zahlen und _ enthalten.");
      return out;
    };

    this._openDialog(
      html,
      async (d) => {
        await this._hass.callWS({ type: `${DOMAIN}/notification/save`, notification: collect(d), original_id: isNew ? null : n.id });
        this._toast("Gespeichert – gilt ab dem nächsten Senden");
        await this._load();
      },
      async () => {
        if (!confirm(used ? `„${n.id}“ wird noch in ${used} Automation(en) verwendet. Trotzdem löschen?` : `„${n.id}“ löschen?`)) throw new Error("");
        await this._hass.callWS({ type: `${DOMAIN}/notification/delete`, notification_id: n.id });
        this._toast("Gelöscht");
        await this._load();
      }
    );
  }

  _fillDatalists() {
    const root = this.shadowRoot;
    const s = root.getElementById("dl-services");
    if (!s.childElementCount) {
      s.innerHTML = Object.entries(this._hass.services)
        .flatMap(([dom, svcs]) => Object.keys(svcs).map((svc) => `<option value="${esc(dom)}.${esc(svc)}"></option>`))
        .sort()
        .join("");
    }
    root.getElementById("dl-entities").innerHTML = Object.values(this._hass.states)
      .map((st) => `<option value="${esc(st.entity_id)}">${esc(st.attributes.friendly_name || "")}</option>`)
      .join("");
  }

  _buttonDialog(b) {
    const isNew = !b;
    b = b || { key: "", button_title: "", icon: "", steps: [], expiry_minutes: 0, authentication_required: false, destructive: false };
    this._fillDatalists();
    // Arbeitskopie der Schritte: pro Schritt Aktion, Entitäten und Zusatzdaten (als JSON-Text)
    const steps = (b.steps && b.steps.length ? b.steps : [{ service: "", target_entities: [], service_data: {} }]).map((s) => ({
      service: s.service || "",
      targets: [...(s.target_entities || [])],
      data: s.service_data && Object.keys(s.service_data).length ? JSON.stringify(s.service_data, null, 2) : "",
      open: !!(s.service_data && Object.keys(s.service_data).length),
    }));
    const stepHtml = (s, i) => `
      <div class="step" data-i="${i}">
        <div class="stephead"><b>Schritt ${i + 1}</b>
          <span class="stepbtns">
            <button class="ib" type="button" data-op="up" title="Nach oben" ${i === 0 ? "disabled" : ""}>▲</button>
            <button class="ib" type="button" data-op="down" title="Nach unten" ${i === steps.length - 1 ? "disabled" : ""}>▼</button>
            <button class="ib" type="button" data-op="del" title="Schritt entfernen" ${steps.length === 1 ? "disabled" : ""}>✕</button>
          </span></div>
        <label>Aktion<input data-f="service" list="dl-services" value="${esc(s.service)}" placeholder="z. B. switch.turn_on" autocomplete="off"></label>
        <div class="sub" style="margin-top:8px">Entitäten</div>
        <div class="pick">${s.targets.map((t, j) => `<span class="chip">${esc(this._entityName(t))} <a data-op="rm" data-j="${j}" style="cursor:pointer">✕</a></span>`).join("") || `<span class="muted">keine</span>`}</div>
        <div style="display:flex;gap:8px;margin-top:6px"><input data-f="add" list="dl-entities" placeholder="Entität suchen …" autocomplete="off"><button class="btn flat" type="button" data-op="add">Hinzufügen</button></div>
        <details ${s.open ? "open" : ""}><summary>Zusätzliche Daten (JSON, optional)</summary>
          <textarea data-f="data" rows="3" placeholder='{"brightness_pct": 50}'>${esc(s.data)}</textarea></details>
      </div>`;
    const html = `
      <div class="dh">${isNew ? "Neuer Knopf" : `Knopf <code>${esc(b.key)}</code>`}</div>
      <div class="db">
        ${isNew ? `<label>Kennung<input name="key" placeholder="z. B. licht_aus" autocomplete="off"><span class="hint">Nur a–z, 0–9 und _; danach fest.</span></label>` : ""}
        <label ${isNew ? "" : 'class="full"'}>Knopftext<input name="button_title" value="${esc(b.button_title)}" placeholder="🔓 Haustür öffnen"></label>
        <label>Symbol (SF Symbol, optional)<input name="icon" value="${esc(b.icon)}" placeholder="lock.open"></label>
        <label>Gültigkeit in Minuten<input name="expiry_minutes" type="number" min="0" max="${this._data.max_expiry_minutes}" value="${esc(b.expiry_minutes)}"><span class="hint">0 = unbegrenzt, höchstens 30 Tage.</span></label>
        <div class="full"><div class="sub">Beim Tippen – Schritte werden der Reihe nach ausgeführt, bei einem Fehler wird abgebrochen.</div>
          <div id="steps"></div>
          <button class="btn flat" type="button" id="addstep">＋ Schritt</button>
        </div>
        <div class="full pick">
          <label><input type="checkbox" name="authentication_required" ${b.authentication_required ? "checked" : ""}>Face ID / Code erforderlich</label>
          <label><input type="checkbox" name="destructive" ${b.destructive ? "checked" : ""}>Rot anzeigen</label>
        </div>
        <div class="derr"></div>
      </div>
      <div class="df">
        ${isNew ? "" : `<button class="btn danger left" data-delete>Löschen</button>`}
        <button class="btn flat" data-close>Abbrechen</button><button class="btn" data-save>Speichern</button>
      </div>`;

    const d = this._openDialog(
      html,
      async (d) => {
        const f = (name) => d.querySelector(`[name="${name}"]`)?.value ?? "";
        const c = (name) => d.querySelector(`[name="${name}"]`)?.checked ?? false;
        const key = isNew ? f("key").trim() : b.key;
        if (isNew && !slugOk(key)) throw new Error("Die Kennung darf nur Kleinbuchstaben, Zahlen und _ enthalten.");
        const payload = steps.map((s, i) => {
          let serviceData = {};
          if (s.data.trim()) {
            try { serviceData = JSON.parse(s.data); } catch (_) { throw new Error(`Schritt ${i + 1}: Die Zusatzdaten sind kein gültiges JSON.`); }
          }
          if (!s.service.trim()) throw new Error(`Schritt ${i + 1}: Bitte eine Aktion angeben.`);
          return { service: s.service.trim(), target_entities: s.targets, service_data: serviceData };
        });
        await this._hass.callWS({
          type: `${DOMAIN}/button/save`,
          subentry_id: isNew ? null : b.subentry_id,
          key,
          button_title: f("button_title"),
          icon: f("icon"),
          steps: payload,
          expiry_minutes: Number(f("expiry_minutes") || 0),
          authentication_required: c("authentication_required"),
          destructive: c("destructive"),
        });
        this._toast("Knopf gespeichert");
        await this._load();
      },
      async () => {
        if (!confirm(`Knopf „${b.button_title}“ löschen?`)) throw new Error("");
        await this._hass.callWS({ type: `${DOMAIN}/subentry/delete`, subentry_id: b.subentry_id });
        this._toast("Knopf gelöscht");
        await this._load();
      }
    );

    const box = d.querySelector("#steps");
    const redraw = () => { box.innerHTML = steps.map(stepHtml).join(""); };
    const addEntity = (i) => {
      const inp = box.querySelector(`.step[data-i="${i}"] [data-f="add"]`);
      const v = inp.value.trim();
      if (v && this._hass.states[v] && !steps[i].targets.includes(v)) steps[i].targets.push(v);
      redraw();
      box.querySelector(`.step[data-i="${i}"] [data-f="add"]`)?.focus();
    };
    box.addEventListener("input", (e) => {
      const st = e.target.closest(".step");
      if (!st) return;
      const s = steps[Number(st.dataset.i)];
      if (e.target.dataset.f === "service") s.service = e.target.value;
      if (e.target.dataset.f === "data") s.data = e.target.value;
    });
    box.addEventListener("toggle", (e) => {
      const st = e.target.closest?.(".step");
      if (st && e.target.tagName === "DETAILS") steps[Number(st.dataset.i)].open = e.target.open;
    }, true);
    box.addEventListener("keydown", (e) => {
      if (e.target.dataset.f === "add" && e.key === "Enter") { e.preventDefault(); addEntity(Number(e.target.closest(".step").dataset.i)); }
    });
    box.addEventListener("click", (e) => {
      const op = e.target.closest("[data-op]");
      if (!op) return;
      const i = Number(op.closest(".step").dataset.i);
      switch (op.dataset.op) {
        case "up": [steps[i - 1], steps[i]] = [steps[i], steps[i - 1]]; break;
        case "down": [steps[i + 1], steps[i]] = [steps[i], steps[i + 1]]; break;
        case "del": steps.splice(i, 1); break;
        case "rm": steps[i].targets.splice(Number(op.dataset.j), 1); break;
        case "add": addEntity(i); return;
      }
      redraw();
    });
    d.querySelector("#addstep").onclick = () => {
      steps.push({ service: "", targets: [], data: "", open: false });
      redraw();
      box.querySelector(`.step[data-i="${steps.length - 1}"] [data-f="service"]`)?.focus();
    };
    redraw();
  }

  _categoryDialog(c) {
    const isNew = !c;
    c = c || { key: "", title: "", group: "" };
    const html = `
      <div class="dh">${isNew ? "Neue Kategorie" : `Kategorie <code>${esc(c.key)}</code>`}</div>
      <div class="db">
        ${isNew ? `<label>Kennung<input name="key" placeholder="z. B. garten" autocomplete="off"><span class="hint">Nur a–z, 0–9 und _; danach fest.</span></label>` : ""}
        <label ${isNew ? "" : 'class="full"'}>Name<input name="title" value="${esc(c.title)}" placeholder="🌱 Garten"><span class="hint">Wird als Titel verwendet, wenn eine Benachrichtigung keinen eigenen hat.</span></label>
        <label class="full">Gruppierung (optional)<input name="group" value="${esc(c.group)}"><span class="hint">Gleiche Gruppierung = auf dem iPhone gestapelt. Leer = Kennung.</span></label>
        <div class="derr"></div>
      </div>
      <div class="df">
        ${isNew ? "" : `<button class="btn danger left" data-delete>Löschen</button>`}
        <button class="btn flat" data-close>Abbrechen</button><button class="btn" data-save>Speichern</button>
      </div>`;
    this._openDialog(
      html,
      async (d) => {
        const f = (name) => d.querySelector(`[name="${name}"]`)?.value ?? "";
        const key = isNew ? f("key").trim() : c.key;
        if (isNew && !slugOk(key)) throw new Error("Die Kennung darf nur Kleinbuchstaben, Zahlen und _ enthalten.");
        await this._hass.callWS({ type: `${DOMAIN}/category/save`, subentry_id: isNew ? null : c.subentry_id, key, title: f("title"), group: f("group") });
        this._toast("Kategorie gespeichert");
        await this._load();
      },
      async () => {
        if (!confirm(`Kategorie „${c.title}“ löschen?`)) throw new Error("");
        await this._hass.callWS({ type: `${DOMAIN}/subentry/delete`, subentry_id: c.subentry_id });
        this._toast("Kategorie gelöscht");
        await this._load();
      }
    );
  }
}

customElements.define("notification-hub-panel", NotificationHubPanel);
