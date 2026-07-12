# test.py
import httpx
import time

print("--- 🚀 [k8s 왕 로드밸런서 ➡️ Nginx ➡️ FastAPI 핑퐁 테스트] ---")

# 총 5번의 요청을 연속으로 보내봅니다.
for i in range(1, 6):
    try:
        # 내 컴퓨터의 80번 포트(쿠버네티스 외부 진입점)로 핑을 쏩니다.
        response = httpx.get("http://127.0.0.1:8080/ping")
        data = response.json()
        
        print(f"[{i}번째 핑퐁 성공]")
        print(f" - 상태: {data['status']}")
        print(f" - 통과한 가상 컴퓨터: {data['via_instance']}")
        print(f" - 백엔드 최종 메시지: {data['message']}")
        print(f" - 공용 프레임워크 명칭: {data['powered_by']}\n")
        
    except Exception as e:
        print(f"[{i}번째 핑퐁 실패] 연결에 실패했습니다: {e}")
        
    # 0.5초 간격으로 요청을 보냅니다.
    time.sleep(0.5)