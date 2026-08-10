"""
condense_log.py -- produces a token-optimized twin of a raw Blender
correctness-test log for pasting back to an LLM. Never touches the raw
log; writes a second, shorter file alongside it.

Adapted from a sibling performance-pipeline script (log_condenser.py) --
same core design, ported to this pipeline's actual noise source (chatty
exporter C++ logging: "io.alembic | WARNING Bounding box is null!" and
equivalents from USD/FBX/glTF) instead of that one's REPEAT_TRIALS/
SUMMARY-block benchmark noise. The UTF-16LE/PowerShell encoding handling
from the original does not apply here (Ubuntu GitHub Actions runner,
plain UTF-8 stdout) and has been dropped rather than carried over unused.

DESIGN, kept identical to the original for the same safety reasons:
 1. A line is NEVER dropped if it contains a high-signal keyword (error,
    exception, traceback, crash, assert, fail), regardless of how often a
    similar-shaped line repeats. This overrides every noise pattern below.
 2. Only an explicit, known-noise pattern list is dropped -- never a
    generic "this repeated N times" rule. Repetition count plays no part
    in the decision, so a script that legitimately prints a repeating
    line (e.g. per-strand or per-frame data) is never at risk of losing
    it just because it looks similar to something else.
 3. Everything from "=== VERSION STAMP ===" to EOF is protected and never
    touched -- that's our own script's meaningful output (ground-truth
    lines, the === CELL RESULT === JSON block), analogous to the SUMMARY
    block protection in the original. Only the noisy pre-amble (Blender
    startup banner, exporter C++ warning spam) before that point is
    subject to filtering.
 4. Runs of 3+ blank lines collapse to 1, outside the protected region.
 5. A footer reports the byte/line reduction and points back at the raw
    log, same as the original.
"""

import re
import sys

ALWAYS_KEEP_SUBSTRINGS = [
    "error", "exception", "traceback", "crash", "assert", "fail",
]

# Known-noisy preamble from Blender/exporter C++ startup and warning spam.
# Extend this list if a new exporter's chatty logging shows up (e.g.
# io.gltf, io.obj) -- add its warning-line prefix here, don't try to
# generalize by repetition count (see module docstring point 2).
NOISE_DROP_PATTERNS = [
    r"^Blender \d+\.\d+",
    r"^Read prefs:",
    r"^Saved session",
    r"^AL lib:",
    r"^Color management:",
    # Exporter C++ warning-log lines, e.g.
    # "00:02.015  io.alembic       | WARNING Bounding box is null!"
    # Matches any io.<format> WARNING line regardless of the specific
    # message text, so it covers USD/FBX/glTF equivalents too without
    # needing a new pattern per warning string.
    r"io\.(alembic|usd|fbx|obj|gltf)\s*\|\s*WARNING",
]
NOISE_RE = [re.compile(p) for p in NOISE_DROP_PATTERNS]

PROTECT_START_RE = re.compile(r"^===\s*VERSION STAMP\s*===")


def _is_always_keep(line):
    low = line.lower()
    return any(s in low for s in ALWAYS_KEEP_SUBSTRINGS)


def _is_noise(line):
    return any(p.search(line) for p in NOISE_RE)


def condense(raw_text):
    """Return (condensed_text, stats_dict). Nothing from
    '=== VERSION STAMP ===' onward is ever dropped or altered. Before that
    point, only lines matching a known-noise pattern are dropped, and only
    if they don't also match an always-keep substring."""
    lines = raw_text.splitlines()
    n = len(lines)

    out = []
    blank_run = 0
    noise_dropped = 0
    protected = False

    for line in lines:
        stripped = line.strip()
        if not protected and PROTECT_START_RE.match(stripped):
            protected = True

        if not protected and _is_noise(line) and not _is_always_keep(line):
            noise_dropped += 1
            continue

        if stripped == "" and not protected:
            blank_run += 1
            if blank_run > 1:
                continue
        else:
            blank_run = 0

        out.append(line)

    condensed_text = "\n".join(out)
    stats = {
        "original_lines": n,
        "condensed_lines": len(out),
        "original_bytes": len(raw_text.encode("utf-8", errors="ignore")),
        "condensed_bytes": len(condensed_text.encode("utf-8", errors="ignore")),
        "noise_lines_dropped": noise_dropped,
    }
    return condensed_text, stats


def condense_file(raw_log_path, condensed_out_path, raw_log_display_path=None):
    with open(raw_log_path, "r", encoding="utf-8", errors="replace") as f:
        raw_text = f.read()
    condensed_text, stats = condense(raw_text)

    pct = 0.0
    if stats["original_bytes"]:
        pct = 100.0 * (1 - stats["condensed_bytes"] / stats["original_bytes"])

    footer = (
        "\n\n----\n"
        f"[condense_log] {stats['original_lines']} lines / "
        f"{stats['original_bytes']} bytes -> {stats['condensed_lines']} lines / "
        f"{stats['condensed_bytes']} bytes ({pct:.0f}% smaller). "
        f"{stats['noise_lines_dropped']} boilerplate line(s) dropped. "
        f"Nothing from '=== VERSION STAMP ===' onward was touched.\n"
        f"Full raw log: {raw_log_display_path or raw_log_path}\n"
    )
    final_text = condensed_text + footer

    with open(condensed_out_path, "w", encoding="utf-8") as f:
        f.write(final_text)

    stats["reduction_pct"] = pct
    return final_text, stats


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python condense_log.py path/to/output.log")
        sys.exit(1)
    path = sys.argv[1]
    out_path = path.rsplit(".", 1)[0] + "_condensed.txt"
    text, stats = condense_file(path, out_path)
    print(f"Wrote {out_path}")
    print(f"{stats['original_lines']} -> {stats['condensed_lines']} lines "
          f"({stats['reduction_pct']:.0f}% smaller)")
