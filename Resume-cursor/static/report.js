const REPORT_STORAGE_KEY = "resume_review_report";

const dimLabels = {
  project_depth: "项目深度",
  tech_match: "技术匹配度",
  expression: "表达规范性",
  structure: "简历结构",
  quantification: "量化程度",
  credibility: "真实可信度",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function scoresHtml(data) {
  const report = data.report || {};
  const scores = report.scores || {};
  return `
    <div class="score-hero"><strong>${escapeHtml(data.overall_score ?? "-")}</strong><span class="muted">/ 100</span></div>
    ${Object.keys(dimLabels).map((key) => {
      const item = scores[key] || {};
      const score = item.score ?? 0;
      const evidence = (item.evidence || [])
        .map((anchor) => `<code>${escapeHtml(anchor)}</code>`)
        .join(" ");
      return `<div class="dim"><span>${dimLabels[key]}</span><div class="bar"><span style="width:${Number(score) || 0}%"></span></div><strong>${escapeHtml(score)}</strong></div><p class="muted">${escapeHtml(item.comment || "")}</p>${evidence ? `<p class="muted">依据：${evidence}</p>` : ""}`;
    }).join("")}
  `;
}

function summaryHtml(data) {
  const summary = (data.report || {}).summary || {};
  const jobFit = summary.job_fit || {};
  return `
    <h3>核心亮点</h3>
    <ul>${(summary.highlights || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    <h3>最重要的改进方向</h3>
    <ul>${(summary.improvements || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    <h3>综合评语</h3>
    <p>${escapeHtml(summary.overall_comment || "")}</p>
    <h3>岗位匹配度</h3>
    <p><strong>${escapeHtml(jobFit.score ?? "-")}</strong> ${escapeHtml(jobFit.comment || "")}</p>
  `;
}

function renderReportBoard(data) {
  const waiting = document.getElementById("report-waiting");
  const board = document.getElementById("report-board");
  const title = document.getElementById("report-title");
  if (!board) return;
  if (waiting) waiting.classList.add("hidden");
  board.classList.remove("hidden");
  if (title) {
    title.textContent = [data.filename, data.status].filter(Boolean).join(" · ");
  }
  document.getElementById("col-scores").innerHTML = scoresHtml(data);
  document.getElementById("col-summary").innerHTML = summaryHtml(data);
}

function saveReportData(data) {
  localStorage.setItem(REPORT_STORAGE_KEY, JSON.stringify(data));
}

function loadReportData() {
  const raw = localStorage.getItem(REPORT_STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function clearReportData() {
  localStorage.removeItem(REPORT_STORAGE_KEY);
}

function goToReportPage(data) {
  const payload = { ...data };
  delete payload._waitId;
  saveReportData(payload);
  window.location.assign("/report");
}

function bootReportPage() {
  const apply = (data) => {
    if (!data || !data.report) return false;
    renderReportBoard(data);
    return true;
  };

  if (apply(loadReportData())) return;
  const waiting = document.getElementById("report-waiting");
  if (waiting) waiting.textContent = "暂无报告，请返回审查页提交简历。";
}
