const state = {
  archive: "",
  q: "",
  page: 1,
  perPage: 50,
  total: 0,
  pages: 0,
  selectedId: null,
  mode: "html",
  allowRemote: false,
  hasAttachment: false,
  archives: [],
};

const el = (id) => document.getElementById(id);

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatDate(ts, raw) {
  if (ts) {
    try {
      return new Date(ts * 1000).toLocaleString("it-IT", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch (_) {
      return raw || "";
    }
  }
  return raw || "";
}

function formatSize(bytes) {
  const n = Number(bytes || 0);
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message = typeof data === "object" && data.error
      ? data.error
      : `Errore HTTP ${response.status}`;
    throw new Error(message);
  }
  return data;
}

async function loadArchives() {
  const data = await fetchJson("/api/archives");
  state.archives = data.archives || [];

  const select = el("archiveSelect");
  const current = state.archive;
  select.innerHTML = '<option value="">Tutti gli archivi</option>';

  const list = el("archiveList");
  list.innerHTML = "";

  for (const archive of state.archives) {
    const option = document.createElement("option");
    option.value = archive.name;
    option.textContent = archive.name;
    select.appendChild(option);

    const button = document.createElement("button");
    button.type = "button";
    button.className = "archive-item" + (state.archive === archive.name ? " active" : "");
    button.dataset.archive = archive.name;
    button.innerHTML = `
      <span>${esc(archive.name)}</span>
      <span class="archive-count">${esc(archive.messages)}</span>
    `;
    button.addEventListener("click", () => {
      state.archive = archive.name;
      state.page = 1;
      el("archiveSelect").value = archive.name;
      document.querySelectorAll(".archive-item").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      loadMessages();
    });
    list.appendChild(button);
  }

  select.value = current;
}

async function loadMessages() {
  const params = new URLSearchParams({
    page: String(state.page),
    per_page: String(state.perPage),
    sort: el("sortSelect").value,
    q: state.q,
  });

  if (state.archive) params.set("archive", state.archive);
  if (state.hasAttachment) params.set("has_attachment", "1");

  const data = await fetchJson(`/api/messages?${params.toString()}`);
  state.total = data.total;
  state.pages = data.pages;

  const list = el("messageList");
  list.innerHTML = "";

  if (!data.messages.length) {
    list.innerHTML = '<div class="empty-state"><p>Nessun messaggio trovato.</p></div>';
  }

  for (const message of data.messages) {
    const row = document.createElement("div");
    row.className = "message-row" + (state.selectedId === message.id ? " selected" : "");
    row.dataset.id = message.id;

    const from = message.from_name
      ? `${message.from_name} <${message.from_addr || ""}>`
      : message.from_addr || "(mittente sconosciuto)";

    row.innerHTML = `
      <div class="message-from">${esc(from)}</div>
      <div class="message-main">
        <div class="message-subject">
          ${esc(message.subject || "(senza oggetto)")}
          ${message.has_attachments ? '<span class="attachment-badge" title="Allegati">📎</span>' : ""}
        </div>
        <div class="message-preview">${esc(message.preview || "")}</div>
      </div>
      <div class="message-side">${esc(formatDate(message.date_ts, message.date_raw))}</div>
    `;

    row.addEventListener("click", () => openMessage(message.id));
    list.appendChild(row);
  }

  el("resultInfo").textContent = `${data.total} messaggi`;
  el("pageInfo").textContent = data.pages
    ? `Pagina ${data.page} di ${data.pages}`
    : "Pagina 1";
  el("prevPage").disabled = data.page <= 1;
  el("nextPage").disabled = data.pages === 0 || data.page >= data.pages;
}

function renderAttachments(attachments) {
  const section = el("attachmentsSection");
  const list = el("attachmentsList");
  list.innerHTML = "";

  if (!attachments || !attachments.length) {
    section.classList.add("hidden");
    return;
  }

  section.classList.remove("hidden");

  for (const attachment of attachments) {
    const item = document.createElement("div");
    item.className = "attachment-item";

    const previewable = [
      "image/jpeg",
      "image/jpg",
      "image/png",
      "image/gif",
      "image/webp",
      "application/pdf",
    ].includes(attachment.mime);

    const previewUrl = `/api/messages/${state.selectedId}/attachments/${attachment.id}`;
    const downloadUrl = `${previewUrl}?download=1`;

    item.innerHTML = `
      <div>
        <div class="attachment-name">${esc(attachment.filename || "allegato")}</div>
        <div class="attachment-meta">${esc(attachment.mime)} · ${esc(formatSize(attachment.size))}</div>
      </div>
      <div class="attachment-actions">
        ${previewable ? `<a href="${previewUrl}" target="_blank" rel="noopener noreferrer">Apri</a>` : ""}
        <a href="${downloadUrl}">Scarica</a>
      </div>
    `;
    list.appendChild(item);
  }
}

async function setMessageBody() {
  if (!state.selectedId) return;

  const frame = el("msgBodyHtml");
  const text = el("msgBodyText");

  if (state.mode === "text") {
    frame.classList.add("hidden");
    text.classList.remove("hidden");

    const body = await fetchJson(
      `/api/messages/${state.selectedId}/body?mode=text`
    ).catch(() => "");
    text.textContent = typeof body === "string" ? body : "";
    return;
  }

  text.classList.add("hidden");
  frame.classList.remove("hidden");

  const params = new URLSearchParams({
    mode: "html",
    allow_remote: state.allowRemote ? "1" : "0",
  });

  const response = await fetch(`/api/messages/${state.selectedId}/body?${params.toString()}`);
  const html = response.ok ? await response.text() : "";

  frame.srcdoc = html || "<p style='font-family:sans-serif;color:#666'>Nessun contenuto HTML disponibile.</p>";
}

async function openMessage(id) {
  state.selectedId = id;
  document.querySelectorAll(".message-row").forEach((row) => {
    row.classList.toggle("selected", Number(row.dataset.id) === Number(id));
  });

  el("messageEmpty").classList.add("hidden");
  el("messageDetail").classList.remove("hidden");

  const detail = await fetchJson(`/api/messages/${id}`);

  el("msgSubject").textContent = detail.subject || "(senza oggetto)";

  const fromLine = detail.from_name
    ? `${detail.from_name} &lt;${esc(detail.from_addr)}&gt;`
    : esc(detail.from_addr || "(mittente sconosciuto)");

  el("msgMeta").innerHTML = `
    <div><strong>Da:</strong> ${fromLine}</div>
    <div><strong>A:</strong> ${esc(detail.to_addrs || "")}</div>
    ${detail.cc_addrs ? `<div><strong>CC:</strong> ${esc(detail.cc_addrs)}</div>` : ""}
    <div><strong>Data:</strong> ${esc(formatDate(detail.date_ts, detail.date_raw))}</div>
    <div><strong>Archivio:</strong> ${esc(detail.archive)}</div>
  `;

  el("msgHeaders").textContent = JSON.stringify(detail.headers || {}, null, 2);

  renderAttachments(detail.attachments);
  await setMessageBody();

  el("listPanel").classList.add("mobile-hidden");
  el("messagePanel").classList.add("mobile-active");
}

function closeMessage() {
  el("listPanel").classList.remove("mobile-hidden");
  el("messagePanel").classList.remove("mobile-active");
}

function setupEvents() {
  el("sidebarToggle").addEventListener("click", () => {
    el("sidebar").classList.toggle("open");
  });

  el("searchForm").addEventListener("submit", (event) => {
    event.preventDefault();
    state.q = el("searchInput").value.trim();
    state.page = 1;
    loadMessages();
  });

  el("archiveSelect").addEventListener("change", (event) => {
    state.archive = event.target.value;
    state.page = 1;
    loadMessages();
  });

  el("sortSelect").addEventListener("change", () => {
    state.page = 1;
    loadMessages();
  });

  el("refreshButton").addEventListener("click", async () => {
    el("refreshButton").disabled = true;
    try {
      await fetchJson("/api/index/rebuild", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      await loadArchives();
      await loadMessages();
    } catch (error) {
      alert(error.message);
    } finally {
      el("refreshButton").disabled = false;
    }
  });

  el("prevPage").addEventListener("click", () => {
    if (state.page > 1) {
      state.page -= 1;
      loadMessages();
    }
  });

  el("nextPage").addEventListener("click", () => {
    if (state.page < state.pages) {
      state.page += 1;
      loadMessages();
    }
  });

  document.querySelectorAll("[data-nav]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-nav]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");

      if (button.dataset.nav === "attachments") {
        state.hasAttachment = true;
        state.q = "";
        el("searchInput").value = "";
      } else {
        state.hasAttachment = false;
      }

      state.page = 1;
      loadMessages();
    });
  });

  el("backButton").addEventListener("click", closeMessage);

  el("htmlMode").addEventListener("click", async () => {
    state.mode = "html";
    el("htmlMode").classList.add("active");
    el("textMode").classList.remove("active");
    await setMessageBody();
  });

  el("textMode").addEventListener("click", async () => {
    state.mode = "text";
    el("textMode").classList.add("active");
    el("htmlMode").classList.remove("active");
    await setMessageBody();
  });

  el("remoteImages").addEventListener("change", async (event) => {
    state.allowRemote = event.target.checked;
    if (state.mode === "html") {
      await setMessageBody();
    }
  });
}

async function init() {
  setupEvents();
  try {
    await loadArchives();
    await loadMessages();
  } catch (error) {
    el("resultInfo").textContent = `Errore: ${error.message}`;
  }
}

document.addEventListener("DOMContentLoaded", init);
