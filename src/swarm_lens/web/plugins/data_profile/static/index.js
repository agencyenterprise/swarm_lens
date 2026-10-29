import { el, api, formatNumber, tip } from "swarm-lens/ui.js";

const prefix = "/plugins/data-profile";
const dimensions = [
  ["actors", "Actors", "Who acted: actions tied to a named or pseudonymous agent"],
  ["time", "Time", "When things happened: real timestamps, not ties or stand-ins"],
  ["conversation", "Conversation", "Who talked to whom: agents messaging in shared channels"],
  ["actions", "Actions", "What agents did: tool calls and their results"],
];
const statusLabels = { present: "Present", partial: "Partial", absent: "Absent" };
const verdictLabels = { supported: "Supported", caution: "Use with caution", unsupported: "Not supported" };
const analysisLabels = { timing: "Timing analysis", "per-agent": "Per-agent comparison",
                         conversation: "Conversation analysis (MAST)", actions: "Action analysis" };
const styles = `
.data-profile { padding: 16px 20px; display: grid; gap: 16px; max-width: 980px; }
.data-profile h3 { margin: 0; font-size: 14px; }
.data-profile .dp-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 10px; }
.data-profile .dp-card { border: 1px solid var(--border); border-radius: var(--radius); padding: 10px 12px;
  background: var(--surface); display: grid; gap: 6px; align-content: start; }
.data-profile .dp-card header { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.data-profile dl { margin: 0; display: grid; grid-template-columns: 1fr auto; gap: 2px 8px; font-size: 12px; }
.data-profile dt { color: var(--text-2); } .data-profile dd { margin: 0; font-family: var(--mono); }
.data-profile [data-tone="present"], .data-profile [data-tone="supported"] { background: var(--accent-soft); color: var(--accent-text); }
.data-profile [data-tone="partial"], .data-profile [data-tone="caution"] { background: var(--warn-soft); color: var(--warn); }
.data-profile [data-tone="absent"], .data-profile [data-tone="unsupported"] { background: var(--danger-soft); color: var(--danger); }
.data-profile .dp-pill { border-radius: 999px; padding: 1px 8px; font-size: 11px; font-weight: 600; white-space: nowrap; }
.data-profile ul { margin: 0; padding: 0; list-style: none; display: grid; gap: 6px; }
.data-profile li { display: grid; grid-template-columns: 210px auto 1fr; gap: 10px; align-items: baseline; font-size: 13px; }
.data-profile .dp-declared { border-left: 3px solid var(--border-strong); padding: 4px 10px; font-size: 13px; }
`;

const label = (key) => key.replace(/_/g, " ");
const value = (name, raw) => name.endsWith("_share") ? `${Math.round(raw * 100)}%` : formatNumber(raw);

function pill(text, tone, hint) {
  const node = el("span", "dp-pill", text);
  node.dataset.tone = tone;
  return hint ? tip(node, hint) : node;
}

export function renderProfile(profile) {
  const root = el("div", "data-profile");
  const intro = el("p", "muted", `Computed from events 1–${formatNumber(profile.cursor ?? profile.events)} of this branch. ` +
    "It describes what the imported history holds, so you can tell which analyses it can support.");
  const grid = el("div", "dp-grid");
  for (const [key, title, hint] of dimensions) {
    const dimension = profile.dimensions[key];
    const card = el("section", "dp-card");
    const header = el("header");
    header.append(tip(el("h3", "", title), hint), pill(statusLabels[dimension.status], dimension.status));
    const facts = el("dl");
    for (const [name, raw] of Object.entries(dimension.evidence)) facts.append(el("dt", "", label(name)), el("dd", "", value(name, raw)));
    card.append(header, el("p", "muted", dimension.note), facts);
    grid.append(card);
  }
  const verdicts = el("ul");
  for (const item of profile.supports) {
    const row = el("li");
    row.append(el("strong", "", analysisLabels[item.analysis] || item.analysis),
               pill(verdictLabels[item.verdict], item.verdict), el("span", "muted", item.reason));
    verdicts.append(row);
  }
  root.append(intro, grid, el("h3", "", "What this supports"), verdicts);
  if (profile.declared) {
    const declared = el("div", "dp-declared");
    const missing = profile.declared.missing?.length ? ` Missing: ${profile.declared.missing.join(", ")}.` : "";
    declared.append(el("strong", "", "The importer declares: "),
                    document.createTextNode(`time is ${profile.declared.time_grade}, agents are ${profile.declared.attribution}.${missing} ${profile.declared.notes || ""}`.trim()));
    root.append(el("h3", "", "Declared by the importer"), declared);
  }
  return root;
}

export function install(host) {
  if (!document.getElementById("data-profile-styles")) {
    const style = document.createElement("style");
    style.id = "data-profile-styles";
    style.textContent = styles;
    document.head.append(style);
  }
  let generation = 0;
  const panel = host.registerView({
    id: "data-profile", title: "Data profile", tip: "What this branch's history can support",
    onShow: async () => {
      const ticket = ++generation;
      const { branch, cursor } = host.context();
      if (!branch) return panel.replaceChildren(el("p", "muted", "Select a run to see its data profile."));
      panel.replaceChildren(el("p", "muted", "Profiling…"));
      try {
        const at = Number.isInteger(cursor) ? `&cursor=${cursor}` : "";
        const profile = await api(`${prefix}/profile?branch_id=${encodeURIComponent(branch.id)}${at}`);
        if (ticket === generation) panel.replaceChildren(renderProfile(profile));
      } catch (error) {
        if (ticket === generation) panel.replaceChildren(el("p", "mast-error", error.message));
      }
    },
    onHide: () => { generation++; },
  });
  host.addAction({ label: "Open data profile", tip: "What this branch's history can support", onClick: () => host.openView("data-profile") });
}
