"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    tp = fp = fn = tn = 0
    for h, j in zip(human, judge):
        if j == POS and h == POS:
            tp += 1
        elif j == POS and h != POS:
            fp += 1
        elif j != POS and h == POS:
            fn += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    cm = confusion(human, judge)
    tp, fp, fn = cm["tp"], cm["fp"], cm["fn"]
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    return (precision, recall)


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    if not human or len(human) != len(judge):
        raise ValueError("Inputs must be non-empty sequences of the same length")
    cm = confusion(human, judge)
    n = len(human)
    p_o = (cm["tp"] + cm["tn"]) / n
    p_h_pos = (cm["tp"] + cm["fn"]) / n
    p_h_neg = (cm["fp"] + cm["tn"]) / n
    p_j_pos = (cm["tp"] + cm["fp"]) / n
    p_j_neg = (cm["fn"] + cm["tn"]) / n
    p_e = p_h_pos * p_j_pos + p_h_neg * p_j_neg
    if p_e >= 1.0 or math.isclose(p_e, 1.0, abs_tol=1e-12):
        raise ValueError("Cohen's kappa is undefined when expected agreement is 1")
    return (p_o - p_e) / (1.0 - p_e)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    denom = sensitivity + specificity - 1.0
    if denom == 0:
        return 0.0
    val = (observed_rate + specificity - 1.0) / denom
    return float(max(0.0, min(1.0, val)))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    import numpy as np
    from scipy import stats as sp_stats

    if len(a) != len(b):
        raise ValueError("Sequences a and b must have the same length")
    if all(x == y for x, y in zip(a, b)):
        return (0.0, 0.0, 0.0)

    a_arr = np.asarray(a, dtype=float)
    b_arr = np.asarray(b, dtype=float)
    d = float(np.mean(a_arr) - np.mean(b_arr))

    def diff_mean(x, y, axis=-1):
        return np.mean(x, axis=axis) - np.mean(y, axis=axis)

    random_state = np.random.default_rng(rng)
    res = sp_stats.bootstrap(
        (a_arr, b_arr),
        diff_mean,
        paired=True,
        method="percentile",
        n_resamples=n_resamples,
        random_state=random_state,
        confidence_level=confidence,
    )
    return (d, float(res.confidence_interval.low), float(res.confidence_interval.high))


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    if k > n or k <= 0 or n <= 0 or c < 0 or c > n:
        raise ValueError(f"Invalid arguments for pass_at_k: n={n}, c={c}, k={k}")
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n."""
    if k > n or k <= 0 or n <= 0 or c < 0 or c > n:
        raise ValueError(f"Invalid arguments for pass_hat_k: n={n}, c={c}, k={k}")
    if c < k:
        return 0.0
    return math.comb(c, k) / math.comb(n, k)
