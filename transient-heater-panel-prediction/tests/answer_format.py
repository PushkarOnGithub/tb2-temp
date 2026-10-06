"""Read and validate the agent's /app/answer.json.

Standard library only and imports no truth, so the grader (python3 -I -S) and
the pytest report share one reader and therefore one contract.  The file is
opened with O_NOFOLLOW after an lstat, so a symlink, FIFO or device at the
answer path is rejected without being read, and nothing is ever evaluated as
code: the only parser is json.loads with NaN/Infinity and duplicate keys refused.
"""

import json
import math
import os
import stat

MAX_BYTES = 65536
K_RANGE = (0.01, 100.0)            # W m^-1 K^-1
RHO_C_RANGE = (1.0e5, 1.0e8)       # J m^-3 K^-1
TOP_KEYS = ("k", "rho_c", "predictions")


class ContractError(Exception):
    """The submission violates a stated requirement of the output contract."""


def _no_constants(token):
    raise ContractError("non-finite JSON constant %s is not allowed" % token)


def _unique_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ContractError("duplicate key %r" % key)
        obj[key] = value
    return obj


def read_bytes(path):
    """Return the raw bytes of a regular, bounded file at ``path``."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        raise ContractError("%s does not exist" % path)
    if not stat.S_ISREG(st.st_mode):
        raise ContractError("%s must be a regular file (not a symlink, FIFO or device)" % path)
    if st.st_size > MAX_BYTES:
        raise ContractError("%s is %d bytes; the limit is %d" % (path, st.st_size, MAX_BYTES))
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ContractError("cannot open %s: %s" % (path, exc.strerror))
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ContractError("%s must be a regular file" % path)
        raw = os.read(fd, MAX_BYTES + 1)
    finally:
        os.close(fd)
    if len(raw) > MAX_BYTES:
        raise ContractError("%s exceeds %d bytes" % (path, MAX_BYTES))
    return raw


def parse(raw):
    """Strict JSON parse of the submission bytes into a Python object."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ContractError("answer.json is not UTF-8 text")
    try:
        return json.loads(text, parse_constant=_no_constants, object_pairs_hook=_unique_pairs)
    except ContractError:
        raise
    except (ValueError, RecursionError) as exc:
        raise ContractError("answer.json is not valid JSON: %s" % (str(exc)[:200],))


def number(value, field):
    """A finite JSON number (int or float, never bool or string) as float."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError("%s must be a JSON number, got %s" % (field, type(value).__name__))
    try:
        x = float(value)
    except OverflowError:
        raise ContractError("%s is out of floating-point range" % field)
    if not math.isfinite(x):
        raise ContractError("%s must be finite" % field)
    return x


def validate(doc, expected_ids):
    """Check the contract and return {'k', 'rho_c', 'predictions'} as floats."""
    if not isinstance(doc, dict):
        raise ContractError("answer.json must contain a JSON object")
    keys = set(doc)
    if keys != set(TOP_KEYS):
        missing = sorted(set(TOP_KEYS) - keys)
        extra = sorted(keys - set(TOP_KEYS))
        raise ContractError("top-level keys must be exactly %s (missing %s, extra %s)"
                            % (list(TOP_KEYS), missing, extra))
    k = number(doc["k"], "k")
    if not K_RANGE[0] <= k <= K_RANGE[1]:
        raise ContractError("k = %r W/(m K) is outside [%g, %g]" % (k, K_RANGE[0], K_RANGE[1]))
    rho_c = number(doc["rho_c"], "rho_c")
    if not RHO_C_RANGE[0] <= rho_c <= RHO_C_RANGE[1]:
        raise ContractError("rho_c = %r J/(m^3 K) is outside [%g, %g]" % (rho_c, RHO_C_RANGE[0], RHO_C_RANGE[1]))
    preds = doc["predictions"]
    if not isinstance(preds, dict):
        raise ContractError("predictions must be a JSON object")
    if set(preds) != set(expected_ids):
        missing = sorted(set(expected_ids) - set(preds))
        extra = sorted(set(preds) - set(expected_ids))
        raise ContractError("predictions keys must be exactly the scenario ids (missing %s, extra %s)"
                            % (missing, extra[:10]))
    out = {sid: number(preds[sid], "predictions.%s" % sid) for sid in expected_ids}
    return {"k": k, "rho_c": rho_c, "predictions": out}


def read_answer(path, expected_ids):
    return validate(parse(read_bytes(path)), expected_ids)
