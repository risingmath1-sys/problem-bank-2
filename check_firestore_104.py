#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')

try:
    from backend.firebase_init import init_admin_sdk
    from firebase_admin import firestore
    init_admin_sdk()
    fs = firestore.client()
except Exception as e:
    print(f"Firestore init 실패: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("=" * 80)
print("[Firestore] 2025-1-1-F 공수1 검색")
print("=" * 80)

# problems 컬렉션에서 검색
try:
    # year=2025, semester=1, exam_type=기말고사
    query = (
        fs.collection("problems")
        .where("year", "==", "2025")
        .where("grade", "==", "1")
        .where("semester", "==", "1")
        .where("source", "==", "NAESIN_A")
        .limit(50)
    )

    docs = list(query.stream())
    print(f"\n2025-1학기 NAESIN_A 검색 결과: {len(docs)}개")

    file_names = set()
    for doc in docs:
        d = doc.to_dict()
        fn = d.get("file_name", "")
        if "2025-1-1-F" in fn or "기말" in d.get("exam_type", ""):
            file_names.add(fn)

    print(f"\n[2025-1-1-F 또는 기말 포함 file_name: {len(file_names)}개]")
    for fn in sorted(file_names):
        print(f"  - {fn}")

except Exception as e:
    print(f"쿼리 실패: {e}")
    import traceback
    traceback.print_exc()
