const tokenKey = "resume_token";

const authView = document.getElementById("auth-view");
const appView = document.getElementById("app-view");
const authError = document.getElementById("auth-error");
const who = document.getElementById("who");
const reportEl = document.getElementById("report");
const reviewStatus = document.getElementById("review-status");

let currentUser = null;

function token() {
  return localStorage.getItem(tokenKey);
}

function formatDetail(data) {
  const detail = data && data.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        const loc = Array.isArray(item.loc) ? item.loc.filter((part) => part !== "body").join(".") : "";
        return loc ? `${loc}: ${item.msg}` : item.msg || JSON.stringify(item);
      })
      .join("；");
  }
  return detail ? JSON.stringify(detail) : "";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function confirmDelete(message, title = "确认删除") {
  const dialog = document.getElementById("confirm-dialog");
  const msgEl = document.getElementById("confirm-message");
  const titleEl = document.getElementById("confirm-title");
  const btnOk = document.getElementById("confirm-ok");
  const btnCancel = document.getElementById("confirm-cancel");
  const backdrop = dialog.querySelector(".confirm-backdrop");
  titleEl.textContent = title;
  msgEl.textContent = message;
  dialog.classList.remove("hidden");
  return new Promise((resolve) => {
    const finish = (value) => {
      dialog.classList.add("hidden");
      btnOk.onclick = null;
      btnCancel.onclick = null;
      backdrop.onclick = null;
      document.removeEventListener("keydown", onKey);
      resolve(value);
    };
    const onKey = (event) => {
      if (event.key === "Escape") finish(false);
    };
    btnOk.onclick = () => finish(true);
    btnCancel.onclick = () => finish(false);
    backdrop.onclick = () => finish(false);
    document.addEventListener("keydown", onKey);
    btnCancel.focus();
  });
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (token()) headers.Authorization = `Bearer ${token()}`;
  if (options.body && !(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, { ...options, headers });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!res.ok) {
    throw new Error(formatDetail(data) || "请求失败");
  }
  return data;
}

function showAuth() {
  authView.classList.remove("hidden");
  appView.classList.add("hidden");
}

function showApp() {
  authView.classList.add("hidden");
  appView.classList.remove("hidden");
}

document.getElementById("tab-login").onclick = () => {
  document.getElementById("tab-login").classList.add("active");
  document.getElementById("tab-register").classList.remove("active");
  document.getElementById("form-login").classList.remove("hidden");
  document.getElementById("form-register").classList.add("hidden");
};

document.getElementById("tab-register").onclick = () => {
  document.getElementById("tab-register").classList.add("active");
  document.getElementById("tab-login").classList.remove("active");
  document.getElementById("form-register").classList.remove("hidden");
  document.getElementById("form-login").classList.add("hidden");
};

document.getElementById("form-login").onsubmit = async (event) => {
  event.preventDefault();
  authError.textContent = "";
  const form = new FormData(event.target);
  try {
    const data = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: form.get("email"), password: form.get("password") }),
    });
    localStorage.setItem(tokenKey, data.access_token);
    await boot();
  } catch (err) {
    authError.textContent = err.message;
  }
};

document.getElementById("form-register").onsubmit = async (event) => {
  event.preventDefault();
  authError.textContent = "";
  const form = new FormData(event.target);
  try {
    const data = await api("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({
        token: form.get("token"),
        email: form.get("email"),
        password: form.get("password"),
      }),
    });
    localStorage.setItem(tokenKey, data.access_token);
    await boot();
  } catch (err) {
    authError.textContent = err.message;
  }
};

document.getElementById("btn-logout").onclick = () => {
  localStorage.removeItem(tokenKey);
  currentUser = null;
  showAuth();
};

document.querySelectorAll(".nav-btn").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll(".nav-btn").forEach((item) => item.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll(".panel").forEach((panel) => panel.classList.add("hidden"));
    document.getElementById(`panel-${btn.dataset.panel}`).classList.remove("hidden");
    if (btn.dataset.panel === "history") loadHistory();
    if (btn.dataset.panel === "invites") loadInvites();
    if (btn.dataset.panel === "admin") loadTenants();
  };
});

const reviewFile = document.getElementById("review-file");
const extractPreview = document.getElementById("extract-preview");
const extractMeta = document.getElementById("extract-meta");
const extractWarn = document.getElementById("extract-warn");
const extractText = document.getElementById("extract-text");
const btnReview = document.getElementById("btn-review");
const btnOpenReport = document.getElementById("btn-open-report");
let extractReady = false;

function resetExtractPreview() {
  extractReady = false;
  btnReview.disabled = true;
  extractPreview.classList.add("hidden");
  extractText.textContent = "";
  extractMeta.textContent = "";
  extractWarn.textContent = "";
  extractWarn.classList.add("hidden");
}

reviewFile.onchange = async () => {
  const file = reviewFile.files && reviewFile.files[0];
  resetExtractPreview();
  reportEl.classList.add("hidden");
  if (!file) return;
  reviewStatus.textContent = "正在提取文本…";
  const body = new FormData();
  body.append("file", file);
  try {
    const data = await api("/api/reviews/extract", { method: "POST", body });
    const layoutLabel = data.layout === "two_column" ? "双栏" : "单栏";
    const fallbackCount = data.fallback_sentence_count ?? 0;
    const fallbackPct = Math.round((data.fallback_ratio || 0) * 100);
    extractMeta.textContent = `${data.filename} · ${layoutLabel} · ${data.section_count} 个父块 · ${data.sentence_count} 个子块 · 正文 ${fallbackCount} 段（${fallbackPct}%）`;
    extractText.textContent = data.anchored_text || "";
    extractPreview.classList.remove("hidden");
    if (fallbackPct >= 40) {
      extractWarn.textContent = `有 ${fallbackPct}% 的片段没有识别到「工作经历 / 项目经历 / 专业技能」等标题，落在「正文」。请核对预览；若标题未识别或双栏错位，打分锚点会跟着偏。`;
      extractWarn.classList.remove("hidden");
    }
    extractReady = true;
    btnReview.disabled = false;
    reviewStatus.textContent = "请先核对提取文本，确认后再开始审查。";
  } catch (err) {
    reviewStatus.textContent = err.message;
  }
};

document.getElementById("form-review").onsubmit = async (event) => {
  event.preventDefault();
  if (!extractReady) {
    reviewStatus.textContent = "请先选择 PDF 并等待文本提取完成";
    return;
  }
  reviewStatus.textContent = "正在审查，请稍候。完成后会自动进入报告页…";
  btnReview.disabled = true;
  btnOpenReport.classList.add("hidden");
  const form = new FormData(event.target);
  try {
    const data = await api("/api/reviews", { method: "POST", body: form });
    reviewStatus.textContent = "审查完成，正在进入报告页…";
    goToReportPage(data);
  } catch (err) {
    reviewStatus.textContent = err.message;
    btnReview.disabled = !extractReady;
  }
};

btnOpenReport.onclick = () => {
  const cached = loadReportData();
  if (!cached) {
    reviewStatus.textContent = "还没有可打开的报告";
    return;
  }
  goToReportPage(cached);
};

document.getElementById("form-invite").onsubmit = async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const result = document.getElementById("invite-result");
  try {
    const data = await api("/api/invites", {
      method: "POST",
      body: JSON.stringify({ email: form.get("email"), role: form.get("role") }),
    });
    result.innerHTML = `邀请码：<code>${data.token}</code>（发给 ${data.email}）`;
    await loadInvites();
  } catch (err) {
    result.textContent = err.message;
  }
};

document.getElementById("form-tenant").onsubmit = async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const result = document.getElementById("tenant-result");
  try {
    const data = await api("/api/admin/tenants", {
      method: "POST",
      body: JSON.stringify({
        name: form.get("name"),
        slug: form.get("slug"),
        admin_email: form.get("admin_email"),
      }),
    });
    result.innerHTML = `已创建 ${data.name}。企业管理员邀请码：<code>${data.invite_token}</code>`;
    await loadTenants();
  } catch (err) {
    result.textContent = err.message;
  }
};

function historyStatusLabel(status) {
  if (status === "succeeded") return "已完成";
  if (status === "failed") return "失败";
  if (status === "running") return "审查中";
  return status || "-";
}

async function loadHistory() {
  const box = document.getElementById("history-list");
  const selectAll = document.getElementById("history-select-all");
  const btnDelete = document.getElementById("btn-history-delete");
  const status = document.getElementById("history-status");
  const keepStatus = status.textContent;
  box.innerHTML = '<p class="muted history-empty">加载中…</p>';
  selectAll.checked = false;
  selectAll.indeterminate = false;
  btnDelete.disabled = true;
  selectAll.onchange = null;
  btnDelete.onclick = null;
  try {
    const items = await api("/api/reviews");
    if (!items.length) {
      box.innerHTML = '<p class="muted history-empty">暂无记录</p>';
      status.textContent = keepStatus.startsWith("已删除") ? keepStatus : "未选择记录";
      return;
    }
    box.innerHTML = items.map((item) => `
      <div class="history-row" data-id="${item.id}">
        <label class="history-check-wrap">
          <input type="checkbox" class="history-check" aria-label="选择 ${escapeHtml(item.filename || "简历")}">
        </label>
        <button type="button" class="history-file" title="查看报告">${escapeHtml(item.filename || "简历")}</button>
        <span class="history-job">${escapeHtml(item.job_title || "未指定岗位")}</span>
        <span class="history-score">${escapeHtml(item.overall_score ?? "-")}</span>
        <span class="history-state">${escapeHtml(historyStatusLabel(item.status))}</span>
        <div class="history-actions">
          <button type="button" class="history-view">查看</button>
          <button type="button" class="history-delete">删除</button>
        </div>
      </div>
    `).join("");
    const syncToolbar = () => {
      const checks = [...box.querySelectorAll(".history-check")];
      const selected = checks.filter((item) => item.checked);
      btnDelete.disabled = selected.length === 0;
      selectAll.checked = checks.length > 0 && selected.length === checks.length;
      selectAll.indeterminate = selected.length > 0 && selected.length < checks.length;
      checks.forEach((item) => {
        item.closest(".history-row").classList.toggle("is-selected", item.checked);
      });
      status.textContent = selected.length ? `已选 ${selected.length} 条，可批量删除` : "未选择记录";
    };
    const selectedIds = () => [...box.querySelectorAll(".history-check:checked")]
      .map((item) => item.closest(".history-row").dataset.id);
    const forgetIfCached = (ids) => {
      const cached = loadReportData();
      if (cached && ids.includes(String(cached.id))) clearReportData();
    };
    const deleteIds = async (ids, mode) => {
      if (!ids.length) return;
      const message = mode === "single"
        ? "确定删除这条审查记录吗？删除后无法恢复。"
        : `确定批量删除选中的 ${ids.length} 条记录吗？删除后无法恢复。`;
      const title = mode === "single" ? "删除审查记录" : "批量删除";
      const ok = await confirmDelete(message, title);
      if (!ok) return;
      btnDelete.disabled = true;
      try {
        let deleted = 0;
        if (mode === "single") {
          const data = await api(`/api/reviews/${encodeURIComponent(ids[0])}`, { method: "DELETE" });
          deleted = data.deleted ?? 1;
        } else {
          const data = await api("/api/reviews/batch-delete", {
            method: "POST",
            body: JSON.stringify({ ids }),
          });
          deleted = data.deleted ?? 0;
        }
        if (!deleted) {
          status.textContent = "未删除任何记录，请刷新页面后重试";
          btnDelete.disabled = selectedIds().length === 0;
          return;
        }
        forgetIfCached(ids);
        await loadHistory();
        document.getElementById("history-status").textContent = `已删除 ${deleted} 条`;
      } catch (err) {
        const text = err.message || "删除失败";
        status.textContent = text.includes("Method Not Allowed") || text.includes("Not Found")
          ? `${text}。请重启服务后再试（python web_run.py）`
          : text;
        btnDelete.disabled = selectedIds().length === 0;
      }
    };
    const openReport = async (id) => {
      try {
        const data = await api(`/api/reviews/${id}`);
        goToReportPage(data);
      } catch (err) {
        status.textContent = err.message;
      }
    };
    selectAll.onchange = () => {
      box.querySelectorAll(".history-check").forEach((item) => {
        item.checked = selectAll.checked;
      });
      syncToolbar();
    };
    btnDelete.onclick = () => deleteIds(selectedIds(), "batch");
    box.querySelectorAll(".history-row").forEach((row) => {
      const id = row.dataset.id;
      row.querySelector(".history-check").onchange = syncToolbar;
      row.querySelector(".history-file").onclick = () => openReport(id);
      row.querySelector(".history-view").onclick = () => openReport(id);
      row.querySelector(".history-delete").onclick = (event) => {
        event.stopPropagation();
        deleteIds([id], "single");
      };
    });
    syncToolbar();
    if (keepStatus.startsWith("已删除")) {
      status.textContent = keepStatus;
    }
  } catch (err) {
    box.innerHTML = `<p class="muted history-empty">${escapeHtml(err.message)}</p>`;
  }
}

async function loadInvites() {
  const box = document.getElementById("invite-list");
  try {
    const items = await api("/api/invites");
    box.innerHTML = items.map((item) => `
      <div class="list-row" style="cursor:default">
        <span>${item.email} · ${item.role}${item.used_at ? " · 已使用" : ""}</span>
        <code>${item.token}</code>
      </div>
    `).join("") || '<p class="muted">暂无邀请</p>';
  } catch (err) {
    box.textContent = err.message;
  }
}

async function loadTenants() {
  const box = document.getElementById("tenant-list");
  try {
    const items = await api("/api/admin/tenants");
    box.innerHTML = items.map((item) => `
      <div class="list-row" style="cursor:default">
        <span>${item.name}（${item.slug}）${item.is_active ? "" : " · 已停用"}</span>
        <button type="button" data-id="${item.id}" data-active="${item.is_active ? "0" : "1"}">${item.is_active ? "停用" : "启用"}</button>
      </div>
    `).join("") || '<p class="muted">暂无企业</p>';
    box.querySelectorAll("button[data-id]").forEach((btn) => {
      btn.onclick = async () => {
        await api(`/api/admin/tenants/${btn.dataset.id}`, {
          method: "PATCH",
          body: JSON.stringify({ is_active: btn.dataset.active === "1" }),
        });
        await loadTenants();
      };
    });
  } catch (err) {
    box.textContent = err.message;
  }
}

async function boot() {
  if (!token()) {
    showAuth();
    return;
  }
  try {
    currentUser = await api("/api/auth/me");
  } catch {
    localStorage.removeItem(tokenKey);
    showAuth();
    return;
  }
  who.textContent = `${currentUser.email} · ${currentUser.role}${currentUser.tenant_name ? " · " + currentUser.tenant_name : ""}`;
  document.getElementById("nav-invites").classList.toggle("hidden", currentUser.role !== "tenant_admin");
  document.getElementById("nav-admin").classList.toggle("hidden", currentUser.role !== "platform_admin");
  document.querySelector('[data-panel="review"]').classList.toggle("hidden", currentUser.role === "platform_admin");
  document.querySelector('[data-panel="history"]').classList.toggle("hidden", currentUser.role === "platform_admin");
  if (currentUser.role === "platform_admin") {
    document.querySelector('[data-panel="admin"]').click();
  }
  showApp();
}

boot();
