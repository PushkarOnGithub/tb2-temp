"""Reader for /app/output/model.json, shared by the grader and the pytest report.

Standard library only, and it imports nothing that holds the answer key, so
the grader can use it under ``python3 -I -S``.  The file is parsed as data
with ``json``; nothing in it is ever evaluated.
"""

import json
import math
import os
import stat

ARTIFACT = "/app/output/model.json"
MAX_BYTES = 65536
K_MIN, K_MAX = 1.0, 1.0e9


class ContractError(Exception):
    """The submission violates the output contract stated in the instruction."""


def _no_duplicates(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ContractError("model.json: duplicate key %r" % (key,))
        out[key] = value
    return out


def _reject_constant(name):
    raise ContractError("model.json: %s is not a finite number" % name)


def _number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError("%s must be a JSON number" % field)
    try:
        x = float(value)
    except OverflowError:
        raise ContractError("%s is out of range" % field)
    if not math.isfinite(x):
        raise ContractError("%s must be finite" % field)
    return x


def read_raw(path=ARTIFACT):
    """Return the bytes of the artifact after the file-type and size checks."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        raise ContractError("model.json not found at %s" % path)
    if not stat.S_ISREG(st.st_mode):
        raise ContractError("model.json must be a regular file (not a symlink, FIFO or device)")
    if st.st_size > MAX_BYTES:
        raise ContractError("model.json is larger than %d bytes" % MAX_BYTES)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as fh:
        raw = fh.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ContractError("model.json is larger than %d bytes" % MAX_BYTES)
    return raw


def parse_model(raw):
    """Validate the JSON document and return k as a list of four floats."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ContractError("model.json is not UTF-8 text")
    try:
        obj = json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_reject_constant)
    except ContractError:
        raise
    except (ValueError, RecursionError):
        raise ContractError("model.json is not valid JSON")
    if not isinstance(obj, dict):
        raise ContractError("model.json must hold a JSON object")
    if set(obj) != {"k"}:
        raise ContractError("model.json must have exactly one key, k (found %s)"
                            % ", ".join(sorted(str(x) for x in obj)))
    k = obj["k"]
    if not isinstance(k, list) or len(k) != 4:
        raise ContractError("k must be a list of exactly four numbers")
    ks = [_number(v, "k[%d]" % i) for i, v in enumerate(k)]
    for i, x in enumerate(ks):
        if not K_MIN <= x <= K_MAX:
            raise ContractError("k[%d] must lie in [1, 1e9] N/m" % i)
    return ks


def read_model(path=ARTIFACT):
    return parse_model(read_raw(path))
