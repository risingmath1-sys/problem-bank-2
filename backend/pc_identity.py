# -*- coding: utf-8 -*-
"""
Phase 1 (배포): PC 인증 — 계정 도용 방지

설계: 배포용설계도.md §2

정책:
  - 1 계정 = 1 PC 고정
  - 첫 로그인 시 자동 등록
  - 다른 PC 시도 → 차단
  - 관리자 계정은 면제

식별: Windows Machine GUID
  HKLM\\SOFTWARE\\Microsoft\\Cryptography\\MachineGuid

기기 변경 (HDD 교체·포맷):
  관리자가 Firestore Console 에서 users/{uid}.device_guid 필드 삭제 →
  사용자 다음 로그인 시 새 PC 로 자동 재등록.
"""
import winreg
from typing import Optional


class DeviceError(Exception):
    """PC 인증 실패."""
    pass


def get_machine_guid() -> str:
    """Windows Machine GUID 읽기. 실패 시 DeviceError."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
        guid = str(guid).strip()
        if not guid:
            raise DeviceError("Machine GUID 가 비어있습니다.")
        return guid
    except FileNotFoundError:
        raise DeviceError("Machine GUID 레지스트리 키를 찾을 수 없습니다.")
    except OSError as e:
        raise DeviceError(f"Machine GUID 읽기 실패: {e}")


def verify_or_register_device(uid: str, role: str) -> None:
    """로그인 흐름에서 호출.

    동작:
      - role == 'admin'           → 통과 (관리자 면제)
      - users/{uid}.device_guid 미설정 → 현재 GUID 등록 + 통과
      - 일치                       → 통과
      - 불일치                     → DeviceError 발생
    """
    if role == "admin":
        return

    current = get_machine_guid()

    from firebase_admin import firestore
    from firebase_admin.firestore import SERVER_TIMESTAMP

    db = firestore.client()
    ref = db.collection("users").document(uid)
    snap = ref.get()
    if not snap.exists:
        raise DeviceError("사용자 정보를 찾을 수 없습니다.")
    data = snap.to_dict() or {}
    saved: Optional[str] = data.get("device_guid")

    if not saved:
        ref.update({
            "device_guid": current,
            "device_registered_at": SERVER_TIMESTAMP,
        })
        return

    if str(saved).strip() == current:
        return

    raise DeviceError(
        "이 계정은 다른 컴퓨터에서 사용 중입니다.\n"
        "기기 변경이 필요하면 선생님(관리자)에게 문의하세요."
    )
