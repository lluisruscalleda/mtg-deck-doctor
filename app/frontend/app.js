(() => {
  const form = document.getElementById("deck-form");
  const formError = document.getElementById("form-error");
  const submitBtn = document.getElementById("submit-btn");
  const retryBtn = document.getElementById("retry-btn");
  const progressPanel = document.getElementById("progress-panel");
  const progressStatus = document.getElementById("progress-status");
  const progressBar = document.getElementById("progress-bar");
  const progressLog = document.getElementById("progress-log");
  const resultPanel = document.getElementById("result-panel");
  const errorPanel = document.getElementById("error-panel");
  const errorMessage = document.getElementById("error-message");

  let lastDeckId = null;
  let lastOptions = null;
  let eventSource = null;

  function text(el, value) {
    el.textContent = value == null ? "" : String(value);
  }

  function clearChildren(el) {
    while (el.firstChild) el.removeChild(el.firstChild);
  }

  function showError(message) {
    formError.hidden = !message;
    text(formError, message || "");
  }

  function parseCardList(raw) {
    const lines = raw.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    const cards = [];
    for (const line of lines) {
      const match = line.match(/^(\d+)\s+(.+)$/);
      if (!match) {
        throw new Error(`Invalid card line: "${line}". Use "4 Lightning Bolt".`);
      }
      const quantity = Number(match[1]);
      const name = match[2].trim();
      if (!Number.isInteger(quantity) || quantity < 1) {
        throw new Error(`Invalid quantity in line: "${line}"`);
      }
      if (!name) {
        throw new Error(`Missing card name in line: "${line}"`);
      }
      cards.push({ name, quantity });
    }
    if (!cards.length) {
      throw new Error("Add at least one card.");
    }
    return cards;
  }

  function setProgress(percent, label) {
    progressPanel.hidden = false;
    progressBar.style.width = `${Math.max(0, Math.min(100, percent))}%`;
    text(progressStatus, label);
  }

  function appendLog(message) {
    const li = document.createElement("li");
    li.textContent = message;
    progressLog.appendChild(li);
  }

  function closeSSE() {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
  }

  function renderMetrics(metrics) {
    const grid = document.getElementById("metrics-grid");
    clearChildren(grid);
    if (!metrics) return;

    const items = [
      ["Total cards", metrics.total_cards],
      ["Lands", metrics.land_count],
      ["Nonlands", metrics.nonland_count],
      ["Avg mana value", metrics.average_mana_value ?? "n/a"],
    ];
    for (const [label, value] of items) {
      const div = document.createElement("div");
      div.className = "metric";
      const lab = document.createElement("span");
      lab.className = "label";
      lab.textContent = label;
      const val = document.createElement("span");
      val.className = "value";
      val.textContent = String(value);
      div.append(lab, val);
      grid.appendChild(div);
    }

    if (metrics.mana_curve) {
      const wrap = document.createElement("div");
      wrap.className = "curve";
      wrap.style.gridColumn = "1 / -1";
      const title = document.createElement("span");
      title.className = "label";
      title.textContent = "Mana curve";
      const bars = document.createElement("div");
      bars.className = "curve-bars";
      const entries = Object.entries(metrics.mana_curve);
      const max = Math.max(1, ...entries.map(([, n]) => Number(n) || 0));
      for (const [bucket, count] of entries) {
        const bar = document.createElement("div");
        bar.className = "curve-bar";
        bar.style.height = `${(Number(count) / max) * 100}%`;
        const label = document.createElement("span");
        label.textContent = bucket;
        bar.appendChild(label);
        bars.appendChild(bar);
      }
      wrap.append(title, bars);
      grid.appendChild(wrap);
    }
  }

  function renderList(el, items) {
    clearChildren(el);
    if (!items || !items.length) {
      const li = document.createElement("li");
      li.textContent = "None listed.";
      el.appendChild(li);
      return;
    }
    for (const item of items) {
      const li = document.createElement("li");
      li.textContent = item;
      el.appendChild(li);
    }
  }

  function renderRecommendations(recs) {
    const root = document.getElementById("recommendations");
    clearChildren(root);
    if (!recs || !recs.length) {
      const p = document.createElement("p");
      p.textContent = "No grounded recommendations available.";
      root.appendChild(p);
      return;
    }
    for (const rec of recs) {
      const card = document.createElement("article");
      card.className = "rec";
      const h = document.createElement("h4");
      h.textContent = rec.card_name;
      const meta = document.createElement("div");
      meta.className = "meta";
      const price =
        rec.estimated_price_usd == null ? "price unknown" : `$${rec.estimated_price_usd}`;
      meta.textContent = `${rec.category || "other"} · ${price}`;
      const reason = document.createElement("p");
      reason.textContent = rec.reason || "";
      card.append(h, meta, reason);
      root.appendChild(card);
    }
  }

  function showResult(analysis) {
    resultPanel.hidden = false;
    errorPanel.hidden = true;
    const result = analysis.result || {};
    text(document.getElementById("result-summary"), result.summary || "");
    renderMetrics(analysis.metrics);
    renderList(document.getElementById("strengths-list"), result.strengths);
    renderList(document.getElementById("weaknesses-list"), result.weaknesses);
    renderRecommendations(result.recommendations);
    renderList(
      document.getElementById("warnings-list"),
      result.warnings || analysis.warnings || []
    );
    setProgress(100, "Completed");
    retryBtn.hidden = false;
  }

  function showFailed(message) {
    resultPanel.hidden = true;
    errorPanel.hidden = false;
    text(errorMessage, message || "Analysis failed.");
    setProgress(100, "Failed");
    retryBtn.hidden = false;
  }

  async function fetchAnalysis(analysisId) {
    const response = await fetch(`/api/v1/analyses/${analysisId}`);
    if (!response.ok) {
      throw new Error("Could not load analysis result.");
    }
    return response.json();
  }

  function subscribe(analysisId) {
    closeSSE();
    clearChildren(progressLog);
    setProgress(0, "Queued");
    appendLog("Subscribed to analysis events");

    eventSource = new EventSource(`/api/v1/analyses/${analysisId}/events`);

    eventSource.addEventListener("queued", (ev) => {
      appendLog(`queued: ${ev.data}`);
      setProgress(5, "Queued");
    });

    eventSource.addEventListener("progress", (ev) => {
      let payload = {};
      try {
        payload = JSON.parse(ev.data);
      } catch {
        payload = {};
      }
      const percent = Number(payload.percent) || 0;
      const step = payload.step || "progress";
      appendLog(`${step} (${percent}%)`);
      setProgress(percent, `Running: ${step}`);
    });

    eventSource.addEventListener("completed", async () => {
      appendLog("completed");
      closeSSE();
      try {
        const analysis = await fetchAnalysis(analysisId);
        showResult(analysis);
      } catch (err) {
        showFailed(err.message);
      } finally {
        submitBtn.disabled = false;
      }
    });

    eventSource.addEventListener("failed", async (ev) => {
      appendLog(`failed: ${ev.data}`);
      closeSSE();
      try {
        const analysis = await fetchAnalysis(analysisId);
        showFailed(analysis.error_message || "Analysis failed.");
      } catch {
        showFailed("Analysis failed.");
      } finally {
        submitBtn.disabled = false;
      }
    });

    eventSource.onerror = () => {
      // Browser will retry; if the stream ended after terminal event, close quietly.
      if (eventSource && eventSource.readyState === EventSource.CLOSED) {
        submitBtn.disabled = false;
      }
    };
  }

  async function createDeckAndAnalyze(payload) {
    showError("");
    resultPanel.hidden = true;
    errorPanel.hidden = true;
    progressPanel.hidden = false;
    submitBtn.disabled = true;
    retryBtn.hidden = true;

    const deckRes = await fetch("/api/v1/decks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: payload.name,
        format: payload.format,
        cards: payload.cards,
      }),
    });
    const deckBody = await deckRes.json().catch(() => ({}));
    if (!deckRes.ok) {
      const detail = deckBody.detail || "Could not create deck.";
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }

    lastDeckId = deckBody.id;
    lastOptions = {
      budget_usd: payload.budget_usd,
      recommendation_count: payload.recommendation_count,
    };

    if (deckBody.warnings && deckBody.warnings.length) {
      appendLog(`Deck warnings: ${deckBody.warnings.join("; ")}`);
    }

    const analysisRes = await fetch(`/api/v1/decks/${lastDeckId}/analyses`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(lastOptions),
    });
    const analysisBody = await analysisRes.json().catch(() => ({}));
    if (!analysisRes.ok) {
      const detail = analysisBody.detail || "Could not start analysis.";
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }

    subscribe(analysisBody.id);
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const cards = parseCardList(document.getElementById("card-list").value);
      const payload = {
        name: document.getElementById("deck-name").value.trim(),
        format: document.getElementById("deck-format").value,
        cards,
        budget_usd: Number(document.getElementById("budget").value),
        recommendation_count: Number(document.getElementById("rec-count").value),
      };
      if (!payload.name) throw new Error("Deck name is required.");
      await createDeckAndAnalyze(payload);
    } catch (err) {
      showError(err.message || "Request failed.");
      submitBtn.disabled = false;
    }
  });

  retryBtn.addEventListener("click", async () => {
    if (!lastDeckId || !lastOptions) return;
    showError("");
    resultPanel.hidden = true;
    errorPanel.hidden = true;
    submitBtn.disabled = true;
    try {
      const analysisRes = await fetch(`/api/v1/decks/${lastDeckId}/analyses`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(lastOptions),
      });
      const analysisBody = await analysisRes.json().catch(() => ({}));
      if (!analysisRes.ok) {
        throw new Error(analysisBody.detail || "Retry failed.");
      }
      clearChildren(progressLog);
      subscribe(analysisBody.id);
    } catch (err) {
      showError(err.message || "Retry failed.");
      submitBtn.disabled = false;
    }
  });
})();
