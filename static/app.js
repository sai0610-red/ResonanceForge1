/**
 * ResonanceForge UI — assess, progress, results, downloads.
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const els = {
    question: $("question"),
    industry: $("industry"),
    companySize: $("companySize"),
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
  };

  let lastReport = null;
  let progressTimer = null;

  function setHidden(el, hidden) {
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

  function startProgressAnimation() {
    resetSteps();
    setHidden(els.progressPanel, false);
    let current = 1;
    setStep(current);
    if (progressTimer) clearInterval(progressTimer);
    progressTimer = setInterval(() => {
      current = current >= 4 ? 1 : current + 1;
      setStep(current);
    }, 2800);
  }

  function stopProgressAnimation(success) {
    if (progressTimer) {
      clearInterval(progressTimer);
      progressTimer = null;
    }
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
      .replace(/(&quot;.*?&quot;|&#39;.*?&#39;|&quot;[\s\S]*?&quot;)/g, (m) => m)
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

  function renderReport(report) {
    lastReport = report;
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
    lines.push("", "---", "*Generated by ResonanceForge v1*", "");
    return lines.join("\n");
  }

  async function runAssessment() {
    const question = (els.question.value || "").trim();
    if (!question) {
      showError("Please enter a company situation / question before running the assessment.");
      return;
    }

    hideError();
    setHidden(els.resultsPanel, true);
    setHidden(els.emptyPanel, true);
    els.runBtn.disabled = true;
    startProgressAnimation();

    const body = {
      question: question,
      industry: els.industry.value || null,
      company_size: els.companySize.value || null,
    };

    try {
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
        const msg = typeof detail === "string" ? detail : JSON.stringify(detail);
        stopProgressAnimation(false);
        showError(msg);
        return;
      }

      stopProgressAnimation(true);
      renderReport(data);
    } catch (err) {
      stopProgressAnimation(false);
      if (err && err.name === "AbortError") {
        showError("Assessment timed out. Check your GROQ_API_KEY and network, then try again.");
      } else {
        showError("Network or server error: " + (err && err.message ? err.message : String(err)));
      }
    } finally {
      els.runBtn.disabled = false;
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
})();
