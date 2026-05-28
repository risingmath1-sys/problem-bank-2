# -*- coding: utf-8 -*-
"""build.bat 내부 헬퍼. version.txt 의 PATCH 를 +1 하고 새 버전을 stdout 에 출력."""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
VFILE = os.path.join(ROOT, "version.txt")

if not os.path.exists(VFILE):
    with open(VFILE, "w", encoding="utf-8") as f:
        f.write("1.0.0\n")

with open(VFILE, "r", encoding="utf-8") as f:
    cur = f.read().strip()

try:
    maj, mnr, pat = (int(x) for x in cur.split("."))
except ValueError:
    print(f"ERROR: version.txt 형식 불량: {cur!r}", file=sys.stderr)
    sys.exit(1)

pat += 1
new = f"{maj}.{mnr}.{pat}"
with open(VFILE, "w", encoding="utf-8") as f:
    f.write(new + "\n")

# build.bat 가 "for /f" 로 캡처 — 줄바꿈 없는 단일 라인 출력
sys.stdout.write(new)
