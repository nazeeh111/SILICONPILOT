# Research foundations and scope

Research checked against primary project repositories and paper landing pages on 25 October 2026. External authors' reported results are references, not SILICONPILOT measurements.

## What is established, and what this project investigates

Learning hardware costs and using them to guide search is established research. SILICONPILOT must not claim to invent surrogate-assisted FPGA optimization. The investigation here is narrower: **does learning from this compiler's inexpensive synthesis results and more expensive routed results improve design selection on an open ECP5 flow under matched compilation budgets?** The original artifacts are this implementation, measured corpus, acquisition policy, and controlled experiments. A new implementation or a useful result does not establish algorithmic novelty or broad superiority.

The release's benchmark report, raw logs and manifests determine which hypotheses are supported. Failed routing, verification failures, and infeasible designs remain part of evaluation rather than disappearing from the denominator. Place-and-route timing is a tool estimate, and simulation cycle counts are not physical board measurements.

## Foundations and credible alternatives

| Primary source | Mechanism and relevance | Decision for SILICONPILOT |
| --- | --- | --- |
| [Duarte et al., 2018](https://arxiv.org/abs/1804.06913), [hls4ml](https://github.com/fastmachinelearning/hls4ml) | Configurable ML-to-FPGA compilation; precision and architecture affect resources and latency. | Cite as a foundational compiler. Use an original small RTL backend to keep the ECP5 core free of proprietary HLS tools. No hls4ml benchmark equivalence claim. |
| [Amaranth](https://github.com/amaranth-lang/amaranth) | Python hardware construction, simulation and toolchain integration. | A viable implementation foundation. Direct Verilog generation is sufficient for this deliberately small subset and keeps emitted circuits easy to inspect. |
| [Yosys](https://github.com/YosysHQ/yosys), [nextpnr](https://github.com/YosysHQ/nextpnr) | Open synthesis and architecture-specific placement/routing. | Actual synthesis and routed ECP5 results are the expensive labels. Preserve tool versions, exact commands and logs. |
| [Verilator](https://github.com/verilator/verilator) | Compiled SystemVerilog simulation and linting. | A strong independent simulation option. Use the release's documented simulator; do not suggest that merely installing a simulator verifies a circuit. |
| [Balandat et al., BoTorch, 2020](https://arxiv.org/abs/1910.06403), [BoTorch](https://github.com/meta-pytorch/botorch) | Modular probabilistic models and acquisition functions for Bayesian optimization. | Reference for the standard BO baseline. A small Gaussian-process baseline can avoid a mandatory PyTorch runtime, but should be named for its actual implementation. |
| [Foumani et al., 2022/2023](https://arxiv.org/abs/2211.02732) | Cost-aware selection among biased low- and high-fidelity information sources. | Do not assume synthesis and routed timing are interchangeable. Validate correlation and ablate fidelity use and compilation cost normalization. |
| [SNAC-Pack 2.0, Weitz et al., 2026](https://arxiv.org/abs/2605.16138), [implementation](https://github.com/fastmachinelearning/nac-opt) | Surrogate-assisted multi-objective FPGA neural architecture codesign, global NSGA-II search and local quantization/pruning with hls4ml deployment. | Directly relevant prior art. Distinguish SILICONPILOT's open ECP5 toolchain and evidence-oriented inspection from unsupported claims of inventing hardware-aware search. |
| [da4ml, Sun et al., 2025/2026](https://arxiv.org/abs/2507.04535), [implementation](https://github.com/calad0i/da4ml) | Distributed arithmetic offers a different way to implement fixed-weight linear operations. | A credible alternative to multiplier reuse. This release does not compare against it and cannot claim the best accelerator architecture. |

The current hls4ml README lists several vendor HLS backends and cites newer distributed-arithmetic work. That is a reason to examine actual backend requirements rather than describing every ML-to-FPGA path as inherently proprietary. SILICONPILOT's documented core, however, uses only its own RTL and the open synthesis/routing toolchain. [hls4ml build documentation](https://github.com/fastmachinelearning/hls4ml#building-a-project)

## Evaluation required for the central claim

Use the same candidate space, initial observations, accuracy checks, routing seeds and compilation-cost accounting for fixed architecture, random search and Gaussian-process Bayesian optimization. Report multiple search seeds, every attempted evaluation, feasible Pareto recovery, and achieved utility as a function of cumulative synthesis-plus-routing wall time. A replay study over an exhaustively measured finite corpus is useful and reproducible, but must be labeled replay; it is not a live optimization speed measurement.

Train the surrogate without the held-out network topology. Report held-out prediction errors and uncertainty coverage separately from interpolation. When search objectives include quantized classification accuracy, use validation rows for search and reserve test rows for final evaluation. Ablate uncertainty, low-fidelity synthesis features, and cost normalization. If one method loses, report that result. A small sensor classifier and one FPGA do not support general hardware superiority.

## Real sensor demonstration

[UCI Banknote Authentication](https://archive.ics.uci.edu/dataset/267/banknote+authentication) contains 1,372 examples, each with four features derived from industrial-camera images: wavelet variance, skewness, curtosis and image entropy. These are real sensor-derived features, not synthetic data. The circuit accepts those four precomputed, standardized features; it does not acquire camera frames or compute wavelets. This dataset is licensed CC BY 4.0 and is attributed in [THIRD_PARTY.md](THIRD_PARTY.md).

The reproducible training script saves row-index splits and fits preprocessing on training rows only. The source does not provide specimen/group IDs, so a stratified row split cannot establish generalization to unseen physical banknotes or cameras. Hidden widths 4, 8 and 12 provide topology variation for hardware generalization experiments, not three independent datasets.

## PaperVizAgent assessment

[Google Research's PaperVizAgent](https://github.com/google-research/papervizagent) was inspected as requested. Its README describes a multi-agent illustration pipeline and configures external model APIs through keys or cloud settings. It is Apache-2.0 software, but its documented model workflow is not an established free local rendering path. Under this project's no separately billed APIs constraint, technically accurate editable SVG/Mermaid diagrams and data-driven local plots are the feasible route. No PaperVizAgent output or runtime result is claimed.
