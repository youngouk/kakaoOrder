import os
import json
import re
import anthropic
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get API key from environment variable
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Initialize Claude client
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def analyze_conversation(conversation_text, date_str=None, shop_name=None):
    """
    Analyze the conversation using Claude 3.7 Sonnet with thinking enabled
    
    Args:
        conversation_text (str): The KakaoTalk conversation text
        date_str (str, optional): Date to filter the conversation (format: "YYYY년 MM월 DD일")
        shop_name (str, optional): Name of the shop/chat
        
    Returns:
        dict: The analyzed data including time-based orders, item summaries, and customer summaries
    """
    # Create the system prompt
    system_prompt = """
    당신은 KakaoTalk 대화 내역을 분석하여 주문 정보를 추출하는 전문가입니다. 
    정확하고 꼼꼼하게 모든 주문 정보를 찾아내세요.
    """
    
    # Create the user prompt with instructions
    date_guidance = f"\n특별히 {date_str} 날짜에 해당하는 대화내용만 분석해주세요." if date_str else ""
    shop_context = f"\n이 대화는 '{shop_name}' 상점의 주문 내역입니다." if shop_name else ""
    
    user_prompt = f"""
    아래 KakaoTalk 대화 내역을 분석하여 주문 정보를 추출해주세요.{date_guidance}{shop_context}
    
    분석 결과는 다음 3가지 테이블로 구성해주세요:
    
    1. 시간순 주문 내역: 대화에서 언급된 모든 주문을 시간 순서대로 정리
       - 시간, 주문자, 품목, 수량, 비고 포함
       
    2. 품목별 총 주문 갯수: 각 품목별 총 주문량 정리
       - 품목명, 총 수량, 주문자 목록 포함
       
    3. 주문자별 주문 내역: 주문자 기준으로 주문 내용 정리
       - 주문자, 품목, 수량, 비고 포함
       - 주문자가 복수의 품목을 주문한 경우 각각 별도 행으로 표시
       - 비고는 해당 주문자의 첫 번째 항목에만 표시
    
    반드시 JSON 형식으로 응답해주세요. 응답 형식은 다음과 같습니다:
    
    ```json
    {
      "time_based_orders": [
        {
          "time": "시간",
          "customer": "주문자",
          "item": "품목",
          "quantity": "수량",
          "note": "비고"
        }
      ],
      "item_based_summary": [
        {
          "item": "품목명",
          "total_quantity": "총 수량",
          "customers": "주문자 목록"
        }
      ],
      "customer_based_orders": [
        {
          "customer": "주문자명",
          "item": "품목명",
          "quantity": "수량",
          "note": "비고"
        }
      ]
    }
    ```
    
    대화내역:
    ```
    {conversation_text}
    ```
    """
    
    try:
        # Call Claude API with thinking enabled
        response = client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=4000,
            temperature=0.2,
            system=system_prompt,
            thinking={"type": "enabled", "budget_tokens": 4000},
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # Extract content from response
        content = response.content[0].text
        
        # Try to parse JSON from the response
        try:
            # Find JSON content if it's wrapped in ```json blocks
            json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = content
                
            # Clean up any trailing backticks
            json_str = json_str.replace('```', '').strip()
            
            # Parse JSON
            result = json.loads(json_str)
            return result
            
        except json.JSONDecodeError as e:
            # If JSON parsing fails, return the raw content for debugging
            return {"error": "JSON parsing failed", "raw_content": content, "message": str(e)}
    
    except Exception as e:
        # Handle any API or other errors
        return {"error": "API call failed", "message": str(e)}
