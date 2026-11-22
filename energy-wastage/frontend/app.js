const state = { results: null, polling: null };

function setupNavigation() {
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
      document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
      button.classList.add("active");
      document.getElementById(button.dataset.view).classList.add("active");
      requestAnimationFrame(() => drawAll());
    });
  });
}

function canvasContext(id) {
  const canvas = document.getElementById(id);
  if (!canvas) return null;
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, rect.width * dpr);
  canvas.height = Math.max(1, rect.height * dpr);
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, rect.width, rect.height);
  return { ctx, width: rect.width, height: rect.height };
}

function axes(ctx, width, height, padding = 38) {
  ctx.strokeStyle = "#edf1f6";
  ctx.fillStyle = "#9aa6b5";
  ctx.font = "10px Inter, sans-serif";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = padding + ((height - padding * 1.5) * i) / 4;
    ctx.beginPath(); ctx.moveTo(padding, y); ctx.lineTo(width - 12, y); ctx.stroke();
  }
  return { left: padding, right: width - 12, top: padding, bottom: height - 28 };
}

function lineChart(id, series, options = {}) {
  const c = canvasContext(id);
  if (!c) return;
  const { ctx, width, height } = c;
  const box = axes(ctx, width, height);
  const flat = series.flatMap((s) => s.values);
  const min = options.min ?? Math.min(...flat);
  const max = options.max ?? Math.max(...flat);
  const range = max - min || 1;
  series.forEach((seriesItem) => {
    ctx.beginPath();
    ctx.strokeStyle = seriesItem.color;
    ctx.lineWidth = seriesItem.width || 2;
    if (seriesItem.dashed) ctx.setLineDash([5, 4]);
    else ctx.setLineDash([]);
    seriesItem.values.forEach((value, index) => {
      const x = box.left + (index / Math.max(1, seriesItem.values.length - 1)) * (box.right - box.left);
      const y = box.bottom - ((value - min) / range) * (box.bottom - box.top);
      if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();
  });
  ctx.setLineDash([]);
}

function barChart(id, values, labels, color) {
  const c = canvasContext(id);
  if (!c) return;
  const { ctx, width, height } = c;
  const box = axes(ctx, width, height);
  const max = Math.max(...values) || 1;
  const slot = (box.right - box.left) / values.length;
  values.forEach((value, index) => {
    const barWidth = Math.max(3, slot * 0.58);
    const x = box.left + slot * index + (slot - barWidth) / 2;
    const barHeight = ((value / max) * (box.bottom - box.top));
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.roundRect(x, box.bottom - barHeight, barWidth, barHeight, 3);
    ctx.fill();
    if (values.length <= 12) {
      ctx.fillStyle = "#9aa6b5";
      ctx.textAlign = "center";
      ctx.fillText(labels[index] ?? "", x + barWidth / 2, height - 8);
    }
  });
}

function histogramChart(id, values, threshold) {
  const c = canvasContext(id);
  if (!c) return;
  const { ctx, width, height } = c;
  const box = axes(ctx, width, height);
  if (!values.length) return;
  const bins = 35;
  const min = Math.min(...values), max = Math.max(...values);
  const range = max - min || 1;
  const counts = Array(bins).fill(0);
  values.forEach((value) => {
    const index = Math.min(bins - 1, Math.floor(((value - min) / range) * bins));
    counts[index]++;
  });
  const maxCount = Math.max(...counts);
  const slot = (box.right - box.left) / bins;
  counts.forEach((count, index) => {
    const barHeight = (count / maxCount) * (box.bottom - box.top);
    ctx.fillStyle = "#7a91da";
    ctx.fillRect(box.left + index * slot, box.bottom - barHeight, Math.max(1, slot - 1), barHeight);
  });
  if (threshold !== undefined) {
    const x = box.left + ((threshold - min) / range) * (box.right - box.left);
    ctx.setLineDash([5, 4]); ctx.strokeStyle = "#ed6a72"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(x, box.top); ctx.lineTo(x, box.bottom); ctx.stroke();
    ctx.setLineDash([]);
  }
}

function drawAll() {
  if (!state.results) return;
  const r = state.results;
  const sample = r.actual_kw.length > r.sample_limit ? r.sample_limit : r.actual_kw.length;
  lineChart("reconstructionChart", [
    { values: r.actual_kw.slice(0, sample), color: "#2f73e8", width: 1.5 },
    { values: r.reconstructed_kw.slice(0, sample), color: "#19a974", width: 1.5, dashed: true },
  ]);
  histogramChart("errorChart", r.test_mae, r.threshold);
  barChart("hourlyChart", r.hourly_profile.map((x) => x.kw), r.hourly_profile.map((x) => String(x.hour)), "#efa83a");
  barChart("weeklyChart", r.weekly_profile.map((x) => x.kw), r.weekly_profile.map((x) => x.day), "#19a974");
  lineChart("lossChart", [
    { values: r.training_history.loss, color: "#2f73e8" },
    { values: r.training_history.val_loss, color: "#ed6a72", dashed: true },
  ]);
  drawAnomalyTimeline(r);
}

function drawAnomalyTimeline(r) {
  const c = canvasContext("anomalyChart");
  if (!c) return;
  const { ctx, width, height } = c;
  const box = axes(ctx, width, height);
  const max = Math.max(...r.actual_kw) || 1;
  const step = (box.right - box.left) / Math.max(1, r.actual_kw.length - 1);
  ctx.beginPath(); ctx.strokeStyle = "#9daabd"; ctx.lineWidth = 1;
  r.actual_kw.forEach((value, index) => {
    const x = box.left + step * index;
    const y = box.bottom - (value / max) * (box.bottom - box.top);
    if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.stroke();
  r.actual_kw.forEach((value, index) => {
    if (r.anomaly_mask[index]) {
      const x = box.left + step * index;
      const y = box.bottom - (value / max) * (box.bottom - box.top);
      ctx.beginPath(); ctx.fillStyle = "#ed6a72"; ctx.arc(x, y, 2.2, 0, Math.PI * 2); ctx.fill();
    }
  });
}

function renderResults(r) {
  state.results = r;
  document.getElementById("periodValue").textContent = `${r.period_hours.toLocaleString()} hours`;
  document.getElementById("periodNote").textContent = `${r.interval_count.toLocaleString()} 15-minute intervals`;
  document.getElementById("anomalyValue").textContent = `${r.anomaly_ratio}%`;
  document.getElementById("anomalyNote").textContent = `${r.detected_anomalies.toLocaleString()} sequences detected`;
  document.getElementById("wastageValue").textContent = `${r.estimated_wastage_kwh.toFixed(3)} kWh`;
  document.getElementById("f1Value").textContent = r.test_metrics ? `${(r.test_metrics.f1 * 100).toFixed(1)}%` : "N/A";
  document.getElementById("f1Note").textContent = r.test_metrics
    ? `Precision ${(r.test_metrics.precision * 100).toFixed(1)}% · Recall ${(r.test_metrics.recall * 100).toFixed(1)}%`
    : "Requires labeled input data";
  document.getElementById("thresholdBadge").textContent = `Threshold ${r.threshold.toFixed(5)} (${r.threshold_percentile}%)`;

  const cards = document.querySelectorAll("#splitGrid div");
  const dataset = r.dataset;
  cards[0].querySelector("strong").textContent = dataset.total_rows.toLocaleString();
  cards[1].querySelector("strong").textContent = dataset.train_rows.toLocaleString();
  cards[2].querySelector("strong").textContent = dataset.validation_rows.toLocaleString();
  cards[3].querySelector("strong").textContent = dataset.test_rows.toLocaleString();

  document.getElementById("thresholdTable").innerHTML = r.threshold_options.map((item) => `
    <div class="threshold-item">
      <strong>${item.percentile}%</strong>
      <span>${item.flagged.toLocaleString()} flagged</span>
      <span>Threshold ${item.threshold.toFixed(5)}</span>
    </div>
  `).join("");
  const metricsText = r.test_metrics
    ? ` Labeled-window F1: ${(r.test_metrics.f1 * 100).toFixed(1)}% across ${r.test_metrics.evaluated_windows} test windows.`
    : " No labels were provided, so supervised accuracy metrics are unavailable.";
  document.querySelector("#notice").textContent = `Analysis complete — LSTM detected ${r.detected_anomalies.toLocaleString()} anomalies; statistical baseline detected ${r.statistical_anomalies.toLocaleString()} intervals.${metricsText}`;
  drawAll();
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { message = (await response.json()).detail || message; } catch (_) {}
    throw new Error(message);
  }
  return response.json();
}

function showProgress(show) {
  document.getElementById("progressOverlay").classList.toggle("visible", show);
}

async function runAnalysis() {
  const payload = {
    threshold_percentile: Number(document.getElementById("thresholdInput").value),
    epochs: Number(document.getElementById("epochsInput").value),
    sequence_length: Number(document.getElementById("sequenceInput").value),
  };
  showProgress(true);
  try {
    await api("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (state.polling) clearInterval(state.polling);
    state.polling = setInterval(pollStatus, 1500);
  } catch (error) {
    showProgress(false);
    document.getElementById("notice").textContent = `Error: ${error.message}`;
  }
}

async function pollStatus() {
  try {
    const status = await api("/api/status");
    document.getElementById("progressTitle").textContent = status.status === "failed" ? "Analysis failed" : "Training energy model";
    document.getElementById("progressMessage").textContent = status.error || status.message;
    document.getElementById("progressBar").style.width = `${status.progress}%`;
    if (status.status === "completed") {
      clearInterval(state.polling);
      state.polling = null;
      const results = await api("/api/results");
      renderResults(results);
      setTimeout(() => showProgress(false), 450);
    } else if (status.status === "failed") {
      clearInterval(state.polling);
      state.polling = null;
      setTimeout(() => showProgress(false), 900);
      document.getElementById("notice").textContent = `Error: ${status.error}`;
    }
  } catch (error) {
    document.getElementById("notice").textContent = `Error: ${error.message}`;
  }
}

async function uploadFile(file) {
  const form = new FormData();
  form.append("file", file);
  document.getElementById("notice").textContent = `Uploading ${file.name}…`;
  try {
    const result = await api("/api/upload", { method: "POST", body: form });
    document.getElementById("notice").textContent = `${result.filename} uploaded successfully. Run analysis to continue.`;
  } catch (error) {
    document.getElementById("notice").textContent = `Upload failed: ${error.message}`;
  }
}

function setupActions() {
  document.getElementById("runButton").addEventListener("click", runAnalysis);
  document.getElementById("trainingRunButton").addEventListener("click", runAnalysis);
  document.getElementById("uploadButton").addEventListener("click", () => document.getElementById("fileInput").click());
  document.getElementById("fileInput").addEventListener("change", (event) => {
    if (event.target.files[0]) uploadFile(event.target.files[0]);
  });
  window.addEventListener("resize", () => { clearTimeout(window.__resizeTimer); window.__resizeTimer = setTimeout(drawAll, 120); });
}

async function initialize() {
  setupNavigation();
  setupActions();
  try {
    const status = await api("/api/status");
    if (status.status === "completed") {
      renderResults(await api("/api/results"));
    }
  } catch (_) {}
}

initialize();
