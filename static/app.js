/**
 * ResonanceForge UI — SSE stream, history, share links, results.
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const els = {
    question: $("question"),
    industry: $("industry"),
    companySize: $("companySize"),
    companyName: $("companyName"),
    roleTitle: $("roleTitle"),
    primarySystems: $("primarySystems"),
    constraints: $("constraints"),
    successMetric: $("successMetric"),
    runBtn: $("runBtn"),
    progressPanel: $("progressPanel"),
    stepsList: $("stepsList"),
    errorPanel: $("errorPanel"),
    errorMessage: $("errorMessage"),
    emptyPanel: $("emptyPanel"),
    resultsPanel: $("resultsPanel"),
    overallBadge: $("overallBadge"),
    scoreGrid: $("scoreGrid"),
    diagSummary: $("diagSummary"),
    topGaps: $("topGaps"),
    complexityBadge: $("complexityBadge"),
    agentList: $("agentList"),
    flowList: $("flowList"),
    archRationale: $("archRationale"),
    codeExplanation: $("codeExplanation"),
    codeBlock: $("codeBlock"),
    copyCodeBtn: $("copyCodeBtn"),
    verdictBadge: $("verdictBadge"),
    strengthsList: $("strengthsList"),
    weaknessesList: $("weaknessesList"),
    risksList: $("risksList"),
    recsList: $("recsList"),
    downloadJsonBtn: $("downloadJsonBtn"),
    downloadMdBtn: $("downloadMdBtn"),
    downloadPilotBtn: $("downloadPilotBtn"),
    shareLinkBtn: $("shareLinkBtn"),
    shareHint: $("shareHint"),
    historyList: $("historyList"),
    historyEmpty: $("historyEmpty"),
    checklistRoot: $("checklistRoot"),
    checklistProgress: $("checklistProgress"),
    leadershipBrief: $("leadershipBrief"),
    briefGoNoGo: $("briefGoNoGo"),
    briefVerdict: $("briefVerdict"),
    briefSummary: $("briefSummary"),
    briefCost: $("briefCost"),
    briefPlan: $("briefPlan"),
    briefBreaks: $("briefBreaks"),
  };

  let lastReport = null;
  let lastAssessmentId = null;
  let checklistQuestions = [];
  let checklistAnswers = {}; // id -> 1..5
  let lastOnePager = null;

  function setHidden(el, hidden) {
    if (!el) return;
    el.classList.toggle("hidden", hidden);
  }

  function clearList(ul) {
    while (ul.firstChild) ul.removeChild(ul.firstChild);
  }

  function fillList(ul, items) {
    clearList(ul);
    (items || []).forEach((text) => {
      const li = document.createElement("li");
      li.textContent = text;
      ul.appendChild(li);
    });
  }

  function readinessClass(level) {
    const v = String(level || "").toLowerCase();
    if (v === "low") return "low";
    if (v === "medium") return "medium";
    if (v === "high") return "high";
    return "";
  }

  function verdictClass(verdict) {
    const v = String(verdict || "").toLowerCase();
    if (v.includes("ready for pilot")) return "ready";
    if (v.includes("needs work")) return "needs";
    if (v.includes("not ready")) return "notready";
    return "";
  }

  function resetSteps() {
    els.stepsList.querySelectorAll(".step").forEach((s) => {
      s.classList.remove("active", "done");
    });
  }

  function setStep(n) {
    els.stepsList.querySelectorAll(".step").forEach((s) => {
      const step = Number(s.dataset.step);
      s.classList.remove("active");
      if (step < n) {
        s.classList.add("done");
      } else if (step === n) {
        s.classList.add("active");
        s.classList.remove("done");
      } else {
        s.classList.remove("done");
      }
    });
  }

  function markAllStepsDone() {
    els.stepsList.querySelectorAll(".step").forEach((s) => {
      s.classList.remove("active");
      s.classList.add("done");
    });
  }

  function showProgress() {
    resetSteps();
    setHidden(els.progressPanel, false);
  }

  function hideProgress(success) {
    if (success) {
      markAllStepsDone();
    } else {
      setHidden(els.progressPanel, true);
      resetSteps();
    }
  }

  function showError(msg) {
    els.errorMessage.textContent = msg;
    setHidden(els.errorPanel, false);
    setHidden(els.emptyPanel, true);
    setHidden(els.resultsPanel, true);
  }

  function hideError() {
    setHidden(els.errorPanel, true);
    els.errorMessage.textContent = "";
  }

  function simpleHighlight(code) {
    const escaped = code
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    return escaped
      .replace(
        /\b(from|import|def|class|return|if|elif|else|for|while|with|as|try|except|raise|True|False|None|and|or|not|in|is|lambda|yield|async|await|pass|break|continue)\b/g,
        '<span style="color:#7dd3fc">$1</span>'
      )
      .replace(/(#[^\n]*)/g, '<span style="color:#6b7280">$1</span>')
      .replace(/("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')/g, '<span style="color:#86efac">$1</span>')
      .replace(/\b(\d+)\b/g, '<span style="color:#fcd34d">$1</span>');
  }

  function renderScores(diagnosis) {
    const dims = [
      { key: "access", label: "ACCESS" },
      { key: "adapt", label: "ADAPT" },
      { key: "adopt", label: "ADOPT" },
    ];
    els.scoreGrid.innerHTML = "";
    dims.forEach(({ key, label }) => {
      const item = diagnosis[key];
      const card = document.createElement("div");
      card.className = "score-card";
      card.innerHTML =
        '<div class="label">' +
        label +
        '</div><div class="score">' +
        item.score +
        '/10</div><p class="reason"></p>';
      card.querySelector(".reason").textContent = item.reason;
      els.scoreGrid.appendChild(card);
    });
  }

  function setShareHint(id) {
    lastAssessmentId = id || null;
    if (!id) {
      setHidden(els.shareHint, true);
      els.shareHint.textContent = "";
      return;
    }
    const url = window.location.origin + "/r/" + id;
    els.shareHint.textContent = "Share link: " + url;
    setHidden(els.shareHint, false);
  }

  function renderReport(report, assessmentId) {
    lastReport = report;
    if (assessmentId) setShareHint(assessmentId);

    const d = report.diagnosis;
    const a = report.architecture;
    const g = report.generated_code;
    const c = report.critique;

    els.overallBadge.textContent = d.overall_readiness;
    els.overallBadge.className = "badge " + readinessClass(d.overall_readiness);
    renderScores(d);
    els.diagSummary.textContent = d.summary;
    fillList(els.topGaps, d.top_gaps);

    els.complexityBadge.textContent = a.estimated_complexity;
    els.complexityBadge.className = "badge badge-muted " + readinessClass(a.estimated_complexity);
    clearList(els.agentList);
    (a.recommended_agents || []).forEach((agent) => {
      const li = document.createElement("li");
      const strong = document.createElement("strong");
      strong.textContent = agent.name;
      li.appendChild(strong);
      li.appendChild(document.createTextNode(" — " + agent.responsibility));
      els.agentList.appendChild(li);
    });
    fillList(els.flowList, a.high_level_flow);
    els.archRationale.textContent = a.rationale;

    els.codeExplanation.textContent = g.explanation;
    els.codeBlock.innerHTML = simpleHighlight(g.code || "");

    els.verdictBadge.textContent = c.final_verdict;
    els.verdictBadge.className = "badge " + verdictClass(c.final_verdict);
    fillList(els.strengthsList, c.strengths);
    fillList(els.weaknessesList, c.weaknesses);
    fillList(els.risksList, c.risks);
    fillList(els.recsList, c.recommendations);

    setHidden(els.emptyPanel, true);
    setHidden(els.resultsPanel, false);
    setHidden(els.errorPanel, true);
  }

  function downloadBlob(filename, content, mime) {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function toMarkdown(report) {
    const d = report.diagnosis;
    const a = report.architecture;
    const g = report.generated_code;
    const c = report.critique;
    const lines = [];
    lines.push("# ResonanceForge Assessment Report", "", "## Question", "", report.user_question, "");
    lines.push("## Diagnosis (ACCESS / ADAPT / ADOPT)", "");
    lines.push("**Overall readiness:** " + d.overall_readiness, "");
    lines.push("| Dimension | Score | Reason |", "|-----------|------:|--------|");
    lines.push("| ACCESS | " + d.access.score + "/10 | " + d.access.reason + " |");
    lines.push("| ADAPT | " + d.adapt.score + "/10 | " + d.adapt.reason + " |");
    lines.push("| ADOPT | " + d.adopt.score + "/10 | " + d.adopt.reason + " |", "");
    lines.push("### Top gaps", "");
    d.top_gaps.forEach((g0) => lines.push("- " + g0));
    lines.push("", "### Summary", "", d.summary, "");
    lines.push("## Architecture", "", "**Estimated complexity:** " + a.estimated_complexity, "");
    lines.push("### Recommended agents", "");
    a.recommended_agents.forEach((ag) => lines.push("- **" + ag.name + "** — " + ag.responsibility));
    lines.push("", "### High-level flow", "");
    a.high_level_flow.forEach((s, i) => lines.push(i + 1 + ". " + s));
    lines.push("", "### Rationale", "", a.rationale, "");
    lines.push("## Generated LangGraph Code", "", g.explanation, "", "```python", g.code, "```", "");
    lines.push("## Critique", "", "**Final verdict:** " + c.final_verdict, "");
    lines.push("### Strengths", "");
    c.strengths.forEach((x) => lines.push("- " + x));
    lines.push("", "### Weaknesses", "");
    c.weaknesses.forEach((x) => lines.push("- " + x));
    lines.push("", "### Risks", "");
    c.risks.forEach((x) => lines.push("- " + x));
    lines.push("", "### Recommendations", "");
    c.recommendations.forEach((x) => lines.push("- " + x));
    lines.push("", "---", "*Generated by ResonanceForge*", "");
    return lines.join("\n");
  }


  function updateChecklistProgress() {
    const total = checklistQuestions.length || 15;
    const answered = Object.keys(checklistAnswers).length;
    if (els.checklistProgress) {
      els.checklistProgress.textContent = answered + " / " + total + " answered";
    }
    const complete = answered >= total && total > 0;
    if (els.runBtn) els.runBtn.disabled = !complete;
    return complete;
  }

  function renderChecklist(questions) {
    checklistQuestions = questions || [];
    const root = els.checklistRoot;
    if (!root) return;
    root.innerHTML = "";
    const dims = [
      { key: "access", label: "ACCESS" },
      { key: "adapt", label: "ADAPT" },
      { key: "adopt", label: "ADOPT" },
    ];
    dims.forEach((dim, idx) => {
      const items = checklistQuestions.filter((q) => q.dimension === dim.key);
      const details = document.createElement("details");
      details.className = "checklist-dim";
      details.open = idx === 0;
      const summary = document.createElement("summary");
      summary.innerHTML = dim.label + ' <span class="dim-count" data-dim="' + dim.key + '">0/' + items.length + '</span>';
      details.appendChild(summary);
      const body = document.createElement("div");
      body.className = "checklist-dim-body";
      items.forEach((q) => {
        const wrap = document.createElement("div");
        wrap.className = "checklist-q";
        wrap.dataset.qid = q.id;
        const prompt = document.createElement("p");
        prompt.className = "checklist-q-prompt";
        prompt.textContent = q.prompt;
        wrap.appendChild(prompt);
        const opts = document.createElement("div");
        opts.className = "checklist-options";
        (q.options || []).forEach((opt) => {
          const label = document.createElement("label");
          label.className = "checklist-opt";
          const input = document.createElement("input");
          input.type = "radio";
          input.name = "cq_" + q.id;
          input.value = String(opt.value);
          if (checklistAnswers[q.id] === opt.value) input.checked = true;
          input.addEventListener("change", () => {
            checklistAnswers[q.id] = Number(opt.value);
            // update dim count
            const dimItems = checklistQuestions.filter((x) => x.dimension === dim.key);
            const n = dimItems.filter((x) => checklistAnswers[x.id] != null).length;
            const badge = details.querySelector('.dim-count[data-dim="' + dim.key + '"]');
            if (badge) badge.textContent = n + "/" + dimItems.length;
            updateChecklistProgress();
          });
          const span = document.createElement("span");
          span.textContent = opt.value + " — " + opt.label;
          label.appendChild(input);
          label.appendChild(span);
          opts.appendChild(label);
        });
        wrap.appendChild(opts);
        body.appendChild(wrap);
      });
      details.appendChild(body);
      root.appendChild(details);
    });
    updateChecklistProgress();
  }

  async function loadChecklist() {
    try {
      const res = await fetch("/api/checklist");
      if (!res.ok) throw new Error("checklist " + res.status);
      const data = await res.json();
      renderChecklist(data.questions || data || []);
    } catch (err) {
      console.warn("Failed to load checklist", err);
      if (els.checklistRoot) {
        els.checklistRoot.textContent = "Could not load checklist. Refresh the page.";
      }
    }
  }

  function collectChecklist() {
    return Object.keys(checklistAnswers).map((qid) => ({
      question_id: qid,
      value: checklistAnswers[qid],
    }));
  }

  function renderLeadershipBrief(report, onePager) {
    if (!els.leadershipBrief) return;
    const d = report.diagnosis;
    const c = report.critique;
    const op = onePager || {};
    els.briefGoNoGo.textContent = op.go_no_go || c.final_verdict || "—";
    els.briefGoNoGo.className = "badge " + verdictClass(op.go_no_go || c.final_verdict);
    els.briefVerdict.textContent = op.executive_verdict || (c.final_verdict + " · " + d.overall_readiness);
    els.briefSummary.textContent = op.summary || d.summary || "";
    els.briefCost.textContent = op.cost_band || "—";
    fillList(els.briefPlan, op.ninety_day_plan || []);
    const breaks = (report.pilot && report.pilot.what_breaks_first) || op.top_gaps || d.top_gaps || [];
    fillList(els.briefBreaks, breaks.slice(0, 6));
  }


    function collectBody() {
    return {
      question: (els.question.value || "").trim(),
      industry: els.industry.value || null,
      company_size: els.companySize.value || null,
      company_name: (els.companyName.value || "").trim() || null,
      role_title: (els.roleTitle.value || "").trim() || null,
      primary_systems: (els.primarySystems.value || "").trim() || null,
      constraints: (els.constraints.value || "").trim() || null,
      success_metric: (els.successMetric.value || "").trim() || null,
      checklist: collectChecklist(),
    };
  }

  function parseSSEChunk(buffer) {
    const events = [];
    const parts = buffer.split("\n\n");
    const rest = parts.pop() || "";
    parts.forEach((block) => {
      if (!block.trim()) return;
      let event = "message";
      const dataLines = [];
      block.split("\n").forEach((line) => {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      });
      if (!dataLines.length) return;
      try {
        events.push({ event: event, data: JSON.parse(dataLines.join("\n")) });
      } catch (_) {
        /* ignore malformed */
      }
    });
    return { events: events, rest: rest };
  }

  async function runViaStream(body) {
    const res = await fetch("/api/assessments/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(body),
    });
    if (!res.ok || !res.body) {
      const errText = await res.text().catch(() => "");
      throw new Error("stream_http_" + res.status + (errText ? ": " + errText : ""));
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let completed = null;
    let failed = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parsed = parseSSEChunk(buffer);
      buffer = parsed.rest;
      for (const ev of parsed.events) {
        if (ev.event === "step" && ev.data && ev.data.step) {
          setStep(Number(ev.data.step));
          if (ev.data.id) lastAssessmentId = ev.data.id;
        } else if (ev.event === "complete") {
          completed = ev.data;
          if (ev.data && ev.data.one_pager) lastOnePager = ev.data.one_pager;
        } else if (ev.event === "error") {
          failed = (ev.data && ev.data.detail) || "Assessment failed";
        }
      }
    }

    if (failed) throw new Error(failed);
    if (!completed || !completed.report) throw new Error("Stream ended without a complete report");
    return completed;
  }

  async function runViaSync(body) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 180000);
    const res = await fetch("/assess", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    clearTimeout(timeout);

    let data = null;
    try {
      data = await res.json();
    } catch (_) {
      data = null;
    }

    if (!res.ok) {
      const detail =
        (data && (data.detail || data.message)) ||
        "Request failed with status " + res.status;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }

    const id = res.headers.get("X-Assessment-Id");
    return { id: id, report: data };
  }

  async function runAssessment() {
    const body = collectBody();
    if (!body.question) {
      showError("Please enter a company situation / question before running the assessment.");
      return;
    }
    if (!updateChecklistProgress()) {
      showError("Please answer all 15 checklist questions before running the assessment.");
      return;
    }

    hideError();
    setHidden(els.resultsPanel, true);
    setHidden(els.emptyPanel, true);
    setShareHint(null);
    lastOnePager = null;
    els.runBtn.disabled = true;
    showProgress();
    setStep(1);

    try {
      let result;
      try {
        result = await runViaStream(body);
      } catch (streamErr) {
        // Fallback to sync POST /assess
        console.warn("SSE stream failed, falling back to /assess", streamErr);
        resetSteps();
        setStep(1);
        result = await runViaSync(body);
        markAllStepsDone();
      }

      hideProgress(true);
      renderReport(result.report, result.id);
      await loadHistory();
      highlightHistory(result.id);
    } catch (err) {
      hideProgress(false);
      if (err && err.name === "AbortError") {
        showError("Assessment timed out. Check your GROQ_API_KEY and network, then try again.");
      } else {
        showError("Network or server error: " + (err && err.message ? err.message : String(err)));
      }
    } finally {
      els.runBtn.disabled = false;
    }
  }

  function formatWhen(iso) {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      return d.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch (_) {
      return iso;
    }
  }

  function highlightHistory(id) {
    els.historyList.querySelectorAll(".history-item").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.id === id);
    });
  }

  async function loadHistory() {
    try {
      const res = await fetch("/api/assessments?limit=50");
      if (!res.ok) throw new Error("history " + res.status);
      const items = await res.json();
      clearList(els.historyList);
      if (!items.length) {
        setHidden(els.historyEmpty, false);
        return;
      }
      setHidden(els.historyEmpty, true);
      items.forEach((item) => {
        const li = document.createElement("li");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "history-item";
        btn.dataset.id = item.id;

        const title = document.createElement("div");
        title.className = "hi-title";
        title.textContent = item.company_name || item.industry || "Assessment";

        const meta = document.createElement("div");
        meta.className = "hi-meta";
        const status = document.createElement("span");
        status.className = "badge " + (item.status || "");
        status.textContent = item.status || "—";
        meta.appendChild(status);
        if (item.overall_readiness) {
          const ready = document.createElement("span");
          ready.className = "badge " + readinessClass(item.overall_readiness);
          ready.textContent = item.overall_readiness;
          meta.appendChild(ready);
        }
        const when = document.createElement("span");
        when.textContent = formatWhen(item.created_at);
        meta.appendChild(when);

        const preview = document.createElement("p");
        preview.className = "hi-preview";
        preview.textContent = item.question_preview || "";

        btn.appendChild(title);
        btn.appendChild(meta);
        btn.appendChild(preview);
        btn.addEventListener("click", () => openAssessment(item.id));
        li.appendChild(btn);
        els.historyList.appendChild(li);
      });
    } catch (err) {
      console.warn("Failed to load history", err);
      setHidden(els.historyEmpty, false);
      els.historyEmpty.textContent = "Could not load history.";
    }
  }

  async function openAssessment(id) {
    hideError();
    try {
      const res = await fetch("/api/assessments/" + encodeURIComponent(id));
      if (!res.ok) throw new Error("Failed to load assessment");
      const data = await res.json();
      highlightHistory(id);
      if (data.status === "completed" && data.report) {
        hideProgress(true);
        renderReport(data.report, data.id);
      } else if (data.status === "failed") {
        showError(data.error || "Assessment failed");
      } else {
        showError("Assessment is still " + (data.status || "in progress"));
      }
    } catch (err) {
      showError(err && err.message ? err.message : String(err));
    }
  }

  els.runBtn.addEventListener("click", runAssessment);

  els.copyCodeBtn.addEventListener("click", async () => {
    if (!lastReport) return;
    const code = lastReport.generated_code.code || "";
    try {
      await navigator.clipboard.writeText(code);
      els.copyCodeBtn.textContent = "Copied!";
      setTimeout(() => {
        els.copyCodeBtn.textContent = "Copy code";
      }, 1500);
    } catch (_) {
      showError("Could not copy to clipboard.");
    }
  });

  els.shareLinkBtn.addEventListener("click", async () => {
    if (!lastAssessmentId) {
      showError("No shareable assessment id yet. Run an assessment first.");
      return;
    }
    const url = window.location.origin + "/r/" + lastAssessmentId;
    try {
      await navigator.clipboard.writeText(url);
      els.shareLinkBtn.textContent = "Copied!";
      setShareHint(lastAssessmentId);
      setTimeout(() => {
        els.shareLinkBtn.textContent = "Share link";
      }, 1500);
    } catch (_) {
      setShareHint(lastAssessmentId);
      showError("Could not copy share link. URL shown below results.");
    }
  });

  els.downloadJsonBtn.addEventListener("click", () => {
    if (!lastReport) return;
    downloadBlob(
      "resonanceforge-report.json",
      JSON.stringify(lastReport, null, 2),
      "application/json"
    );
  });

  els.downloadMdBtn.addEventListener("click", () => {
    if (!lastReport) return;
    downloadBlob(
      "resonanceforge-report.md",
      toMarkdown(lastReport),
      "text/markdown"
    );
  });

  if (els.downloadPilotBtn) {
    els.downloadPilotBtn.addEventListener("click", () => {
      if (!lastAssessmentId) {
        showError("No assessment id for pilot download. Run an assessment first.");
        return;
      }
      window.location.href = "/api/assessments/" + encodeURIComponent(lastAssessmentId) + "/pilot.zip";
    });
  }

  loadChecklist();
  loadHistory();
})();
