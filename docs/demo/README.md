# SILICONPILOT demonstration film

A 60-second landscape film made with the `/brag` workflow and a pinned local Hyperframes renderer. It shows genuine observatory captures, exact compiler behavior and quantitative charts drawn from the measured corpus. The presentation is intentionally silent. The UI captures show recorded experiment results; the film does not depict live FPGA execution or physical hardware measurements.

- `brag.mp4`: 1920×1080, 30fps; selected UI hero baked into frame zero.
- `brag.jpg`: settled product hero poster.
- `composition/index.html`: editable, seekable HTML/GSAP composition.
- `template.html` and `build_composition.py`: regenerate the composition and measured chart from the repository's current corpus and app captures.
- `source-provenance.json`: hashes identifying the corpus and captured UI sources.
- `render-verification.json`: final media metadata, decoder result and visual QA record.
- `brag-plan.md`, `composition-brief.md`, and `composition/DESIGN.md`: editorial and visual direction.
- `share-copy.txt`: short caption; it has not been posted.

The finished video is attached to the [v0.1.0 GitHub release](https://github.com/nazeeh111/SILICONPILOT/releases/tag/v0.1.0) as `SILICONPILOT-demo.mp4`; the Git source retains its poster, editable composition and verification evidence.

To refresh evidence after a new benchmark run, capture the running app into `docs/media/`, then run `python docs/demo/build_composition.py` from the repository root. The builder freezes real records into `composition/assets/measurements.json` and creates the chart directly from those records. Review the captures against their measurement edition before rendering.

Rendering uses Hyperframes 0.8.33, Chrome, Node >=22 and FFmpeg. The editable source also works with the upstream CLI (`npx hyperframes@0.8.33 lint docs/demo/composition`, inspect and render). The recorded release was produced with the user's installed pinned local runner. That runner's path is machine-specific, and installing or using it is not a requirement for the FPGA compiler.

The GSAP 3.14.2 runtime is included for this free local composition under the [GSAP standard license](https://gsap.com/standard-license); its original license header is preserved. This asset is separate from SILICONPILOT's Apache-2.0-licensed original code. Product captures, diagram source and chart data are original project artifacts, subject to the dataset attribution documented elsewhere in the repository.
