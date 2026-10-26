# Camera-feature classifier and data protocol

The demonstration uses [Volker Lohweg's Banknote Authentication dataset](https://archive.ics.uci.edu/dataset/267/banknote+authentication), UCI DOI [10.24432/C55P57](https://doi.org/10.24432/C55P57), licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The source consists of 1,372 rows of industrial-camera image features and binary class labels. It contains no raw images or specimen identities.

The four circuit inputs are wavelet variance, wavelet skewness, wavelet curtosis, and image entropy. Host software applies `(raw_feature - mean) / scale`, with mean and scale saved in `models/dataset_manifest.json`. Scale is twice each training feature's standard deviation. The FPGA circuit starts at these standardized features; camera acquisition, wavelet extraction and standardization are outside the generated circuit.

## Split and training

The fixed seed is `20261025`. Stratified splitting reserves 275 rows for final test, 275 for validation and 822 for training. All row indices are saved. Training rows alone fit preprocessing, weights and activation rescaling. Search uses validation accuracy. Final test accuracy should be reported after selecting hardware, separately from validation and float-model accuracy.

`src/siliconpilot/dataset.py` trains a one-hidden-layer ReLU MLP using scikit-learn's L-BFGS solver and a fixed weight-decay coefficient of 0.1. It exports plain model JSON with dense weights, biases and metadata. Widths 4 and 12 are provided for hardware-cost generalization tests; width 8 is the main demonstration. Hidden units and binary output logits are positively rescaled to reduce fixed-point saturation while preserving the float classifier. The two scores correspond to class indices 0 and 1; score ties resolve to class 0.

Reproduce from the repository root after installing the pinned environment:

```sh
python -m siliconpilot.dataset train --root .
```

This reads the included, hash-checked source CSV and regenerates three model files and the dataset manifest. The manifest includes data/model hashes, package versions, split indices, training loss and float accuracies. Generated canonical model files are the benchmark inputs; exact retraining hashes can depend on numerical-library versions and platform.

## Observed validation results

These are **integer-reference classification results**, before RTL verification. The release's circuit verification evidence determines whether generated hardware matches the reference. Each entry uses 275 validation rows, signed activations and weights, floor-after-accumulation rounding, saturation, and a 24-bit accumulator.

| Hidden units | Float | 4 bits, F=1 | 6 bits, F=3 | 8 bits, F=5 | 10 bits, F=7 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 4 | 99.27% | 91.64% | 99.27% | 99.27% | 99.27% |
| 8 | 100.00% | 93.45% | 98.55% | 100.00% | 100.00% |
| 12 | 99.27% | 84.00% | 100.00% | 100.00% | 99.27% |

`F` is the number of fractional bits. More precision need not monotonically improve accuracy: quantization can move a score across a classification boundary. Full counts and tie counts are in `models/validation_accuracy.json`.

## Limits

This small demonstration establishes a reproducible compiler workload, not a deployed authentication system. A stratified row split does not prove robustness to new specimen populations, camera changes, image manipulation or fraud. Dataset labels are used exactly as supplied, without inventing names for their numeric meanings. Physical camera/FPGA measurements are not included unless a separate hardware report explicitly records them.

The source archive is retained as `data/banknote-authentication.zip`; the original member is renamed `data/banknote.csv` without numeric changes. `data/provenance.json` records URLs, archive and CSV SHA-256 digests and attribution. No data is downloaded during normal CLI execution or import.
