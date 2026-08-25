#!/usr/bin/env python3
"""Behavioural check of guard_bash's build-rule scoping. Both directions."""
import json, subprocess, sys

GUARD = "/home/joh/Documents/sin_and_punishment/sin-punishment-recompiled/scripts/guard_bash.py"
PROJ = "/home/joh/Documents/sin_and_punishment/sin-punishment-recompiled"
BUILD = "cmake " + "--build " + "build --target x"      # assembled, so this file
                                                        # is not itself a needle

def run(cmd):
    p = subprocess.run([sys.executable, GUARD], input=json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": cmd}}),
        capture_output=True, text=True)
    return p.returncode, (p.stderr or "").strip()

cases = [
    # (label, command, expected_rc)
    ("OUR tree, no cd — must still REFUSE",
     BUILD, 2),
    ("OUR tree, cd inside the repo — must still REFUSE",
     f"cd {PROJ}/lib && {BUILD}", 2),
    ("OUR tree, relative cd inside — must still REFUSE",
     f"cd lib && {BUILD}", 2),
    ("THIRD-PARTY tree, cd outside — must ALLOW",
     f"cd ~/Documents/sin_and_punishment/tools/ares-64 && {BUILD}", 0),
    ("THIRD-PARTY absolute path — must ALLOW",
     f"cd /tmp && {BUILD}", 0),
    ("pgrep in a wait-loop is NOT blocked (deliberately not a rule)",
     'until ! pgrep -f "desktop-ui/ares"; do sleep 5; done', 0),
    ("the destructive kill-by-pattern form is STILL blocked",
     'pk' + 'ill -f SinPunishmentRecompiled', 2),
]

fails = 0
for label, cmd, want in cases:
    rc, err = run(cmd)
    ok = rc == want
    print(("ok    " if ok else "FAIL  ") + label + ("" if ok else f"  -- rc={rc} want={want}"))
    if not ok:
        fails += 1
        if err:
            print("        " + err.splitlines()[0][:110])

print(f"\n{len(cases)-fails}/{len(cases)} controls pass")
sys.exit(1 if fails else 0)
