"""Reproducible industrial-camera feature classifier, with training-only scaling.

The circuit accepts four already standardized wavelet features, not pixels.
Training is optional; importing a model and integer inference need no sklearn.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SOURCE_URL = "https://archive.ics.uci.edu/static/public/267/banknote+authentication.zip"
DATASET_CITATION = (
    "Lohweg, V. (2012). Banknote Authentication [Dataset]. "
    "UCI Machine Learning Repository. https://doi.org/10.24432/C55P57."
)
SEED = 20261025


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_dataset(root: str | Path, split: str = "test") -> tuple[list[list[float]], list[int]]:
    """Load standardized float features and labels using saved row-index splits.

    Valid splits are train, validation, test and all. The transform is estimated
    on training rows only and stored in models/dataset_manifest.json.
    """
    root = Path(root)
    manifest = json.loads((root / "models/dataset_manifest.json").read_text())
    raw = root / "data/banknote.csv"
    if sha256(raw) != manifest["csv_sha256"]:
        raise ValueError("Dataset bytes differ from the training manifest")
    rows = [[float(x) for x in line.split(",")] for line in raw.read_text().splitlines() if line]
    if split == "all":
        indices = list(range(len(rows)))
    elif split in ("train", "validation", "test"):
        indices = manifest["split_indices"][split]
    else:
        raise ValueError(f"Unknown dataset split {split!r}")
    mean, scale = manifest["preprocessing"]["mean"], manifest["preprocessing"]["scale"]
    x = [[(rows[i][j] - mean[j]) / scale[j] for j in range(4)] for i in indices]
    return x, [int(rows[i][-1]) for i in indices]


def train_models(root: str | Path, widths: tuple[int, ...] = (4, 8, 12)) -> dict[str, Any]:
    """Train dense/ReLU networks and export plain JSON, deterministic on pinned stack.

    Two output scores are the symmetric binary logit pair. Positive scaling of
    logits preserves class decisions while avoiding unnecessary fixed-point
    saturation. Hidden-unit rescaling preserves the real-valued network exactly.
    Validation and test rows never fit scaling, weights or rescaling factors.
    """
    import numpy as np
    import sklearn
    from sklearn.model_selection import train_test_split
    from sklearn.neural_network import MLPClassifier

    root = Path(root)
    raw = root / "data/banknote.csv"
    data = np.loadtxt(raw, delimiter=",")
    if data.shape != (1372, 5) or not np.isfinite(data).all():
        raise ValueError("Expected the complete finite 1372-row, four-feature UCI dataset")
    x, y = data[:, :4], data[:, 4].astype(int)
    if set(y) != {0, 1}:
        raise ValueError("Expected binary class labels")
    trainval, test = train_test_split(np.arange(len(y)), test_size=0.2, random_state=SEED, stratify=y)
    train, validation = train_test_split(trainval, test_size=0.25, random_state=SEED, stratify=y[trainval])
    # Divide standardized features by 2 so ordinary samples fit Q3.F formats.
    mean = x[train].mean(axis=0)
    scale = x[train].std(axis=0) * 2.0
    z = (x - mean) / scale
    preprocessing = {"kind": "train_only_standardization", "mean": mean.tolist(), "scale": scale.tolist(),
                     "formula": "(raw_feature - mean) / scale", "implemented_in_hardware": False}
    manifest: dict[str, Any] = {
        "dataset": "UCI Banknote Authentication", "doi": "10.24432/C55P57", "source_url": SOURCE_URL,
        "citation": DATASET_CITATION, "license": "CC-BY-4.0", "rows": len(y),
        "features": ["variance", "skewness", "curtosis", "entropy"],
        "sensor_origin": "Wavelet features extracted from industrial-camera banknote images",
        "csv_sha256": sha256(raw), "seed": SEED, "preprocessing": preprocessing,
        "split_indices": {"train": sorted(train.tolist()), "validation": sorted(validation.tolist()), "test": sorted(test.tolist())},
        "split_sizes": {"train": len(train), "validation": len(validation), "test": len(test)},
        "versions": {"numpy": np.__version__, "scikit_learn": sklearn.__version__},
        "evaluation_caveat": "Stratified row split; source provides no specimen/group IDs. This is not a new-camera or unseen-specimen generalization claim.",
        "models": [],
    }
    (root / "models").mkdir(exist_ok=True)
    for width in widths:
        estimator = MLPClassifier(hidden_layer_sizes=(width,), activation="relu", solver="lbfgs", alpha=0.1,
                                  max_iter=3000, random_state=SEED + width, tol=1e-9)
        estimator.fit(z[train], y[train])
        w1, w2 = [v.copy() for v in estimator.coefs_]
        b1, b2 = [v.copy() for v in estimator.intercepts_]
        activation = np.maximum(0.0, z[train] @ w1 + b1)
        factors = np.maximum.reduce((activation.max(axis=0) / 2.5, np.abs(w1).max(axis=0) / 2.5, np.abs(b1) / 2.5, np.full(width, 0.1)))
        w1 /= factors[None, :]
        b1 /= factors
        w2 *= factors[:, None]
        # Clip risks are observable in integer accuracy, never silently hidden.
        logits = (np.maximum(0.0, z[train] @ w1 + b1) @ w2 + b2).ravel()
        logit_scale = 2.5 / max(float(np.abs(logits).max()), float(np.abs(w2).max()), 1.0)
        w2 = np.concatenate((-w2 / 2, w2 / 2), axis=1) * logit_scale
        b2 = np.concatenate((-b2 / 2, b2 / 2)) * logit_scale
        model = {"name": f"banknote_4x{width}x2", "input_size": 4,
                 "layers": [{"op": "dense", "weights": w1.T.tolist(), "bias": b1.tolist()},
                            {"op": "relu"}, {"op": "dense", "weights": w2.T.tolist(), "bias": b2.tolist()}],
                 "metadata": {"dataset": "UCI Banknote Authentication", "dataset_sha256": sha256(raw),
                              "seed": SEED + width, "preprocessing": preprocessing,
                              "training_rows": len(train), "validation_rows": len(validation), "test_rows": len(test)}}
        file = root / "models" / f"banknote_4x{width}x2.json"
        file.write_text(json.dumps(model, indent=2) + "\n")
        predictions = np.argmax(np.maximum(0.0, z @ w1 + b1) @ w2 + b2, axis=1)
        metrics = {"name": model["name"], "model_sha256": sha256(file), "hidden_units": width,
                   "float_accuracy": {split: float(np.mean(predictions[ids] == y[ids])) for split, ids in
                                      (("train", train), ("validation", validation), ("test", test))},
                   "iterations": int(estimator.n_iter_), "training_loss": float(estimator.loss_),
                   "max_abs_weight": float(max(np.abs(w1).max(), np.abs(w2).max()))}
        manifest["models"].append(metrics)
    (root / "models/dataset_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest



def evaluate_accuracy(model: dict[str, Any], config: Any, root: str | Path, split: str = "validation") -> dict[str, Any]:
    """Measure bit-exact integer task accuracy; use validation during search."""
    from .model import quantize
    from .reference import evaluate_integer, quantize_input
    features, labels = load_dataset(root, split)
    quantized = quantize(model, config)
    correct = 0
    ties = 0
    for row, label in zip(features, labels):
        scores = evaluate_integer(quantized, quantize_input(row, config))
        # Python's max resolves score ties toward the first class, consistently.
        predicted = max(range(len(scores)), key=lambda i: scores[i])
        correct += predicted == label
        ties += len(set(scores)) != len(scores)
    return {"split": split, "samples": len(labels), "correct": correct,
            "accuracy": correct / len(labels), "tied_scores": ties}

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("train", "inspect"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    if args.action == "train":
        manifest = train_models(args.root)
        print(json.dumps({"split_sizes": manifest["split_sizes"], "models": manifest["models"]}, indent=2))
    else:
        print((args.root / "models/dataset_manifest.json").read_text())


if __name__ == "__main__":
    main()
