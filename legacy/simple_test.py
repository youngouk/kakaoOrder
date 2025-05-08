#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
from llm_service import SELLER_KEYWORDS

# 카카오톡 메시지 패턴
MESSAGE_PATTERN = r'(\d{4})년\s*\d{1,2}월\s*\d{1,2}일\s*(오전|오후)\s*(\d{1,2}):(\d{2}),\s*([^:]+)\s*:\s*(.*)'

print("판매자 키워드 목록:")
for keyword in SELLER_KEYWORDS:
    print(f"- {keyword}")

# 테스트 메시지
test_lines = [
    "2025년 4월 26일 오후 2:10, 우국상 신검단 : 테스트 메시지",
    "2025년 4월 26일 오후 2:15, 머슴 : 다른 테스트 메시지",
    "2025년 4월 26일 오후 2:20, 일반사용자 : 일반 메시지"
]

print("\n메시지 테스트:")
for line in test_lines:
    print(f"\n원본: {line}")
    match = re.search(MESSAGE_PATTERN, line)
    if match:
        sender = match.group(5).strip()
        is_seller = any(keyword in sender for keyword in SELLER_KEYWORDS)
        print(f"발신자: '{sender}', 판매자 여부: {is_seller}")
        if is_seller:
            matching_keywords = [keyword for keyword in SELLER_KEYWORDS if keyword in sender]
            print(f"매칭된 키워드: {matching_keywords}")
    else:
        print("메시지 패턴 불일치")

print("\n문제 해결을 위한 정규식 패턴 테스트:")
test_regex = r'(\d{4})년\s*\d{1,2}월\s*\d{1,2}일\s*(오전|오후)\s*(\d{1,2}):(\d{2}),\s*([^:]+)\s*:\s*(.*)'

for line in test_lines:
    match = re.search(test_regex, line)
    if match:
        print(f"패턴 매칭: {line}")
        groups = match.groups()
        print(f"추출된 그룹 수: {len(groups)}")
        for i, group in enumerate(groups):
            print(f"그룹 {i+1}: '{group}'")
    else:
        print(f"패턴 불일치: {line}") 