/* SILICONPILOT: buildless, offline-capable recorded experiment viewer. */
"use strict";
const $ = (id) => document.getElementById(id);
const ns = "http://www.w3.org/2000/svg";
const state = {
  data: null,
  candidates: [],
  selected: null,
  model: "all",
  axis: "latency_us",
  hdl: "",
  wave: null,
  frame: 0,
  playing: false,
  timer: null,
  selectionToken: 0,
};
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const number = (value, digits = 1) =>
  Number.isFinite(Number(value)) && value !== null && value !== ""
    ? Number(value).toLocaleString("en-US", { maximumFractionDigits: digits })
    : "—";
const accuracy = (value) =>
  value == null
    ? null
    : Number(value) > 1
      ? Number(value) / 100
      : Number(value);
const pct = (value) =>
  value == null ? "—" : `${number(accuracy(value) * 100, 1)}%`;
const safeUrl = (value) => {
  if (!value || typeof value !== "string") return null;
  try {
    const u = new URL(value, location.href);
    return ["http:", "https:"].includes(u.protocol) ? u.href : null;
  } catch {
    return null;
  }
};
const metric = (label, value, unit = "") =>
  `<div><span>${esc(label)}</span><strong>${esc(value)}${unit ? `<small>${esc(unit)}</small>` : ""}</strong></div>`;
const empty = (title, body) =>
  `<div class="empty-state"><div><strong>${esc(title)}</strong>${esc(body)}</div></div>`;
function el(name, attrs = {}, content) {
  const n = document.createElementNS(ns, name);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (content != null) n.textContent = content;
  return n;
}
function svg(width, height, label) {
  return el("svg", {
    viewBox: `0 0 ${width} ${height}`,
    role: "img",
    "aria-label": label,
  });
}
function finite(value) {
  return value != null && Number.isFinite(Number(value));
}
function verified(c) {
  return c.verification?.passed === true;
}
function current() {
  return state.candidates.filter(
    (c) => state.model === "all" || c.model_id === state.model,
  );
}
function feasible(c) {
  return (
    verified(c) &&
    c.routed === true &&
    c.timing_met !== false &&
    finite(c.accuracy) &&
    finite(c.latency_us) &&
    finite(c.lut) &&
    accuracy(c.accuracy) >= Number($("budget-accuracy").value) / 100 &&
    Number(c.latency_us) <= Number($("budget-latency").value) &&
    Number(c.lut) <= Number($("budget-lut").value)
  );
}
function frontier(candidates) {
  return candidates
    .filter(
      (c) =>
        finite(c[state.axis]) &&
        finite(c.accuracy) &&
        !candidates.some(
          (d) =>
            d !== c &&
            Number(d[state.axis]) <= Number(c[state.axis]) &&
            accuracy(d.accuracy) >= accuracy(c.accuracy) &&
            (Number(d[state.axis]) < Number(c[state.axis]) ||
              accuracy(d.accuracy) > accuracy(c.accuracy)),
        ),
    )
    .sort((a, b) => Number(a[state.axis]) - Number(b[state.axis]));
}
function toast(text) {
  $("toast").textContent = text;
  $("toast").hidden = false;
  setTimeout(() => ($("toast").hidden = true), 3200);
}
function extent(values, pad = 0.1) {
  const clean = values.filter(Number.isFinite);
  if (!clean.length) return [0, 1];
  let min = Math.min(...clean),
    max = Math.max(...clean);
  if (min === max) {
    min -= Math.max(Math.abs(min) * 0.15, 1);
    max += Math.max(Math.abs(max) * 0.15, 1);
  }
  const margin = (max - min) * pad;
  return [min - margin, max + margin];
}
function labelAxis(root, x, y, text, attrs = {}) {
  root.append(el("text", { x, y, class: "axis-label", ...attrs }, text));
}
function setupBudgets() {
  const cs = state.candidates;
  const maxLatency = Math.ceil(
    Math.max(1, ...cs.map((c) => Number(c.latency_us) || 0)) * 1.05,
  );
  const maxLut = Math.ceil(
    Math.max(1, ...cs.map((c) => Number(c.lut) || 0)) * 1.05,
  );
  $("budget-latency").max = maxLatency;
  $("budget-latency").step =
    maxLatency < 10 ? 0.01 : maxLatency < 100 ? 0.1 : 1;
  $("budget-latency").min = 0;
  $("budget-latency").value = maxLatency;
  $("budget-lut").max = maxLut;
  $("budget-lut").min = 0;
  $("budget-lut").value = maxLut;
  $("budget-accuracy").value = 0;
}
function updateBudgets() {
  $("accuracy-output").textContent =
    `${number($("budget-accuracy").value, 1)}%`;
  $("latency-output").textContent =
    `${number($("budget-latency").value, 2)} µs`;
  $("lut-output").textContent = `${number($("budget-lut").value, 0)} LUT4`;
  const cs = current();
  $("candidate-select").replaceChildren(
    ...cs.map((c) => {
      const o = document.createElement("option");
      o.value = c.id;
      o.textContent = c.id;
      return o;
    }),
  );
  if (state.selected) $("candidate-select").value = state.selected.id;
  const valid = cs
    .filter(feasible)
    .sort(
      (a, b) =>
        a.latency_us - b.latency_us || b.accuracy - a.accuracy || a.lut - b.lut,
    );
  $("feasible-count").textContent = valid.length;
  $("feasible-note").textContent =
    `of ${cs.length} measured ${cs.length === 1 ? "design" : "designs"} in this model selection`;
  if (valid.length) {
    const best = valid[0];
    $("recommendation").classList.remove("empty");
    $("recommendation").innerHTML =
      `<span class="eyebrow">LOWEST LATENCY INSIDE YOUR ENVELOPE</span><strong>${esc(best.id)}</strong><p>${pct(best.accuracy)} accuracy · ${number(best.latency_us, 2)} µs · ${number(best.lut, 0)} LUT4</p>`;
    if (
      !state.selected ||
      !feasible(state.selected) ||
      !cs.includes(state.selected)
    )
      selectCandidate(best.id);
  } else {
    $("recommendation").classList.add("empty");
    $("recommendation").innerHTML =
      '<span class="eyebrow">NO VERIFIED DESIGN FITS</span><strong>Widen the envelope.</strong><p>Increase the latency or logic budget, reduce the accuracy threshold, or explore another model.</p>';
    if (cs.length && !cs.includes(state.selected)) selectCandidate(cs[0].id);
  }
  renderPareto();
  renderHistory();
}
function renderSummary() {
  const cs = state.candidates,
    acc = cs.map((c) => accuracy(c.accuracy)).filter(Number.isFinite),
    clocks = cs.map((c) => Number(c.fmax_mhz)).filter((v) => v > 0);
  $("total-designs").textContent = cs.length;
  $("verified-count").textContent =
    `${cs.filter(verified).length} independently RTL-verified`;
  $("accuracy-range").textContent = acc.length
    ? `${number(Math.min(...acc) * 100, 1)}–${number(Math.max(...acc) * 100, 1)}%`
    : "—";
  $("clock-range").textContent = clocks.length
    ? `${number(Math.min(...clocks), 0)}–${number(Math.max(...clocks), 0)} MHz`
    : "—";
}
function renderPareto() {
  const wrap = $("pareto-chart"),
    cs = current().filter((c) => finite(c[state.axis]) && finite(c.accuracy));
  wrap.replaceChildren();
  if (!cs.length) {
    wrap.innerHTML = empty(
      "No measurements to plot",
      "Compile and verify a design to populate this experiment.",
    );
    return;
  }
  const W = 760,
    H = 340,
    p = { l: 65, r: 30, t: 25, b: 58 };
  const [xmin, xmax] = extent(
    cs.map((c) => Number(c[state.axis])),
    0.08,
  );
  let [ymin, ymax] = extent(
    cs.map((c) => accuracy(c.accuracy) * 100),
    0.2,
  );
  ymin = Math.max(0, Math.floor(ymin));
  ymax = Math.min(100, Math.ceil(ymax));
  if (ymin === ymax) ymin = ymax - 1;
  const x = (v) => p.l + ((v - xmin) / (xmax - xmin)) * (W - p.l - p.r),
    y = (v) => p.t + ((ymax - v) / (ymax - ymin)) * (H - p.t - p.b);
  const root = svg(
    W,
    H,
    "Measured hardware accuracy and cost. Use Tab to focus a candidate and Enter to inspect it.",
  );
  for (let i = 0; i <= 4; i++) {
    const vx = xmin + ((xmax - xmin) * i) / 4,
      vy = ymin + ((ymax - ymin) * i) / 4;
    root.append(
      el("line", {
        x1: p.l,
        y1: y(vy),
        x2: W - p.r,
        y2: y(vy),
        class: "grid-line",
      }),
    );
    root.append(
      el(
        "text",
        {
          x: p.l - 12,
          y: y(vy) + 3,
          "text-anchor": "end",
          class: "tick-label",
        },
        `${number(vy, 1)}%`,
      ),
    );
    root.append(
      el("line", {
        x1: x(vx),
        y1: p.t,
        x2: x(vx),
        y2: H - p.b,
        class: "grid-line",
      }),
    );
    root.append(
      el(
        "text",
        {
          x: x(vx),
          y: H - p.b + 20,
          "text-anchor": "middle",
          class: "tick-label",
        },
        number(vx, vx < 10 ? 2 : 0),
      ),
    );
  }
  labelAxis(root, p.l, p.t - 10, "VALIDATION ACCURACY");
  labelAxis(
    root,
    W - p.r,
    H - 10,
    {
      latency_us: "SIMULATED LATENCY / µs",
      lut: "MAPPED LUT4 PRIMITIVES",
      compile_seconds: "COMPILATION WALL TIME / s",
    }[state.axis],
    { "text-anchor": "end" },
  );
  const front = frontier(cs.filter(feasible));
  if (front.length > 1)
    root.append(
      el("polyline", {
        points: front
          .map(
            (c) =>
              `${x(Number(c[state.axis]))},${y(accuracy(c.accuracy) * 100)}`,
          )
          .join(" "),
        fill: "none",
        stroke: "#d94a25",
        "stroke-width": 1.4,
        "stroke-dasharray": "5 4",
      }),
    );
  const sel = state.selected;
  cs.sort((a, b) => (a === sel) - (b === sel));
  cs.forEach((c) => {
    const selected = c === sel;
    const point = el("circle", {
      cx: x(Number(c[state.axis])),
      cy: y(accuracy(c.accuracy) * 100),
      r: selected ? 7 : 4.5,
      fill: feasible(c) ? "#d94a25" : "#c3c9bf",
      stroke: selected ? "#202927" : "#fbfaf6",
      "stroke-width": selected ? 2 : 1.5,
      class: "plot-point",
      tabindex: 0,
      role: "button",
      "aria-label": `${c.id}, ${pct(c.accuracy)} accuracy, ${number(c.latency_us, 2)} microseconds, ${number(c.lut, 0)} LUT4${selected ? ", selected" : ""}`,
      "aria-pressed": selected,
    });
    point.append(
      el(
        "title",
        {},
        `${c.id}\n${pct(c.accuracy)} accuracy\n${number(c.latency_us, 2)} µs · ${number(c.lut, 0)} LUT4\n${feasible(c) ? "Inside budget" : "Outside budget"}`,
      ),
    );
    point.addEventListener("click", () => selectCandidate(c.id));
    point.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        selectCandidate(c.id);
      }
    });
    root.append(point);
    if (selected) {
      const tx = x(Number(c[state.axis])),
        ty = y(accuracy(c.accuracy) * 100);
      root.append(
        el(
          "text",
          {
            x: Math.min(W - p.r - 5, Math.max(p.l + 5, tx)),
            y: ty > 50 ? ty - 16 : ty + 24,
            "text-anchor":
              tx > W * 0.7 ? "end" : tx < W * 0.3 ? "start" : "middle",
            fill: "#202927",
            "font-size": 10,
            "font-family": "ui-monospace,monospace",
          },
          c.id,
        ),
      );
    }
  });
  wrap.append(root);
  $("plot-caption").textContent =
    `${cs.length} measured designs · ${front.length} non-dominated on displayed axes within budget`;
}
function renderHistory() {
  const wrap = $("history-chart"),
    cs = current();
  wrap.replaceChildren();
  const explicit = (state.data.history || [])
    .map((h) => ({
      ...h,
      candidate: state.candidates.find((c) => c.id === h.candidate_id),
    }))
    .filter(
      (h) =>
        h.candidate &&
        (state.model === "all" || h.candidate.model_id === state.model),
    );
  const referenceVolume = Number(state.data.history_reference_hypervolume);
  if (
    explicit.length &&
    referenceVolume > 0 &&
    explicit.every((h) => finite(h.hypervolume) && finite(h.elapsed_seconds))
  ) {
    renderVolumeHistory(explicit, referenceVolume);
    return;
  }
  const rows = explicit.length
    ? explicit
    : cs.map((c, i) => ({
        iteration: i + 1,
        candidate: c,
        strategy: "Recorded candidate order",
      }));
  $("history-count").textContent = `${rows.length} EVALUATIONS`;
  if (!rows.length) {
    wrap.innerHTML = empty(
      "Search trace awaits results",
      "Only evaluated designs appear here.",
    );
    return;
  }
  const W = 500,
    H = 205,
    p = { l: 48, r: 15, t: 20, b: 37 };
  let best = -Infinity;
  const points = rows.map((h, i) => {
    best = Math.max(best, accuracy(h.candidate.accuracy) * 100);
    return { x: i + 1, y: best, row: h };
  });
  let [ymin, ymax] = extent(
    points.map((p) => p.y),
    0.2,
  );
  ymax = Math.min(100, Math.ceil(ymax));
  ymin = Math.max(0, Math.floor(ymin));
  if (ymax === ymin) ymin = ymax - 1;
  const x = (v) =>
      p.l + ((v - 1) / Math.max(1, rows.length - 1)) * (W - p.l - p.r),
    y = (v) => p.t + ((ymax - v) / (ymax - ymin)) * (H - p.t - p.b);
  const root = svg(
    W,
    H,
    "Best observed validation accuracy after each recorded evaluation.",
  );
  for (let i = 0; i < 3; i++) {
    const val = ymin + ((ymax - ymin) * i) / 2;
    root.append(
      el("line", {
        x1: p.l,
        x2: W - p.r,
        y1: y(val),
        y2: y(val),
        class: "grid-line",
      }),
    );
    root.append(
      el(
        "text",
        {
          x: p.l - 8,
          y: y(val) + 3,
          "text-anchor": "end",
          class: "tick-label",
        },
        `${number(val, 0)}%`,
      ),
    );
  }
  let d = `M ${x(points[0].x)} ${y(points[0].y)}`;
  points.slice(1).forEach((pt, i) => (d += ` H ${x(pt.x)} V ${y(pt.y)}`));
  root.append(
    el("path", { d, fill: "none", stroke: "#286b50", "stroke-width": 2 }),
  );
  points.forEach((pt) => {
    const dot = el("circle", {
      cx: x(pt.x),
      cy: y(pt.y),
      r: pt.row.candidate === state.selected ? 5 : 2.5,
      fill: pt.row.candidate === state.selected ? "#d94a25" : "#286b50",
    });
    dot.append(
      el(
        "title",
        {},
        `Evaluation ${pt.x}: ${pt.row.candidate.id}\nBest accuracy: ${number(pt.y, 1)}%\n${pt.row.strategy || ""}`,
      ),
    );
    root.append(dot);
  });
  labelAxis(root, p.l, 11, "BEST OBSERVED ACCURACY");
  root.append(el("text", { x: p.l, y: H - 15, class: "tick-label" }, "1"));
  root.append(
    el(
      "text",
      { x: W - p.r, y: H - 15, class: "tick-label", "text-anchor": "end" },
      rows.length,
    ),
  );
  labelAxis(root, W - p.r, H - 1, "COMPLETED EVALUATIONS", {
    "text-anchor": "end",
  });
  wrap.append(root);
  $("history-note").textContent = explicit.length
    ? "Recorded search evaluation sequence. The curve is the best validation accuracy observed so far; it does not represent a hardware-cost objective."
    : "Candidates in recorded artifact order. The curve is best observed validation accuracy, not a claim of search efficiency. Reproduce strategy comparisons using the benchmark CLI.";
}
function renderVolumeHistory(rows, referenceVolume) {
  const wrap = $("history-chart"),
    W = 500,
    H = 205,
    p = { l: 48, r: 15, t: 23, b: 40 };
  const points = rows.map((row, index) => ({
    row,
    index,
    x: Number(row.elapsed_seconds),
    y: (Number(row.hypervolume) / referenceVolume) * 100,
  }));
  const xmax = Math.max(1, ...points.map((pt) => pt.x)),
    ymax = Math.max(100, ...points.map((pt) => pt.y));
  const x = (v) => p.l + (v / xmax) * (W - p.l - p.r),
    y = (v) => p.t + ((ymax - v) / ymax) * (H - p.t - p.b);
  const root = svg(
    W,
    H,
    "Recorded cost-aware search replay: recovered three-dimensional Pareto hypervolume as a percentage of the full measured reference, versus charged compilation cost.",
  );
  $("history-count").textContent = `${rows.length} QUERIES`;
  for (let i = 0; i <= 2; i++) {
    const value = (ymax * i) / 2;
    root.append(
      el("line", {
        x1: p.l,
        x2: W - p.r,
        y1: y(value),
        y2: y(value),
        class: "grid-line",
      }),
    );
    root.append(
      el(
        "text",
        {
          x: p.l - 8,
          y: y(value) + 3,
          "text-anchor": "end",
          class: "tick-label",
        },
        `${number(value, 0)}%`,
      ),
    );
  }
  for (let i = 0; i <= 3; i++) {
    const value = (xmax * i) / 3;
    root.append(
      el("line", {
        x1: x(value),
        x2: x(value),
        y1: p.t,
        y2: H - p.b,
        class: "grid-line",
      }),
    );
    root.append(
      el(
        "text",
        {
          x: x(value),
          y: H - p.b + 18,
          "text-anchor": i === 0 ? "start" : i === 3 ? "end" : "middle",
          class: "tick-label",
        },
        number(value, 0),
      ),
    );
  }
  let path = `M ${x(0)} ${y(0)}`;
  for (const pt of points) path += ` H ${x(pt.x)} V ${y(pt.y)}`;
  root.append(
    el("path", { d: path, fill: "none", stroke: "#286b50", "stroke-width": 2 }),
  );
  for (const pt of points) {
    const selected = pt.row.candidate === state.selected;
    const dot = el("circle", {
      cx: x(pt.x),
      cy: y(pt.y),
      r: selected ? 4.5 : 2.5,
      fill: selected ? "#d94a25" : "#286b50",
    });
    dot.append(
      el(
        "title",
        {},
        `Query ${pt.row.iteration ?? pt.index + 1}: ${pt.row.candidate.id} · ${pt.row.fidelity || "recorded"}\n${number(pt.y, 2)}% of reference Pareto volume\n${number(pt.x, 2)} seconds charged compilation cost\n${pt.row.reason || pt.row.strategy || ""}`,
      ),
    );
    root.append(dot);
  }
  labelAxis(root, p.l, 11, "REFERENCE 3D PARETO VOLUME / %");
  labelAxis(root, W - p.r, H - 1, "CHARGED COMPILATION COST / s", {
    "text-anchor": "end",
  });
  wrap.replaceChildren(root);
  $("history-note").textContent =
    `${state.data.history_label || "Recorded search policy · measured-cost replay"}. Volume covers accuracy, latency, and mapped LUT4 resources, normalized to the full measured reference. The time axis charges recorded compilation costs; it is not a live wall clock.`;
}
function modelFor(c) {
  return (
    (state.data.models || []).find((m) => m.id === c?.model_id) ||
    state.data.model ||
    {}
  );
}
function renderModel(c) {
  const m = modelFor(c),
    cfg = c?.config || {};
  $("model-title").textContent = m.name || "From features to decisions";
  const layers = m.layers || [];
  const nodes = [
    { op: "input", units: m.input_size },
    ...layers.map((l) => ({
      op: l.op,
      units: l.units || l.output_size || l.weights?.length,
    })),
  ];
  let prior = m.input_size;
  for (const node of nodes) {
    node.inputs = prior;
    if (node.op === "dense") prior = node.units;
  }
  const dense = nodes.filter((n) => n.op === "dense");
  $("model-shape").textContent = dense.length
    ? `${m.input_size || "?"} → ${dense.map((n) => n.units || "?").join(" → ")}`
    : "DENSE / RELU";
  const root = svg(
    570,
    150,
    "Interactive fixed-shape model dataflow. Select a layer to inspect its operation.",
  );
  root.setAttribute("role", "group");
  const gap = 12,
    width = Math.min(
      100,
      (550 - gap * (nodes.length - 1)) / Math.max(1, nodes.length),
    );
  const groups = [];
  function inspectNode(index) {
    groups.forEach((g, i) => {
      g.setAttribute("aria-pressed", i === index);
      g.querySelector("rect").setAttribute(
        "stroke",
        i === index
          ? "#d94a25"
          : nodes[i].op === "relu"
            ? "#e8b79d"
            : "#d7ddd1",
      );
      g.querySelector("rect").setAttribute("stroke-width", i === index ? 2 : 1);
    });
    const n = nodes[index];
    const detail =
      n.op === "input"
        ? `${n.units || "Fixed-shape"} sensor features. Preprocessing is fitted on training data and retained with the model.`
        : n.op === "relu"
          ? "ReLU applies max(0, x) independently to each activation. Inspect the arithmetic specification for the quantized representation."
          : `Dense: ${n.inputs || "?"} inputs × ${n.units || "?"} outputs${n.inputs && n.units ? ` = ${n.inputs * n.units} weight products` : ""}. ${cfg.parallelism || "?"} dedicated MAC lanes reuse multipliers within this layer.`;
    $("operation-detail").textContent = detail;
  }
  nodes.forEach((n, i) => {
    const x = 10 + i * (width + gap),
      y = 35;
    if (i > 0) {
      root.append(
        el("path", {
          d: `M ${x - gap} 70 H ${x - 2}`,
          stroke: "#9ca59a",
          "stroke-width": 1.2,
          fill: "none",
        }),
      );
      root.append(
        el("path", {
          d: `m ${x - 5} 67 3 3-3 3`,
          stroke: "#9ca59a",
          "stroke-width": 1.2,
          fill: "none",
        }),
      );
    }
    const title =
      n.op === "input" ? "Features" : n.op === "relu" ? "ReLU" : "Dense";
    const g = el("g", {
      role: "button",
      tabindex: 0,
      "aria-label": `${title}${n.units ? `, ${n.units} ${n.op === "input" ? "inputs" : "outputs"}` : ""}. Inspect operation.`,
      "aria-pressed": "false",
      class: "model-node",
    });
    g.append(
      el("rect", {
        x,
        y,
        width,
        height: 70,
        rx: 2,
        fill: n.op === "relu" ? "#fae9dd" : "#f1f3ec",
        stroke: n.op === "relu" ? "#e8b79d" : "#d7ddd1",
      }),
    );
    g.append(
      el(
        "text",
        {
          x: x + width / 2,
          y: y + 27,
          "text-anchor": "middle",
          class: "node-title",
        },
        title,
      ),
    );
    g.append(
      el(
        "text",
        {
          x: x + width / 2,
          y: y + 45,
          "text-anchor": "middle",
          class: "node-sub",
        },
        n.op === "relu"
          ? "max(0, x)"
          : `${n.units || "?"} ${n.op === "input" ? "inputs" : "outputs"}`,
      ),
    );
    g.addEventListener("click", () => inspectNode(i));
    g.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        inspectNode(i);
      }
    });
    root.append(g);
    groups.push(g);
    root.append(
      el(
        "text",
        {
          x: x + width / 2,
          y: y + 88,
          "text-anchor": "middle",
          class: "node-sub",
        },
        n.op === "input"
          ? "SENSOR"
          : n.op === "relu"
            ? "ACTIVATION"
            : i === nodes.length - 1
              ? "CLASS SCORES"
              : `LAYER ${nodes.slice(0, i + 1).filter((n) => n.op === "dense").length}`,
      ),
    );
  });
  $("model-graph").replaceChildren(root);
  $("operation-detail").textContent =
    "Select a layer to inspect its operation.";
  $("dataflow-note").textContent = c
    ? `${cfg.parallelism ?? "—"} parallel MAC ${cfg.parallelism === 1 ? "lane is" : "lanes are"} dedicated to each layer and reused across dot-product operations. ${cfg.pipeline ? "Registered multiplier pipeline." : "Direct multiply-accumulate scheduling."} Integer arithmetic is checked independently.`
    : "Select a candidate to inspect its integer arithmetic and multiplier scheduling.";
  $("config-grid").innerHTML = [
    ["PRECISION", `${cfg.bits ?? "—"} bits`],
    ["ACCUMULATOR", `${cfg.accumulator_bits ?? "—"} bits`],
    [
      "PARALLELISM",
      `${cfg.parallelism ?? "—"} MAC ${cfg.parallelism === 1 ? "lane" : "lanes"}`,
    ],
    ["FRACTIONAL BITS", cfg.fractional_bits ?? "—"],
    ["PIPELINING", cfg.pipeline ? "Enabled" : "Disabled"],
    ["BUFFERING", cfg.buffering ?? "—"],
  ]
    .map(
      ([k, v]) => `<div><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`,
    )
    .join("");
}
function renderEvidence(c) {
  const v = c.verification || {};
  $("candidate-name").textContent = c.id;
  $("candidate-status").textContent = verified(c)
    ? "✓ RTL VERIFIED"
    : "EVIDENCE INCOMPLETE";
  $("candidate-status").style.color = verified(c)
    ? "var(--green)"
    : "var(--muted)";
  $("candidate-metrics").innerHTML = [
    metric("VALIDATION ACCURACY", pct(c.accuracy)),
    metric("SIMULATED LATENCY", number(c.latency_us, 2), "µs"),
    metric("LUT4 / REGISTERS", `${number(c.lut, 0)} / ${number(c.ff, 0)}`),
    metric("DSP / BRAM", `${number(c.dsp, 0)} / ${number(c.bram, 0)}`),
    metric("ROUTED FMAX", number(c.fmax_mhz, 1), "MHz"),
    metric("COMPILATION", number(c.compile_seconds, 1), "s"),
  ].join("");
  const throughput = c.core_throughput_estimate_per_s ?? c.throughput_per_s;
  $("throughput-note").hidden = !finite(throughput);
  $("throughput-note").textContent = finite(throughput)
    ? `CORE THROUGHPUT BOUND: ${number(throughput, 0)} inferences/s · INITIATION INTERVAL: ${number(c.initiation_interval_cycles, 0)} cycles. ${c.throughput_scope || "Analytic estimate at the target clock; excludes streaming serialization and backpressure."}`
    : "";
  const boundaryCount = v.boundary_and_random_samples ?? v.boundary_samples;
  const boundaryLabel =
    v.boundary_and_random_samples == null
      ? "Boundary values"
      : "Boundary & random";
  const tests = [
    [
      "Integer differential",
      v.passed,
      finite(v.samples)
        ? `${number(v.samples, 0)} test vectors`
        : v.summary || "See verification report",
    ],
    [
      boundaryLabel,
      v.passed === true && (boundaryCount > 0 || v.boundary === true),
      finite(boundaryCount)
        ? `${number(boundaryCount, 0)} vectors`
        : "See detailed report",
    ],
    [
      "Backpressure",
      v.backpressure === true,
      v.backpressure === true
        ? "Output stability under stalls"
        : "Not independently recorded here",
    ],
    [
      "Reset behavior",
      v.reset === true,
      v.reset === true
        ? "Reset during active transaction"
        : "Not independently recorded here",
    ],
  ];
  $("view-verification").innerHTML =
    `<div class="verification-layout"><div class="verification-intro"><div class="check-seal">${verified(c) ? "✓" : "?"}</div><div><h3>${verified(c) ? "Bit-exact against the integer reference." : "Inspect the available evidence."}</h3><p>${esc(v.summary || "Generated RTL is simulated independently against integer reference outputs. Synthesis and routing results are recorded separately. Full reports and raw HDL are available for inspection.")}</p></div></div><div class="check-grid">${tests.map(([label, passed, detail]) => `<div class="check-item ${passed ? "" : "unconfirmed"}"><b>${passed ? "✓" : "·"}</b><div>${esc(label)}<span>${esc(detail)}</span></div></div>`).join("")}</div></div><p class="verification-footnote">ARITHMETIC: ${esc(c.config?.bits ?? "—")}-BIT ACTIVATIONS · ${esc(c.config?.accumulator_bits ?? "—")}-BIT ACCUMULATOR · ${esc(c.latency_cycles ?? "—")} SIMULATED CYCLES. Read the arithmetic specification for rounding, overflow, and handshake semantics.</p>`;
  $("artifact-links").replaceChildren();
  for (const [label, url] of [
    ["HDL ↗", c.hdl_url],
    ["Manifest ↗", c.manifest_url],
    ["Raw report ↗", c.report_url],
    ["VCD ↗", c.waveform_url],
  ]) {
    const href = safeUrl(url);
    if (href) {
      const a = document.createElement("a");
      a.href = href;
      a.textContent = label;
      a.target = "_blank";
      a.rel = "noreferrer";
      $("artifact-links").append(a);
    }
  }
  $("measurement-code").textContent = JSON.stringify(c, null, 2);
  $("export-selection").disabled = false;
}
async function selectCandidate(id) {
  const c = state.candidates.find((c) => c.id === id);
  if (!c) return;
  state.selected = c;
  $("candidate-select").value = c.id;
  const token = ++state.selectionToken;
  stopWave();
  renderPareto();
  renderHistory();
  renderModel(c);
  renderEvidence(c);
  state.hdl = c.hdl || "";
  $("hdl-code").textContent = state.hdl || "Loading generated HDL…";
  $("hdl-filename").textContent = c.hdl_url?.split("/").pop() || "design.v";
  state.wave = c.waveform || null;
  state.frame = 0;
  renderWave();
  if (!state.hdl && safeUrl(c.hdl_url)) {
    try {
      const r = await fetch(c.hdl_url);
      if (!r.ok) throw Error(`HTTP ${r.status}`);
      const text = await r.text();
      if (token === state.selectionToken) {
        state.hdl = text;
        $("hdl-code").textContent = text;
      }
    } catch (err) {
      if (token === state.selectionToken)
        $("hdl-code").textContent =
          `HDL could not be loaded (${err.message}). Use the artifact link above.`;
    }
  } else if (!state.hdl)
    $("hdl-code").textContent = "No generated HDL attached to this record.";
  if (!state.wave && safeUrl(c.waveform_url)) {
    try {
      const r = await fetch(c.waveform_url);
      if (!r.ok) throw Error(`HTTP ${r.status}`);
      const text = await r.text();
      if (token === state.selectionToken) {
        state.wave = c.waveform_url.endsWith(".json")
          ? JSON.parse(text)
          : parseVcd(text);
        state.frame = 0;
        renderWave();
      }
    } catch (err) {
      if (token === state.selectionToken)
        $("waveform-chart").innerHTML = empty(
          "Trace unavailable",
          `The waveform artifact could not be read: ${err.message}`,
        );
    }
  }
}
function parseVcd(text) {
  const lines = text.split(/\r?\n/),
    defs = [],
    events = [];
  let time = 0,
    inDefinitions = true,
    scale = (text.match(/\$timescale\s+([^$]+)\$end/)?.[1] || "VCD time units")
      .trim()
      .replace(/\s+/g, " ");
  for (const line of lines) {
    const t = line.trim();
    if (t.startsWith("$var")) {
      const a = t.split(/\s+/);
      if (defs.length < 100)
        defs.push({ code: a[3], name: a[4], width: Number(a[2]) });
    }
    if (t.startsWith("$enddefinitions")) inDefinitions = false;
    if (inDefinitions) continue;
    if (t[0] === "#") {
      time = Number(t.slice(1));
      continue;
    }
    if (/^[01xz]/i.test(t)) {
      events.push({ time, code: t.slice(1), value: t[0] });
    } else if (t[0] === "b") {
      const a = t.slice(1).split(/\s+/);
      events.push({ time, code: a[1], value: a[0] });
    }
  }
  const preferred = [
    "clk",
    "rst",
    "reset",
    "in_valid",
    "in_ready",
    "out_valid",
    "out_ready",
    "busy",
    "state",
  ];
  const chosen = preferred
    .map((n) => defs.find((d) => d.name === n))
    .filter(Boolean);
  for (const d of defs) {
    if (chosen.length >= 8) break;
    if (!chosen.includes(d) && d.width <= 32) chosen.push(d);
  }
  const codes = new Set(chosen.map((d) => d.code));
  const relevant = events.filter((e) => codes.has(e.code));
  const times = [...new Set(relevant.map((e) => e.time))]
    .sort((a, b) => a - b)
    .slice(0, 200);
  const values = new Map();
  let ix = 0;
  const sorted = relevant.sort((a, b) => a.time - b.time);
  const signals = chosen.map((d) => ({
    name: d.name,
    width: d.width,
    values: [],
  }));
  for (const tm of times) {
    while (ix < sorted.length && sorted[ix].time <= tm) {
      values.set(sorted[ix].code, sorted[ix].value);
      ix++;
    }
    signals.forEach((s, i) => s.values.push(values.get(chosen[i].code) || "x"));
  }
  return {
    cycles: times,
    signals,
    time_unit: scale,
    kind: "vcd",
    truncated: [...new Set(relevant.map((e) => e.time))].length > 200,
  };
}
function stopWave() {
  state.playing = false;
  clearInterval(state.timer);
  state.timer = null;
  $("wave-play").textContent = "▶ Replay";
}
function renderWave() {
  const w = state.wave,
    wrap = $("waveform-chart");
  if (!w || !Array.isArray(w.signals) || !w.signals.length) {
    wrap.innerHTML = empty(
      "No waveform attached",
      "A recorded simulation trace will appear when the candidate includes a waveform artifact.",
    );
    $("wave-play").disabled = true;
    $("wave-position").disabled = true;
    return;
  }
  const length = Math.min(
    200,
    Math.max(...w.signals.map((s) => s.values?.length || 0)),
  );
  if (!length) return;
  state.frame = Math.min(state.frame, length - 1);
  $("wave-play").disabled = false;
  $("wave-position").disabled = false;
  $("wave-position").max = length - 1;
  $("wave-position").value = state.frame;
  $("wave-cycle").textContent = w.cycles?.[state.frame] ?? state.frame;
  $("wave-position-label").textContent = w.kind === "vcd" ? "Time" : "Cycle";
  $("wave-caption").textContent =
    `Recorded RTL trace · ${w.kind === "vcd" ? `VCD time in ${w.time_unit || "file units"}` : "clock cycles"}${w.truncated ? " · first 200 timestamps" : ""}`;
  const W = 950,
    row = 40,
    left = 125,
    right = 18,
    top = 26,
    H = top + w.signals.length * row + 20;
  const root = svg(
    W,
    H,
    "Recorded simulation waveform. Replay controls move the time cursor.",
  );
  const dx = (W - left - right) / Math.max(1, length - 1);
  for (let i = 0; i < length; i += Math.max(1, Math.ceil(length / 12))) {
    const x = left + i * dx;
    root.append(
      el("line", {
        x1: x,
        x2: x,
        y1: top - 7,
        y2: H - 15,
        stroke: "#e2e5dc",
        "stroke-dasharray": "2 4",
      }),
    );
    root.append(
      el(
        "text",
        { x, y: 12, "text-anchor": "middle", class: "tick-label" },
        w.cycles?.[i] ?? i,
      ),
    );
  }
  w.signals.slice(0, 12).forEach((s, idx) => {
    const y = top + idx * row;
    root.append(
      el(
        "text",
        {
          x: 0,
          y: y + 18,
          "font-size": 10,
          "font-family": "ui-monospace,monospace",
          fill: "#59665a",
        },
        s.name,
      ),
    );
    const vals = s.values || [];
    const binary = vals.every((v) => [0, 1, "0", "1", "x", "z"].includes(v));
    if (binary) {
      let d = "";
      let lastY = null;
      vals.slice(0, length).forEach((v, i) => {
        const xx = left + i * dx,
          known = ["0", "1", 0, 1].includes(v);
        if (!known) {
          if (lastY !== null) d += ` H${xx}`;
          lastY = null;
          root.append(
            el("line", {
              x1: xx,
              x2: xx + dx,
              y1: y + 15,
              y2: y + 15,
              stroke: "#8c928b",
              "stroke-dasharray": "2 2",
            }),
          );
          if (i === 0 || vals[i - 1] !== v)
            root.append(
              el(
                "text",
                { x: xx + 2, y: y + 12, "font-size": 7, fill: "#717772" },
                String(v),
              ),
            );
          return;
        }
        const yy = y + (v === 1 || v === "1" ? 5 : 25);
        d += lastY === null ? ` M${xx} ${yy}` : ` H${xx} V${yy}`;
        lastY = yy;
      });
      root.append(
        el("path", {
          d,
          fill: "none",
          stroke: idx % 2 ? "#286b50" : "#d94a25",
          "stroke-width": 1.5,
        }),
      );
    } else {
      let last = -Infinity;
      vals.slice(0, length).forEach((v, i) => {
        if (i && String(v) === String(vals[i - 1])) return;
        const x = left + i * dx;
        root.append(
          el("line", {
            x1: x,
            x2: x,
            y1: y + 5,
            y2: y + 25,
            stroke: "#869581",
          }),
        );
        if (x - last > 35) {
          root.append(
            el(
              "text",
              {
                x: x + 4,
                y: y + 19,
                "font-size": 8,
                "font-family": "ui-monospace,monospace",
                fill: "#59665a",
              },
              String(v).length > 14 ? String(v).slice(0, 10) + "…" : v,
            ),
          );
          last = x;
        }
      });
      root.append(
        el("line", {
          x1: left,
          x2: W - right,
          y1: y + 5,
          y2: y + 5,
          stroke: "#869581",
        }),
      );
      root.append(
        el("line", {
          x1: left,
          x2: W - right,
          y1: y + 25,
          y2: y + 25,
          stroke: "#869581",
        }),
      );
    }
  });
  const cx = left + state.frame * dx;
  root.append(
    el("line", {
      x1: cx,
      x2: cx,
      y1: 18,
      y2: H - 15,
      stroke: "#202927",
      "stroke-width": 1.3,
    }),
  );
  root.append(el("path", { d: `M${cx - 4} 15h8l-4 6z`, fill: "#202927" }));
  wrap.replaceChildren(root);
}
function activateTab(name, focus = false) {
  document.querySelectorAll("[data-tab]").forEach((t) => {
    const active = t.dataset.tab === name;
    t.classList.toggle("active", active);
    t.setAttribute("aria-selected", active);
    t.tabIndex = active ? 0 : -1;
    $(`view-${t.dataset.tab}`).hidden = !active;
    if (active && focus) t.focus();
  });
  if (name !== "waveform") stopWave();
}
function exportSelection() {
  if (!state.selected) return;
  const blob = new Blob(
    [
      JSON.stringify(
        {
          schema_version: 1,
          exported_at: new Date().toISOString(),
          provenance:
            "Recorded SILICONPILOT experiment; timing estimates are not physical FPGA measurements.",
          target: state.data.target,
          dataset: state.data.dataset,
          candidate: state.selected,
        },
        null,
        2,
      ),
    ],
    { type: "application/json" },
  );
  const url = URL.createObjectURL(blob),
    a = document.createElement("a");
  a.href = url;
  a.download = `siliconpilot-${state.selected.id}.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function load() {
  try {
    const response = await fetch("data/observatory.json", {
      cache: "no-cache",
    });
    if (!response.ok) throw Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!Array.isArray(data.candidates))
      throw Error("Expected candidates array in experiment record");
    state.data = data;
    state.candidates = data.candidates.map((c) => ({
      ...c,
      accuracy: accuracy(c.accuracy),
      latency_us: finite(c.latency_us)
        ? Number(c.latency_us)
        : finite(c.latency_cycles) && finite(data.target?.clock_mhz)
          ? Number(c.latency_cycles) / Number(data.target.clock_mhz)
          : null,
    }));
    const target = data.target || {};
    $("target-device").textContent =
      `${target.family || "ECP5"} · ${target.device || "LFE5U-25F"}`;
    const dataset = data.dataset || {};
    $("dataset-label").textContent =
      `${dataset.name || "Sensor classifier"}${dataset.validation_samples ? ` · ${number(dataset.validation_samples, 0)} validation examples` : ""}`;
    $("provenance-label").textContent =
      `Artifact generated ${data.generated_at || "at the recorded benchmark revision"}${dataset.license ? ` · Dataset: ${dataset.license}` : ""}.`;
    for (const m of data.models || []) {
      const o = document.createElement("option");
      o.value = m.id;
      o.textContent = m.name || m.id;
      $("model-select").append(o);
    }
    setupBudgets();
    renderSummary();
    $("load-message").hidden = state.candidates.length > 0;
    if (!state.candidates.length)
      $("load-message").textContent =
        "The observatory is ready. No measured candidates are included yet. Run the benchmark pipeline to produce data/observatory.json.";
    updateBudgets();
    if (state.candidates.length && !state.selected)
      selectCandidate(state.candidates[0].id);
    if (!state.candidates.length) {
      renderModel();
      $("view-verification").innerHTML = empty(
        "Evidence appears after verification",
        "There are no candidate records in this experiment.",
      );
    }
  } catch (err) {
    $("load-message").textContent =
      `Recorded experiment could not be loaded: ${err.message}. Serve this directory over HTTP and ensure data/observatory.json is present. See the repository instructions.`;
    state.data = { candidates: [], models: [] };
    renderModel();
    $("pareto-chart").innerHTML = empty(
      "Experiment data unavailable",
      "The interface never substitutes synthetic performance numbers.",
    );
    $("history-chart").innerHTML = empty(
      "No recorded search trace",
      "Load a real experiment to inspect its history.",
    );
    $("view-verification").innerHTML = empty(
      "No evidence loaded",
      "Candidate reports must come from the compiler and verification pipeline.",
    );
  }
}
$("model-select").addEventListener("change", (e) => {
  state.model = e.target.value;
  updateBudgets();
});
$("axis-select").addEventListener("change", (e) => {
  state.axis = e.target.value;
  renderPareto();
});
["budget-accuracy", "budget-latency", "budget-lut"].forEach((id) =>
  $(id).addEventListener("input", updateBudgets),
);
$("reset-budgets").addEventListener("click", () => {
  setupBudgets();
  updateBudgets();
});
$("export-selection").addEventListener("click", exportSelection);
document.querySelectorAll("[data-tab]").forEach((t) => {
  t.addEventListener("click", () => activateTab(t.dataset.tab));
  t.addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    const tabs = [...document.querySelectorAll("[data-tab]")],
      ix = tabs.indexOf(t),
      next =
        e.key === "Home"
          ? 0
          : e.key === "End"
            ? tabs.length - 1
            : (ix + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) %
              tabs.length;
    activateTab(tabs[next].dataset.tab, true);
  });
});
$("copy-hdl").addEventListener("click", async () => {
  if (!state.hdl) return toast("No HDL is loaded for this candidate.");
  try {
    await navigator.clipboard.writeText(state.hdl);
    toast("Generated HDL copied.");
  } catch {
    toast(
      "Clipboard unavailable. Use the HDL artifact link to save the source.",
    );
  }
});
$("wave-position").addEventListener("input", (e) => {
  stopWave();
  state.frame = Number(e.target.value);
  renderWave();
});
$("wave-play").addEventListener("click", () => {
  if (state.playing) return stopWave();
  if (!state.wave) return;
  state.playing = true;
  $("wave-play").textContent = "Ⅱ Pause";
  if (state.frame >= Number($("wave-position").max)) state.frame = 0;
  state.timer = setInterval(() => {
    state.frame++;
    if (state.frame > Number($("wave-position").max)) {
      stopWave();
      state.frame = Number($("wave-position").max);
    }
    renderWave();
  }, 100);
});
window.addEventListener("pagehide", stopWave);
load();

// Local compilation is exposed only when the loopback server confirms its API.
let localBusy = false;
$("candidate-select").addEventListener("change", (e) =>
  selectCandidate(e.target.value),
);
async function detectLocalCompiler() {
  if (!["127.0.0.1", "localhost", "[::1]"].includes(location.hostname)) return;
  try {
    const r = await fetch("/api/health");
    if (!r.ok) return;
    const health = await r.json();
    if (health.mode !== "local") return;
    $("local-compile-toggle").hidden = false;
  } catch {
    /* Static hosting and ordinary HTTP preview intentionally have no compiler API. */
  }
}
function openLocalCompiler() {
  const cfg = state.selected?.config || {
    bits: 8,
    fractional_bits: 5,
    accumulator_bits: 24,
    parallelism: 1,
    pipeline: false,
    buffering: 1,
  };
  $("compile-model").replaceChildren(
    ...(state.data?.models || []).map((m) => {
      const o = document.createElement("option");
      o.value = m.id;
      o.textContent = m.name || m.id;
      return o;
    }),
  );
  if (state.selected) $("compile-model").value = state.selected.model_id;
  for (const [id, key] of [
    ["compile-bits", "bits"],
    ["compile-fraction", "fractional_bits"],
    ["compile-accumulator", "accumulator_bits"],
    ["compile-parallelism", "parallelism"],
    ["compile-buffering", "buffering"],
  ])
    $(id).value = cfg[key];
  $("compile-pipeline").checked = Boolean(cfg.pipeline);
  $("local-compile-dialog").showModal();
}
$("local-compile-toggle").addEventListener("click", openLocalCompiler);
$("local-compile-close").addEventListener("click", () =>
  $("local-compile-dialog").close(),
);
$("local-compile-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (localBusy) return;
  const config = {
    bits: Number($("compile-bits").value),
    fractional_bits: Number($("compile-fraction").value),
    accumulator_bits: Number($("compile-accumulator").value),
    parallelism: Number($("compile-parallelism").value),
    pipeline: $("compile-pipeline").checked,
    buffering: Number($("compile-buffering").value),
  };
  const result = $("local-compile-result");
  result.hidden = false;
  result.classList.remove("error");
  if (
    config.fractional_bits >= config.bits ||
    config.accumulator_bits < 2 * config.bits
  ) {
    result.classList.add("error");
    result.textContent =
      "Fractional bits must be fewer than precision bits. Accumulator width must be at least twice precision.";
    return;
  }
  localBusy = true;
  $("local-compile-submit").disabled = true;
  $("local-compile-submit").textContent =
    "Compiling & independently simulating…";
  result.textContent =
    "Running the local compiler and integer-reference testbench. This may take several seconds.";
  try {
    const r = await fetch("/api/compile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model_id: $("compile-model").value,
        config,
        verify: true,
        route: false,
      }),
    });
    const data = await r.json();
    if (!r.ok) throw Error(data.error || data.message || `HTTP ${r.status}`);
    const passed = data.verification?.passed === true;
    result.classList.toggle("error", !passed);
    result.innerHTML = `<strong>${passed ? "Fresh RTL verified." : "Compilation returned. Inspect verification."}</strong><div>${passed ? `${number(data.verification.samples, 0)} integer-reference test vectors passed.` : "Verification evidence is included in the response below."} This local job has not been synthesized or routed.</div>`;
    for (const [label, file] of [
      ["Generated HDL", "design.v"],
      ["Build manifest", "manifest.json"],
    ]) {
      const href = safeUrl(`${data.artifact_base || ""}${file}`);
      if (href && data.artifact_base) {
        const a = document.createElement("a");
        a.href = href;
        a.target = "_blank";
        a.rel = "noreferrer";
        a.textContent = label + " ↗";
        result.append(a);
      }
    }
    const details = document.createElement("details"),
      summary = document.createElement("summary"),
      pre = document.createElement("pre");
    summary.textContent = "Inspect compiler response";
    pre.textContent = JSON.stringify(data, null, 2);
    details.append(summary, pre);
    result.append(details);
  } catch (err) {
    result.classList.add("error");
    result.textContent = `Local compilation failed: ${err.message}. Check the toolchain installation and retry. Full errors remain visible here.`;
  } finally {
    localBusy = false;
    $("local-compile-submit").disabled = false;
    $("local-compile-submit").innerHTML =
      "Generate HDL & simulate <span>→</span>";
  }
});
detectLocalCompiler();
