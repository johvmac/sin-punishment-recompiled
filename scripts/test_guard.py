#!/usr/bin/env python3
"""Control matrix for scripts/guard_bash.py (T40).

Lives in a file rather than a heredoc because the guard inspects the literal
text of any Bash command -- a matrix containing refusal strings as *test data*
is indistinguishable from one containing them as intent, so the guard correctly
refuses to run it inline. That is the guard working, not a problem to route
around, so the test moved to a file instead.
"""
import json
import subprocess
import sys

B = "build/SinPunishmentRecompiled"
KILL = "pk" + "ill -f"          # split so this file is not itself a tripwire
CMAKE = "cmake --build build"

CASES = [
    # (command, expected returncode: 2 = refuse, 0 = allow, label)
    (f"echo {B}",                          2, "bare launch"),
    (f"ls >/dev/null; echo {B}",           2, "THE BUG: safe token in a DIFFERENT statement"),
    (f"./{B}",                             2, "explicit ./ launch"),
    (f"sha256sum foo; echo {B}",           2, "sha256sum cannot vouch for echo"),
    (f"echo {B} | head -1",                2, "piped launch"),
    (f"{KILL} something",                  2, "pkill -f"),
    (f"ls; {KILL} something",              2, "pkill hidden behind ls"),
    (CMAKE,                                2, "direct cmake build"),
    (f"ls && {CMAKE} -j8",                 2, "cmake hidden behind ls"),

    (f"strings {B} | grep -c SNP",         0, "strings inspection"),
    (f"sha256sum {B} | cut -c1-16",        0, "hashing the binary"),
    (f"ls -l {B}",                         0, "listing the binary"),
    (f"stat -c%y {B}",                     0, "stat the binary"),
    (f"cp {B} /tmp/x",                     0, "copying the binary"),
    (f"gdb -batch --args {B}",             0, "gdb: deliberate and supervised"),
    (f"echo hi; sha256sum {B}",            0, "safe use beside an unrelated echo"),
    ("scripts/run_game.sh 25 /tmp/x.log",  0, "the sanctioned runner"),
    ("scripts/build.sh --no-recomp",       0, "the sanctioned builder"),
    ("echo hello world",                   0, "unrelated command"),

    # The gdb wrappers take the binary as an ARGUMENT, and `\bgdb\b` does not
    # match `gdb_watch.sh` because `_` is a word character. That refused the
    # project's own supervised debugger tools -- the case most likely to make
    # someone reach for a bypass.
    (f"scripts/gdb_watch.sh 0x8013C278 140 230 /tmp/w.log {B} '== 0x02000000'",
     0, "gdb_watch.sh with an explicit binary argument"),
    (f"scripts/gdb_fault.sh 210 /tmp/f.log {B}",
     0, "gdb_fault.sh with an explicit binary argument"),
    (f"scripts/gdb_threads.sh 90 /tmp/t.log {B}",
     0, "gdb_threads.sh with an explicit binary argument"),

    # ...but the exemption must stay inside its own statement (T40).
    (f"scripts/gdb_watch.sh 0x1 1 1 /tmp/w.log; ./{B}",
     2, "a sanctioned runner must NOT vouch for a launch beside it"),

    # TRUNCATED STDERR (A198). The failure this was built from, verbatim:
    ("scripts/rom_disasm.py 0x800F9424 0x800F9460 2>&1 | tail -25",
     2, "the exact command that dropped A196's overlay warning"),
    ("scripts/ledger.py --index 2>&1 | head -20",
     2, "head truncates a merged stream just as silently as tail"),

    # THE OVER-REFUSAL CONTROLS. Without these, the rule above passes on a guard
    # that refuses everything -- which would be worse than no guard, because it
    # gets switched off. Each names a reason the shape is NOT the hazard:
    ("scripts/ledger.py --index | tail -20",
     0, "no 2>&1 -- stderr still reaches the terminal, nothing is dropped"),
    ("cat /tmp/some.log 2>&1 | tail -20",
     0, "no project script -- not this guard's business"),
    ("scripts/ledger.py --index 2>&1 | grep A99",
     0, "grep drops by CONTENT, a choice you make -- documented scope limit"),
    ('scripts/ledger.py --index >"$O" 2>"$E"; tail -20 "$O"; cat "$E"',
     0, "THE PRESCRIBED IDIOM must not be refused by the rule prescribing it"),

    # ...and the pipeline boundary must hold, the same way statements do (T40).
    ("scripts/ledger.py --index >/tmp/o.txt 2>/tmp/e.txt; tail -3 /tmp/other.log",
     0, "a `tail` in a LATER pipeline must not condemn an earlier one"),
]


def main():
    bad = 0
    for cmd, want, label in CASES:
        p = subprocess.run(
            [sys.executable, "scripts/guard_bash.py"],
            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
            capture_output=True, text=True,
        )
        ok = p.returncode == want
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  want={want} got={p.returncode}  {label}")
    print(f"\n{len(CASES) - bad}/{len(CASES)} correct")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
