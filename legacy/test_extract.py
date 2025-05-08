#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from llm_service import extract_product_info_from_seller_messages

# 테스트 메시지
test_message = """2025년 4월 26일 오후 2:10, 우국상 신검단 : 🌈🌈오늘특가상품 잔여수량🌈🌈

한우송화버섯 해장국 2팩 6900원, 3팩 8900원

한우사골곰탕 2팩 6900원

한우나주곰탕 6900원

초코생크림 케이크 1개 2만원

고구마생크림 케이크 1개 2만원

프리미엄 하이드로겔 시트 1상자 9500원

💚마감은 오늘 오후 5시입니다💚
"""

# 함수 실행
results = extract_product_info_from_seller_messages(test_message)

# 결과 출력
print("\n추출된 상품 정보:")
for category, products in results.items():
    if products:
        for p in products:
            print(f"  - {category}: {p['name']} ({p.get('price', '가격정보없음')})") 