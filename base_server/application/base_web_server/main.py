# main.py
from fastapi import FastAPI, Header
from typing import Optional

# 상위 디렉토리 격리 구조를 고려하여 상대 경로가 아닌 시스템 기준 모듈 경로로 가져옵니다.
from template.template_common import CommonTemplate
from service.stock_service import StockService

# FastAPI 비동기 웹 애플리케이션 객체 생성
app = FastAPI(title="KIS Base Web Server")

# 모듈 객체 초기화
template = CommonTemplate()
stock = StockService()

@app.get("/ping")
def ping(x_instance_name: Optional[str] = Header(None)):
    """
    Nginx를 거쳐 들어오는 핑퐁 테스트용 API 엔드포인트.
    Nginx가 헤더에 주입해 준 'X-Instance-Name'을 읽어옵니다.
    """
    # 만약 문지기(Nginx)가 헤더를 안 주거나 다이렉트 호출 시 예외 처리
    instance_name = x_instance_name if x_instance_name else "UNKNOWN-HEADER"
    
    # 주식 서비스 엔진 상태 추출
    engine_status = stock.get_service_status()
    message = f"pong ({engine_status})"
    
    # 공용 템플릿 규격에 맞춰 최종 응답데이터 리턴
    return template.format_response(
        status="success", 
        message=message, 
        via_instance=instance_name
    )