"""Held-out configurations, generated only inside the verifier image.

None of these configurations, nor their answers, appear in any file the agent
receives.  Generation is a pure function of HELDOUT_SEED (counter-based
SHA-256 stream), so identical runs grade identically.
"""

import hashlib

HELDOUT_SEED = "vsf-heldout-2026-10"
N_HELDOUT = 40


def _u01(counter):
    h = hashlib.sha256(("%s|%d" % (HELDOUT_SEED, counter)).encode("ascii")).digest()
    return (int.from_bytes(h[:8], "big") + 0.5) / 18446744073709551616.0


def heldout_configurations(admissible):
    """Return N_HELDOUT configurations as (added_mass[4], stiffness_factor[4]).

    ``admissible(added_mass, stiffness_factor)`` lets the deriver reject draws
    whose true natural frequencies are too close to order unambiguously; a
    rejected draw is skipped deterministically.
    """
    out = []
    c = 0
    while len(out) < N_HELDOUT:
        if c > 100000:
            raise RuntimeError("held-out generator exhausted")
        u = [_u01(c * 16 + i) for i in range(16)]
        c += 1
        n_loaded = 1 if u[0] < 0.5 else 2
        floors = [0, 1, 2, 3]
        chosen = []
        for i in range(n_loaded):
            idx = min(int(u[1 + i] * len(floors)), len(floors) - 1)
            chosen.append(floors.pop(idx))
        added = [0.0] * 4
        for i, f in enumerate(chosen):
            added[f] = round(0.3 + 2.2 * u[3 + i], 2)
        factor = [1.0] * 4
        if u[5] < 0.5:
            s = min(int(u[6] * 4), 3)
            factor[s] = round(0.6 + 1.0 * u[7], 3)
        cfg = (added, factor)
        if cfg in out or not admissible(added, factor):
            continue
        out.append(cfg)
    return out
