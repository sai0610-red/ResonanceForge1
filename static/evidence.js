/* Evidence section shared by the main UI and the share page.
 * Renders report.evidence (customer passages shown to agents) with textContent only. */
(function () {
  function render(card, evidence) {
    if (!card) return;
    const body = card.querySelector(".evidence-body");
    if (!evidence) {
      card.classList.add("hidden");
      if (body) body.textContent = "";
      return;
    }
    body.textContent = "";
    const docs = (evidence.documents || []).map((d) => d.label + " = " + d.filename).join(", ");
    const passages = evidence.passages || [];
    const cited = passages.filter((p) => p.cited).length;
    const meta = document.createElement("p");
    meta.className = "muted";
    meta.textContent =
      "Documents: " + (docs || "none") + " · " + passages.length + " passages retrieved, " +
      cited + " cited · unverified citations removed: " + (evidence.citations_dropped || 0);
    body.appendChild(meta);
    if (!passages.length) {
      const p = document.createElement("p");
      p.textContent = "No passages matched this assessment.";
      body.appendChild(p);
    }
    passages.forEach((p) => {
      const item = document.createElement("div");
      item.className = "evidence-item" + (p.cited ? " cited" : "");
      const head = document.createElement("div");
      head.className = "evidence-head";
      const ref = document.createElement("strong");
      ref.textContent = "[" + p.ref + "]";
      head.appendChild(ref);
      head.appendChild(
        document.createTextNode(
          " " + p.document + ", chunk " + p.chunk + " · " +
          (p.cited ? "cited" : "retrieved, not cited") + " · " + (p.used_by || []).join(", ")
        )
      );
      const text = document.createElement("blockquote");
      const t = (p.text || "").replace(/\s+/g, " ").trim();
      text.textContent = t.length > 600 ? t.slice(0, 597) + "..." : t;
      item.appendChild(head);
      item.appendChild(text);
      body.appendChild(item);
    });
    card.classList.remove("hidden");
  }

  function toMarkdown(evidence) {
    if (!evidence) return [];
    const lines = ["## Evidence", ""];
    const docs = (evidence.documents || []).map((d) => d.label + " = " + d.filename).join(", ");
    lines.push("Customer documents: " + (docs || "none"), "");
    (evidence.passages || []).forEach((p) => {
      lines.push("- **[" + p.ref + "]** " + p.document + ", chunk " + p.chunk +
        " (" + (p.cited ? "cited" : "retrieved, not cited") + ")");
      lines.push("  > " + (p.text || "").replace(/\s+/g, " ").trim().slice(0, 400));
    });
    lines.push("");
    return lines;
  }

  window.RFEvidence = { render: render, toMarkdown: toMarkdown };
})();
