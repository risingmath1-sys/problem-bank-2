"""URL encoding 이슈 확인."""
import sys, io, urllib.parse
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

pid = "[중][2025][2-1-a][서울강남구][대왕중][유리수와순환소수-일차부등식활용]_1"
print(f"원본 pid: {pid}\n")
print(f"URL 인코딩(quote): {urllib.parse.quote(pid)}\n")
print(f"URL 인코딩(quote_plus): {urllib.parse.quote_plus(pid)}\n")

# 브라우저가 hx-post URL 을 그대로 보내면?
url_raw = f"/api/library/problem/{pid}/preference"
print(f"raw URL: {url_raw}")
print(f"raw URL 안의 대괄호 [, ] 는 URI Reserved Character 일 수도\n")

# FastAPI 가 한글 path parameter 받는지 확인은 별도로
print("FastAPI path parameter 는 URL 디코딩된 결과를 받음.")
print("문제: 브라우저 또는 HTMX 가 [, ] 를 어떻게 인코딩하는가")

