# template_common.py

class CommonTemplate:
    """
    모든 백엔드 응답의 표준 JSON 포맷을 생성하는 가상 프레임워크 클래스
    """
    def __init__(self):
        # 우리 시스템의 고유 프레임워크 명칭 정의
        self.framework_name = "KIS-MSA-Framework"

    def format_response(self, status: str, message: str, via_instance: str) -> dict:
        """
        입력받은 데이터를 규격화된 파이썬 딕셔너리(JSON 변환용)로 반환합니다.
        """
        return {
            "status": status,                  # 성공 여부 (success / fail)
            "message": message,                # 비즈니스 로직 처리 결과 메시지
            "via_instance": via_instance,      # 해당 요청을 처리한 문지기 인스턴스 이름
            "powered_by": self.framework_name  # 시스템 공용 프레임워크 표기
        }