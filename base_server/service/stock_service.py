# stock_service.py

class StockService:
    """
    자동매매 및 주식 자산 데이터 연산을 담당하는 핵심 서비스 클래스
    """
    def __init__(self):
        # 엔진 가동 상태 초기화
        self.engine_ready = True

    def get_service_status(self) -> str:
        """
        현재 주식 트레이딩 엔진의 가동 준비 상태를 문자열로 반환합니다.
        """
        if self.engine_ready:
            return "STOCK-ENGINE-READY"
        return "STOCK-ENGINE-OFFLINE"