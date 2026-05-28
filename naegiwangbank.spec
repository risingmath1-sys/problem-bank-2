# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — 내기왕문제은행 .exe 빌드.

build.bat 이 호출. 직접 호출은 비권장 (버전 자동 증가가 동작 안 함).

데이터 파일:
  - templates/      : HWP 템플릿
  - backend/*.json  : 단원분류 등 설정
  - backend/naegiwangbank-firebase-adminsdk-*.json : ★Phase 2에서 분리 예정
  - backend/indexers/*.json : 인덱서 매핑

데이터/숨김 import 누락 시 .exe 실행은 되지만 특정 기능에서 ImportError → 빌드 후 반드시 스모크 테스트.
"""
import os

block_cipher = None

# 데이터 파일 (소스, 빌드 내 상대 경로)
datas = [
    ('templates', 'templates'),
    ('backend/curriculum_config.json', 'backend'),
    ('backend/unit_hierarchy.json', 'backend'),
    ('backend/registration_log.json', 'backend'),
    ('backend/indexers/naesin_n_unit_map.json', 'backend/indexers'),
    ('backend/logo.png', 'backend'),
    # ★ Phase 2 완료: admin SDK 키는 더 이상 번들에 포함하지 않음.
    #   탐색 순서는 backend/firebase_init.py 참조
    #   (env var → .exe 옆 → %APPDATA%\naegiwangbank\firebase-key.json)
    ('firestore.rules', '.'),
    ('firebase.json', '.'),
]

# 데이터 파일 존재 검증 (오타/누락 조기 감지)
for src, _ in datas:
    if not os.path.exists(src):
        raise FileNotFoundError(f"datas: 누락된 파일/폴더: {src}")

# 숨김 import — PyInstaller 가 정적 분석으로 못 찾는 모듈
hiddenimports = [
    # Firebase Admin SDK
    'firebase_admin',
    'firebase_admin.credentials',
    'firebase_admin.firestore',
    'firebase_admin.auth',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'google.cloud.firestore_v1.base_query',
    'google.api_core',
    'google.auth',
    'grpc',

    # HWP 자동화
    'win32com',
    'win32com.client',
    'pythoncom',
    'pywintypes',
    'pyhwpx',

    # 백엔드 모듈 (동적 import 가능성 있는 것들)
    'backend',
    'backend.indexers',
    'backend.indexers.naesin_ang',
    'backend.indexers.naesin_n',
    'backend.indexers.suneung_special',
    'backend.indexers.suneung_wansung',
    'backend.indexers.mock_exam',
]

a = Analysis(
    ['backend/main_gui.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 빌드 크기 축소 (개발용 도구)
        'pytest',
        'IPython',
        'jupyter',
        'matplotlib.tests',
        'numpy.tests',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='naegiwangbank',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # UPX 압축 끔 — Windows Defender 오탐 방지
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # --windowed (콘솔 창 숨김)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
