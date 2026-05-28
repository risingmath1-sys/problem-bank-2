"""NAESIN_N 재인덱싱 — 로컬 파서 직접 호출."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.firebase_init import init_admin_sdk
try:
    init_admin_sdk()
except Exception:
    pass

from backend.hwp_metadata_parser_v2 import HWPMetadataParserV2
from backend.indexer_registry import get_indexer
from server.services.engine import get_engine

# 재인덱싱 대상 폴더
target_path = r"G:\문제은행\문제들\100생성문제\10-1공수1"

# 설정
config_path = PROJECT_ROOT / "backend" / "curriculum_config.json"
output_dir = PROJECT_ROOT / "backend" / "indexed_results"
output_dir.mkdir(parents=True, exist_ok=True)

print(f"Target: {target_path}")
print(f"Config: {config_path}")
print(f"Output: {output_dir}")
print()

# 파서 초기화
engine = get_engine()
parser = HWPMetadataParserV2(
    output_dir=str(output_dir),
    config_path=str(config_path),
    engine=engine,
)

# 진행 콜백
def on_progress(msg):
    print(f"[진행] {msg}")

# 재인덱싱 실행
print("=== 재인덱싱 시작 ===\n")
result = parser.process(
    path=target_path,
    is_folder=True,
    source="NAESIN_N",
    force_reindex=True,
    stealth_mode=True,
    common_meta={},
    on_progress=on_progress,
)

print(f"\n=== 재인덱싱 완료 ===")
print(f"Result: {result}")

