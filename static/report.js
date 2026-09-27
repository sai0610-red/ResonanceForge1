/**
 * ResonanceForge share page — read-only report for /r/{id}.
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const els = {
    errorPanel: $("errorPanel"),
    errorMessage: $("errorMessage"),
    loadingPanel: $("loadingPanel"),
    resultsPanel: $("resultsPanel"),
    companyTitle: $("companyTitle"),
    reportMeta: $("reportMeta"),
    situationBox: $("situationBox"),
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
    scaffoldBadge: $("scaffoldBadge"),
    scaffoldDetail: $("scaffoldDetail"),
    pilotBtn: $("downloadPilotBtn"),
    pilotMsg: $("pilotMsg"),
  };

  const TOKEN_KEY = "rf_demo_token";
  let currentId = null;

  function getToken() {
    try {
      return (localStorage.getItem(TOKEN_KEY) || "").trim();
    } catch (_) {
      return "";
    }
  }

  let lastCode = "";

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

  function metaItem(label, value) {
    if (!value) return null;
    const span = document.createElement("span");
    const strong = document.createElement("strong");
    strong.textContent = label + ": ";
    span.appendChild(strong);
    span.appendChild(document.createTextNode(value));
    return span;
  }


  function fillList(ul, items) {
    if (!ul) return;
    while (ul.firstChild) ul.removeChild(ul.firstChild);
    (items || []).forEach((text) => {
      const li = document.createElement("li");
      li.textContent = text;
      ul.appendChild(li);
    });
  }

  function renderLeadershipBrief(report, onePager, assessmentId) {
    const brief = document.getElementById("leadershipBrief");
    if (!brief) return;
    const d = report.diagnosis;
    const c = report.critique;
    const op = onePager || {};
    const go = document.getElementById("briefGoNoGo");
    if (go) {
      go.textContent = op.go_no_go || c.final_verdict || "—";
      go.className = "badge " + verdictClass(op.go_no_go || c.final_verdict);
    }
    const verdict = document.getElementById("briefVerdict");
    if (verdict) verdict.textContent = op.executive_verdict || ((c.final_verdict || "") + " · " + (d.overall_readiness || ""));
    const summary = document.getElementById("briefSummary");
    if (summary) summary.textContent = op.summary || d.summary || "";
    const cost = document.getElementById("briefCost");
    if (cost) cost.textContent = op.cost_band || "—";
    fillList(document.getElementById("briefPlan"), op.ninety_day_plan || []);
    const breaks = (report.pilot && report.pilot.what_breaks_first) || op.top_gaps || d.top_gaps || [];
    fillList(document.getElementById("briefBreaks"), breaks.slice(0, 6));
    if (assessmentId) currentId = assessmentId;
  }

  function renderScaffoldCheck(sc) {
    if (!els.scaffoldBadge) return;
    if (!sc) {
      setHidden(els.scaffoldBadge, true);
      setHidden(els.scaffoldDetail, true);
      return;
    }
    els.scaffoldBadge.textContent = sc.ok ? "Compile check: PASS" : "Compile check: FAIL";
    els.scaffoldBadge.className = "badge scaffold-badge " + (sc.ok ? "pass" : "fail");
    els.scaffoldBadge.title = sc.error || "ast.parse + compile() succeeded (not executed)";
    const parts = [
      (sc.lines || 0) + " lines",
      "StateGraph " + (sc.has_stategraph ? "found" : "missing"),
      ".compile() " + (sc.has_compile ? "found" : "missing"),
    ];
    if (sc.error) parts.push(sc.error);
    els.scaffoldDetail.textContent = "Static check only (parsed and compiled, not executed): " + parts.join(" · ");
    setHidden(els.scaffoldBadge, false);
    setHidden(els.scaffoldDetail, false);
  }

  function showPilotMsg(msg) {
    if (!els.pilotMsg) return;
    els.pilotMsg.textContent = msg || "";
    setHidden(els.pilotMsg, !msg);
  }

  async function downloadPilot() {
    if (!currentId) return;
    showPilotMsg("");
    const headers = {};
    const token = getToken();
    if (token) headers["X-Demo-Token"] = token;
    try {
      // fetch + blob so X-Demo-Token is sent (a plain link would drop the header).
      const res = await fetch(
        "/api/assessments/" + encodeURIComponent(currentId) + "/pilot.zip",
        { headers: headers }
      );
      if (res.status === 401) {
        showPilotMsg("The pilot download needs the demo token. Open the main app, paste the token in 'Demo token', then retry here.");
        return;
      }
      if (res.status === 429) {
        showPilotMsg("Rate limit reached. Try again later.");
        return;
      }
      if (!res.ok) {
        showPilotMsg("Pilot download failed (status " + res.status + ").");
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "resonanceforge-pilot-" + currentId + ".zip";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      showPilotMsg("Pilot download failed: " + (err && err.message ? err.message : String(err)));
    }
  }

  function render(payload) {
    const report = payload.report;
    const d = report.diagnosis;
    const a = report.architecture;
    const g = report.generated_code;
    const c = report.critique;

    els.companyTitle.textContent =
      payload.company_name || payload.industry || "AI readiness assessment";

    clearList(els.reportMeta);
    // reportMeta is a div, not ul — use append
    els.reportMeta.innerHTML = "";
    [
      metaItem("Industry", payload.industry),
      metaItem("Size", payload.company_size),
      metaItem("Role", payload.role_title),
      metaItem("Systems", payload.primary_systems),
      metaItem("Constraints", payload.constraints),
      metaItem("Success metric", payload.success_metric),
      metaItem(
        "Date",
        payload.created_at
          ? new Date(payload.created_at).toLocaleString()
          : null
      ),
    ].forEach((node) => {
      if (node) els.reportMeta.appendChild(node);
    });

    els.situationBox.textContent = payload.question || report.user_question || "";

    els.overallBadge.textContent = d.overall_readiness;
    els.overallBadge.className = "badge " + readinessClass(d.overall_readiness);

    els.verdictBadge.textContent = c.final_verdict;
    els.verdictBadge.className = "badge " + verdictClass(c.final_verdict);

    els.scoreGrid.innerHTML = "";
    [
      { key: "access", label: "ACCESS" },
      { key: "adapt", label: "ADAPT" },
      { key: "adopt", label: "ADOPT" },
    ].forEach(({ key, label }) => {
      const item = d[key];
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

    els.diagSummary.textContent = d.summary;
    fillList(els.topGaps, d.top_gaps);

    els.complexityBadge.textContent = a.estimated_complexity;
    els.complexityBadge.className =
      "badge badge-muted " + readinessClass(a.estimated_complexity);
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
    lastCode = g.code || "";
    els.codeBlock.innerHTML = simpleHighlight(lastCode);
    renderScaffoldCheck(report.scaffold_check);

    fillList(els.strengthsList, c.strengths);
    fillList(els.weaknessesList, c.weaknesses);
    fillList(els.risksList, c.risks);
    fillList(els.recsList, c.recommendations);

    renderLeadershipBrief(report, payload.one_pager, payload.id);

    document.title =
      (payload.company_name ? payload.company_name + " — " : "") +
      "ResonanceForge Report";
  }

  function assessmentIdFromPath() {
    const parts = window.location.pathname.split("/").filter(Boolean);
    // /r/{id}
    const idx = parts.indexOf("r");
    if (idx >= 0 && parts[idx + 1]) return parts[idx + 1];
    return parts[parts.length - 1] || null;
  }

  async function load() {
    setHidden(els.loadingPanel, false);
    setHidden(els.errorPanel, true);
    setHidden(els.resultsPanel, true);

    const id = assessmentIdFromPath();
    if (!id) {
      setHidden(els.loadingPanel, true);
      els.errorMessage.textContent = "Missing assessment id in URL.";
      setHidden(els.errorPanel, false);
      return;
    }

    try {
      const res = await fetch("/api/reports/" + encodeURIComponent(id));
      if (!res.ok) {
        let detail = "Report not found or not completed.";
        try {
          const j = await res.json();
          if (j && j.detail) detail = j.detail;
        } catch (_) {}
        throw new Error(detail);
      }
      const data = await res.json();
      render(data);
      setHidden(els.loadingPanel, true);
      setHidden(els.resultsPanel, false);
    } catch (err) {
      setHidden(els.loadingPanel, true);
      els.errorMessage.textContent =
        err && err.message ? err.message : String(err);
      setHidden(els.errorPanel, false);
    }
  }

  if (els.pilotBtn) els.pilotBtn.addEventListener("click", downloadPilot);

  els.copyCodeBtn.addEventListener("click", async () => {
    if (!lastCode) return;
    try {
      await navigator.clipboard.writeText(lastCode);
      els.copyCodeBtn.textContent = "Copied!";
      setTimeout(() => {
        els.copyCodeBtn.textContent = "Copy code";
      }, 1500);
    } catch (_) {
      els.errorMessage.textContent = "Could not copy to clipboard.";
      setHidden(els.errorPanel, false);
    }
  });

  load();
})();
