# Third-party provenance and licensing

SILICONPILOT's source license is separate from the data and external tools below. Upstream licenses were checked on 25 October 2026. Tools are invoked as separate programs; the repository does not relicense them or vendor their executables. If distributing a toolchain bundle, preserve the bundle's complete licenses and notices, including transitive components.

## Redistributed dataset

**Banknote Authentication**, Volker Lohweg (2012), UCI Machine Learning Repository. DOI: [10.24432/C55P57](https://doi.org/10.24432/C55P57). Dataset landing page: [UCI](https://archive.ics.uci.edu/dataset/267/banknote+authentication). Licensed [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).

The original numeric dataset is redistributed as `data/banknote.csv` when present. Changes consist of a filename change; generated model weights, standardization parameters and row splits are derivative analysis artifacts saved separately under `models/`. The source archive and CSV SHA-256 digests are recorded in the dataset manifest when acquired. The original consists of four camera-image-derived features and one class column. This project is not endorsed by UCI or the dataset creator.

Suggested citation:

> Lohweg, V. (2012). Banknote Authentication [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C55P57.

## Toolchain and Python dependencies

| Component | Upstream license | Use / redistribution boundary |
| --- | --- | --- |
| [Yosys](https://github.com/YosysHQ/yosys/blob/main/COPYING) | ISC | External synthesis executable; generated output is not a copy of the compiler source. Technology libraries or bundled dependencies can have separate notices. |
| [nextpnr](https://github.com/YosysHQ/nextpnr/blob/main/COPYING) | ISC | External ECP5 placement/routing; retain Project Trellis/database notices when distributing a toolchain. |
| [Verilator](https://github.com/verilator/verilator#open-license) | LGPL-3.0 or Artistic-2.0 | Optional external simulator. Generated runtime files may carry their own upstream headers and exceptions. |
| [Icarus Verilog](https://github.com/steveicarus/iverilog) | GPL-2.0 | External simulator, if selected; no executable vendored here. |
| [NumPy](https://github.com/numpy/numpy/blob/main/LICENSE.txt) | BSD-3-Clause | Numeric analysis and optional classifier training. |
| [SciPy](https://github.com/scipy/scipy/blob/main/LICENSE.txt) | BSD-3-Clause | Numeric optimization and Gaussian-process support through scikit-learn. |
| [scikit-learn](https://github.com/scikit-learn/scikit-learn/blob/main/COPYING) | BSD-3-Clause | Classifier and surrogate training. |
| [Matplotlib](https://github.com/matplotlib/matplotlib/blob/main/LICENSE/LICENSE) | Matplotlib license, PSF-derived | Locally rendered quantitative figures. |

Package-specific wheels and OSS CAD Suite bundles may include additional third-party components and notices. Installation pins and build manifests identify the actual versions used; this table does not stand in for those manifests.

## Investigated foundations, no vendored code

| Foundation | License | Status |
| --- | --- | --- |
| [hls4ml](https://github.com/fastmachinelearning/hls4ml/blob/main/LICENSE) | Apache-2.0 | Research reference; no converter code copied. |
| [Amaranth](https://github.com/amaranth-lang/amaranth/blob/main/LICENSE.txt) | BSD-2-Clause | Evaluated hardware construction alternative; no code copied. |
| [BoTorch](https://github.com/meta-pytorch/botorch/blob/main/LICENSE) | MIT | Bayesian optimization reference; no requirement to install it for the documented small baseline. |
| [SNAC-Pack / nac-opt](https://github.com/fastmachinelearning/nac-opt/blob/main/LICENSE) | Apache-2.0 | Related work; no source or pretrained models copied. |
| [PaperVizAgent](https://github.com/google-research/papervizagent) | Apache-2.0 | Investigated; model API workflow not used. |

Research papers are cited through links in [research.md](research.md); linking and scholarly attribution do not grant a license to reproduce their figures. All project-specific diagrams should be authored locally, with data charts drawn from this project's retained benchmark records.

## Demo composition

The editable Hyperframes demonstration includes GSAP 3.14.2, with its upstream license header retained in `docs/demo/composition/assets/gsap.min.js`. GSAP uses the free [Standard License](https://gsap.com/standard-license), which is distinct from SILICONPILOT's Apache-2.0 license. No paid API, narration service or purchased media was used. Genuine application screenshots and original technical graphics are generated from this project.

