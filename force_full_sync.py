#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Firestore → 캐시 강제 full sync."""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from backend.firebase_init import init_admin_sdk
init_admin_sdk()

from backend.data_cache import ProblemsCache
from google.cloud import firestore
fs = firestore.Client.from_service_account_json("G:/문제은행/문제은행2/firebase-key.json")

print("[force_full_sync] 시작...")
cache = ProblemsCache(fs, verbose=True)
n = cache.full_sync()
print(f"\n[완료] {n}건 적재 → {cache.cache_path}")
