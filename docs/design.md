# Hardware Design Observatory

SILICONPILOT uses the visual language of a laboratory instrument: warm paper, graphite ink, safety orange for candidate selection, and muted green for verification. Typography separates editorial context, measured values, and source-level details. The mark is an original editable SVG chip grid with a directional triangle.

The app is buildless HTML, CSS, and JavaScript with no external runtime, fonts, analytics, or network services. Serve `observatory/` over HTTP. It loads `data/observatory.json`, then fetches selected HDL and waveform artifacts relative to that directory. It can be hosted statically; the published experience explores recorded experiments rather than remotely running FPGA tools.

## Interaction contract

- Accuracy, latency, and mapped-LUT4 sliders filter actual measured candidates. The recommended design is the lowest-latency independently verified, routed candidate meeting timing and satisfying all three budgets. Ties prefer accuracy and then fewer mapped LUT4 primitives.
- Pareto points are keyboard-focusable buttons. The frontier contains candidates not dominated in selected horizontal cost and accuracy, inside the current constraints. A candidate is dominated when another has no greater cost, no lower accuracy, and improves at least one.
- Model graph nodes can be clicked or focused and activated with Enter to inspect operation dimensions and lane scheduling. Model selection limits chart points and candidate recommendations. The inspected dataflow and arithmetic always follow the selected candidate.
- When supplied history includes hypervolume, charged elapsed seconds, and a reference volume, the search trace shows recovered 3D accuracy–latency–mapped-LUT4 Pareto hypervolume divided by that measured reference, against charged compilation cost. It is explicitly labeled as measured-cost replay. Other history shows best observed validation accuracy; without explicit history it is clearly labeled as artifact order and makes no search-efficiency claim.
- Verification claims require explicit evidence fields. Missing boundary, reset, or backpressure details remain unconfirmed. HDL, manifest, raw report, and VCD links point at retained artifacts.
- Waveform replay uses supplied signal arrays or parses an actual VCD. VCD replay shows event timestamps, preserves unknown values, and caps display to the first 200 transitions. The full file remains downloadable.
- Export saves the selected record with experiment provenance. It does not compile hardware.

Missing or invalid experiment data produces a clear empty/error state and never substituted performance values. All timings are labeled as simulation or routed estimates. The UI makes no physical FPGA measurement claim.

## Data format

Top-level fields: `schema_version`, `generated_at`, `target`, `dataset`, `models`, `candidates`, and optional `history`. `target.clock_mhz` is used only to convert recorded latency cycles when microseconds are absent.

Candidate fields include `id`, `model_id`, `config`, `accuracy` (fraction or percentage), `latency_cycles`, `latency_us`, `throughput_per_s`, `lut`, `ff`, `dsp`, `bram`, `fmax_mhz`, `compile_seconds`, `routed`, `timing_met`, `verification`, and artifact URLs relative to the observatory root. HDL may alternatively be embedded in `hdl`. Verification fields are `passed`, `samples`, `boundary_samples`, `backpressure`, `reset`, and `summary`.

Optional waveform data: `{cycles:[0,1,...], signals:[{name:"out_valid", values:[0,0,1,...]}]}`. Alternatively `waveform_url` can reference a VCD or equivalent waveform JSON. History entries reference `candidate_id` and can include `iteration` and `strategy`.

The layout responds from a desktop instrument workspace to a single-column mobile inspection view. On narrow screens, the Pareto plot and model graph scroll horizontally to preserve legible scientific labels. Tabs support standard arrow-key navigation. Reduced-motion preferences disable transitions. Color is supplemented with text labels, selection outlines, and verification symbols.

Chart resource counts use total mapped LUT4 equivalents: logic LUT4 + 2 × CCU2C carry cells, matching nextpnr total LUT4 accounting. The measurement record separately retains logic_lut, carry_lut, and routed_comb usage. Core latency excludes streaming top-level serialization. Each dense layer owns its MAC lanes; multipliers are reused within each layer, not shared across layers. The acquisition chart uses validation examples; untouched final-test accuracy is reported separately.

## Local compiler

When the app is served by the SILICONPILOT local server on loopback, it confirms `/api/health` reports `mode: local` and exposes a native dialog. The user can configure a supplied model's precision, fraction and accumulator widths, dedicated multiplier lanes, buffering, and pipelining. Submitting posts the same typed configuration to `/api/compile` with verification enabled and routing disabled. The UI prevents duplicate submission, retains errors, and links fresh HDL and manifest evidence. New local simulations remain separate from the recorded, synthesized and routed Pareto corpus. On public static hosting the local compiler control is absent.
