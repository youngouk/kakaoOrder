#!/usr/bin/env python3
"""
주문 분석 시스템 테스트 스크립트
"""
import os
import sys
import json
from llm_service import analyze_conversation, extract_product_info_from_seller_messages

# 테스트 샘플 메시지
TEST_MESSAGE = """
2025년 4월 26일 오후 2:10, 우국상 신검단 : 🌈🌈오늘특가상품 잔여수량🌈🌈

한우송화버섯 해장국 2팩 6900원, 3팩 8900원

한우사골곰탕 2팩 6900원

초코생크림 케이크 1개 2만원

고구마생크림 케이크 1개 2만원

프리미엄 하이드로겔 시트 1상자 9500원

💚마감은 오늘 오후 5시입니다💚

2025년 4월 26일 오후 2:15, 머슴 : 📣📣오늘 마감 안내📣📣
곰탕류는 월요일 수령
케이크는 화요일 수령
하이드로겔 마스크팩은 수요일 수령

2025년 4월 26일 오후 3:10, 하늘 5555 : 초코생크림 케이크 1개 주문해요
"""

def test_product_extraction():
    """판매자 메시지에서 상품 정보 추출 테스트"""
    print("\n===== 판매자 메시지 상품 정보 추출 테스트 =====")
    result = extract_product_info_from_seller_messages(TEST_MESSAGE)
    total_products = sum(len(products) for products in result.values())
    
    if total_products > 0:
        print(f"\n✅ 성공: {total_products}개 상품 추출됨")
        for category, products in result.items():
            if products:
                print(f"\n{category} 카테고리 ({len(products)}개):")
                for product in products:
                    print(f"  - {product['name']} ({product.get('price', '가격 정보 없음')})")
    else:
        print("❌ 실패: 상품 정보를 추출하지 못했습니다.")

def test_conversation_analysis():
    """대화 분석 전체 테스트"""
    print("\n===== 전체 대화 분석 테스트 =====")
    result = analyze_conversation(
        conversation_text=TEST_MESSAGE,
        shop_name="우국상검단점"
    )
    
    # 결과 요약
    if "error" in result:
        print(f"❌ 분석 오류: {result.get('message', '알 수 없는 오류')}")
    else:
        print("✅ 분석 완료")
        print(f"시간순 주문: {len(result.get('time_based_orders', []))}개")
        print(f"품목별 요약: {len(result.get('item_based_summary', []))}개")
        print(f"주문자별 주문: {len(result.get('customer_based_orders', []))}개")
        
        # 상품 목록 확인
        if "available_products" in result and result["available_products"]:
            print(f"\n추출된 상품 정보 ({len(result['available_products'])}개):")
            for product in result["available_products"]:
                print(f"  - {product.get('name', '이름 없음')} "
                      f"({product.get('category', '카테고리 없음')})")

def main():
    """메인 테스트 함수"""
    print("===== 주문 분석 시스템 테스트 시작 =====")
    test_product_extraction()
    test_conversation_analysis()
    print("\n===== 테스트 완료 =====")

if __name__ == "__main__":
    main() 