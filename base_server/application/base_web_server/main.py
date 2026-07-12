from fastapi import FastAPI, Header
from typing import Optional
from template.template_common import CommonTemplate
from service.stock_service import StockService
from datetime import datetime
import os

app = FastAPI(title="KIS Base Web Server")
template = CommonTemplate()
stock = StockService()

# 로그를 저장할 가상 하드디스크 폴더 경로
LOG_DIR = "/app/logs"
LOG_FILE_PATH = os.path.join(LOG_DIR, "trading_history.log")

@app.get("/ping")
def ping(x_instance_name: Optional[str] = Header(None)):
    instance_name = x_instance_name if x_instance_name else "UNKNOWN-HEADER"
    
    # 💡 [추가] 요청이 들어올 때마다 파일에 영수증을 한 줄씩 적습니다.
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{now}] 문지기 '{instance_name}'를 통해 노크 들어옴!\n"
    
    with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
        f.write(log_message)
        
    return template.format_response(
        status="success", 
        message=f"pong ({stock.get_service_status()})", 
        via_instance=instance_name
    )