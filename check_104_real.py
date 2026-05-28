#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3
import sys

# stdout 인코딩 설정
sys.stdout.reconfigure(encoding='utf-8')

db_path = "problem_bank.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 2025년 1학기 기말 공통수학1 관련 레코드 검색
print("=" * 80)
print("[2025-1-1-F][공수1] 관련 DB 검색")
print("=" * 80)

# year, grade, semester, exam_type, subject 기준으로 검색
cursor.execute("""
    SELECT DISTINCT file_name, source, year, grade, semester, exam_type, subject, school
    FROM problems
    WHERE year = '2025' AND grade = '1' AND semester = '1'
    AND exam_type LIKE '%기말%'
    AND (subject LIKE '%공통수학1%' OR subject LIKE '%공수1%' OR subject LIKE '%수학상%')
    ORDER BY file_name
""")

rows = cursor.fetchall()
print("\n[검색 결과: {} 개의 unique file]".format(len(rows)))
for row in rows:
    print("  - file_name: {}".format(row[0]))
    print("    source: {}, year: {}, grade: {}, semester: {}, exam: {}, subject: {}, school: {}".format(
        row[1], row[2], row[3], row[4], row[5], row[6], row[7]))
    print()

# 파일명에 "2025-1-1-F"가 들어간 모든 레코드
print("=" * 80)
print("file_name에 '2025-1-1-F' 포함된 레코드")
print("=" * 80)
cursor.execute("""
    SELECT DISTINCT file_name, source, COUNT(*) as cnt
    FROM problems
    WHERE file_name LIKE '%2025-1-1-F%'
    GROUP BY file_name, source
    ORDER BY file_name
""")
rows = cursor.fetchall()
print("\n[검색 결과: {} 개]".format(len(rows)))
for row in rows:
    print("  {} | source={} | {}문제".format(row[0], row[1], row[2]))

conn.close()
