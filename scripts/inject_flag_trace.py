#!/usr/bin/env python3
"""Inject SNP flag-protocol tracing into the generated pump/dispatcher code."""
import glob

injections = [
    ("boot_func_80025E44", "// 0x80025F7C: lbu         $a0, -0x756B($at)",
     '    if (getenv("SNP_FLAG")) fprintf(stderr, "[flag] pump reads 0x%02X\\n", (unsigned)(uint8_t)ctx->r4);\n'),
    ("boot_func_800263CC", "// 0x8002655C: lbu         $v1, -0x756B($at)",
     '    if (getenv("SNP_FLAG")) fprintf(stderr, "[flag] disp reads 0x%02X\\n", (unsigned)(uint8_t)ctx->r3);\n'),
    ("boot_func_800263CC", "// 0x8002656C: sb          $zero, -0x756B($at)",
     '    if (getenv("SNP_FLAG")) fprintf(stderr, "[flag] disp clears\\n");\n'),
    ("boot_func_800263CC", "// 0x80026564: sb          $v1, -0x756C($at)",
     '    if (getenv("SNP_FLAG")) fprintf(stderr, "[flag] disp saves prev\\n");\n'),
]

for path in sorted(glob.glob("RecompiledFuncs/funcs_*.c")):
    s = open(path).read()
    orig = s
    for fn, comment, insert in injections:
        idx = s.find("RECOMP_FUNC void %s(" % fn)
        if idx == -1:
            continue
        end = s.find("RECOMP_FUNC", idx + 10)
        body = s[idx:end if end != -1 else len(s)]
        if comment in body:
            ci = body.find(comment)
            stmt_end = body.find("\n", ci)
            nxt = body.find("\n", stmt_end + 1)
            body = body[:nxt+1] + insert + body[nxt+1:]
            s = s[:idx] + body + s[end:]
    if s != orig:
        if "#include <stdio.h>" not in s:
            s = '#include <stdio.h>\n' + s
        open(path, "w").write(s)
        print("patched", path)
print("done")
