from __future__ import annotations

import random
import secrets
from typing import Any


CATALOG_VERSION = "v1"
PREPROCESSORS = ("none", "standard_scaler", "robust_scaler")
REPRESENTATIONS = ("raw_flatten", "summary_statistics", "fft_statistics", "lag_statistics")
METHODS: dict[str, tuple[dict[str, Any], ...]] = {
    "logistic_regression": tuple({"regularization": value} for value in (0.01, 0.1, 1, 10)),
    "linear_svm": tuple({"regularization": value} for value in (0.01, 0.1, 1, 10)),
    "knn_euclidean": tuple({"neighbors": value} for value in (1, 3, 5, 9, 15)),
    "knn_dtw": tuple({"neighbors": value} for value in (1, 3, 5, 9, 15)),
    "random_forest": tuple(
        {"trees": trees, "max_depth": depth}
        for trees in (100, 300, 500)
        for depth in (None, 4, 8, 16)
    ),
    "hist_gradient_boosting": tuple(
        {"learning_rate": rate, "max_depth": depth}
        for rate in (0.03, 0.1, 0.3)
        for depth in (None, 4, 8, 16)
    ),
}


def sample_candidates(k: int, seed: int | None = None) -> dict[str, Any]:
    if k < 1:
        raise ValueError("Random-search candidate count must be positive.")
    actual_seed = secrets.randbits(63) if seed is None else int(seed)
    rng = random.Random(actual_seed)
    catalog = [
        {
            "preprocessor": preprocessor,
            "representation": representation,
            "method": method,
            "parameters": parameters,
        }
        for preprocessor in PREPROCESSORS
        for representation in REPRESENTATIONS
        for method, parameter_sets in METHODS.items()
        for parameters in parameter_sets
    ]
    if k > len(catalog):
        raise ValueError(f"Requested {k} candidates from a catalog of {len(catalog)}.")
    selected = rng.sample(catalog, k)
    return {
        "catalogVersion": CATALOG_VERSION,
        "seed": actual_seed,
        "candidateCount": k,
        "candidates": [
            {"candidateId": f"random-{index:03d}", **candidate}
            for index, candidate in enumerate(selected, start=1)
        ],
    }
