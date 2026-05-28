"""
IndexerRegistry - 소스 코드 → 인덱서 클래스 매핑.

새 소스 추가 시 이 파일에만 1줄 추가하면 된다.
main_gui.py, indexer_base.py 수정 불필요.
"""

try:
    from backend.indexers.naesin_ang import NaesinAngIndexer
    from backend.indexers.naesin_n import NaesinNIndexer
    from backend.indexers.suneung_special import SuneungSpecialIndexer
    from backend.indexers.suneung_wansung import SuneungWansungIndexer
    from backend.indexers.mock_exam import MockExamIndexer
    from backend.indexer_base import BaseIndexer
except ImportError:
    from indexers.naesin_ang import NaesinAngIndexer
    from indexers.naesin_n import NaesinNIndexer
    from indexers.suneung_special import SuneungSpecialIndexer
    from indexers.suneung_wansung import SuneungWansungIndexer
    from indexers.mock_exam import MockExamIndexer
    from indexer_base import BaseIndexer


REGISTRY = {
    "NAESIN_A":         NaesinAngIndexer,
    "NAESIN_N":         NaesinNIndexer,
    "SUNEUNG_SPECIAL":  SuneungSpecialIndexer,
    "SUNEUNG_COMPLETE": SuneungWansungIndexer,
    "MOCK_EXAM":        MockExamIndexer,
    # "TEXTBOOK":         TextbookIndexer,         # 추후 추가
}


def get_indexer(source_type: str):
    """
    소스 코드에 해당하는 인덱서 인스턴스 반환.
    미구현 소스는 None 반환 → UI에서 '개발 중' 화면 표시.
    """
    cls = REGISTRY.get(source_type)
    if cls is None:
        return None
    return cls()
