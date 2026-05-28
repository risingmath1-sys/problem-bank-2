"""일괄작업 후 안전 동기화 + 검증 헬퍼.

언제 쓰나:
  - Firestore 에 직접 batch.update 등 우회 쓰기 후
  - 캐시 stale 의심될 때
  - 정기 점검

실행:
  python backend/resync_all.py            # cache full_sync + audit
  python backend/resync_all.py --skip-audit   # sync 만
  python backend/resync_all.py --quick    # incremental + audit

수행:
  1. cache.full_sync() — Firestore 전체 다시 받기
  2. audit_db.audit() — 정합성 검증 (subject↔unit_code, Z코드, mapped_unit_code 잔재)
  3. 결과 리포트
"""
import sys, io, argparse, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-audit", action="store_true", help="audit 스킵, sync만 실행")
    parser.add_argument("--quick", action="store_true", help="full_sync 대신 incremental_sync")
    parser.add_argument("--source", default="", help="audit 시 특정 소스만 (예: NAESIN_N)")
    args = parser.parse_args()

    from backend.firebase_init import init_admin_sdk
    try:
        init_admin_sdk()
    except Exception:
        pass

    from server.services.engine import get_engine
    engine = get_engine()

    print("=" * 60)
    print("resync_all — 캐시 동기화 + 정합성 검증")
    print("=" * 60)
    print(f"cache: {engine.cache.cache_path}")
    print(f"current count: {engine.cache.count()}")
    print()

    # 1. 캐시 동기화
    t0 = time.time()
    if args.quick:
        print("[1/2] incremental_sync (변경분만)...")
        n = engine.cache.incremental_sync()
    else:
        print("[1/2] full_sync (전체 재다운로드)...")
        n = engine.cache.full_sync()
    print(f"  완료: {n}건 / {time.time()-t0:.1f}s")
    print(f"  cache count: {engine.cache.count()}")
    print()

    # 2. 정합성 검사
    if args.skip_audit:
        print("[2/2] audit 스킵")
        return 0

    print("[2/2] audit_db 정합성 검사...")
    from backend.audit_db import audit
    issues = audit(args.source, "")
    return 0 if issues == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
