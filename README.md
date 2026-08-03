# 🚀 High-Availability K8s Trading Infrastructure (`kis-auto-trading`)

> **Automated Stock Trading Infrastructure with K8s High-Availability Architecture, Dynamic Reverse Proxy, and Zero-Trust Secret Management.**

본 프로젝트는 한국투자증권(KIS) Open API 기반의 **24/7 무중단 주식 자동매매 시스템**을 위한 **고가용성(High-Availability) 마이크로서비스 인프라**입니다.
외부 트래픽 제어, 동적 헤더 주입, 로드밸런싱, k8s Secret 기반 보안, hostPath 볼륨 마운트를 통한 로깅 보존까지 프로덕션 레벨의 안정성을 갖추도록 설계되었습니다.

또한, 본 명세서는 **인프라 자동 생성 AI 에이전트 및 IaC(Infrastructure as Code) 자동화 프로젝트**가 본 시스템의 토폴로지를 분석하고 표준 템플릿으로 재복제할 수 있도록 제공되는 **System Architecture Blueprint Reference**입니다.

---

## 📋 System Topology & Traffic Flow

```text
[ External Client / Probe (test.py) ]
                 │ (HTTP Request via http://127.0.0.1:8080)
                 ▼
[ Service: king-load-balancer (Type: LoadBalancer / Port: 8080 -> TargetPort: 80) ]
                 │
                 ▼
[ Nginx Reverse Proxy Layer (HA: 2 Replicas) ]
  ├── Pod 1: instance-web-nginx-deploy-xxxx1
  └── Pod 2: instance-web-nginx-deploy-xxxx2
                 │ (Injects Dynamic Header: X-Instance-Name from k8s Secret)
                 ▼
[ Internal Service: backend-service (ClusterIP / Port: 8000) ]
                 │ (Round-Robin Load Balancing)
                 ▼
[ FastAPI Application Engine Layer (Scale-out: 3 Replicas) ]
  ├── Pod 1: instance-web-fastapi-deploy-yyyy1
  ├── Pod 2: instance-web-fastapi-deploy-yyyy2
  └── Pod 3: instance-web-fastapi-deploy-yyyy3
                 │
                 ▼ (Appends Execution Logs with Unbuffered I/O)
[ Persistent Volume: Volume Mount (/app/logs) ──► Host Path (/run/desktop/mnt/host/c/kis-auto-trading/logs) ]

```

---

## 📂 Project Structure & Module Boundaries

```text
C:\kis-auto-trading\
 ├── base_server/                 # Microservice Backend & Proxy Sources
 │    ├── template/
 │    │    └── template_common.py # Unified JSON Response Formatter
 │    ├── service/
 │    │    └── stock_service.py   # Core Trading Engine Business Logic
 │    ├── application/
 │    │    └── base_web_server/
 │    │         └── main.py       # FastAPI Entry Point (Unbuffered File Logging)
 │    ├── nginx.conf.template     # Dynamic Nginx Configuration Blueprint
 │    ├── Dockerfile.web          # Python 3.10-slim Container Spec (PYTHONPATH=/app)
 │    └── Dockerfile.nginx        # Custom Nginx Image with Template Auto-Substitution
 │
 ├── logs/                        # [Git-Ignored] Host-Side Persistent Log Storage
 ├── kis_secret.env               # [Git-Ignored] Local Master Secret File (App Keys, Instances)
 ├── .gitignore                   # Security Enforcement Rules (*.env, logs/, venv/ exclusion)
 ├── requirements.txt             # Frozen Dependencies (fastapi, uvicorn, httpx)
 ├── kis-instances.yaml           # Fully Decoupled Production K8s Manifest (No Hardcoded Secrets)
 └── test.py                      # System Health Probe & Integration Test Script

```

---

## 🔒 Security Architecture & Zero-Trust Secret Lifecycle

1. **Separation of Concerns**: `kis-instances.yaml` 설계도 내에는 **그 어떠한 민감 정보(App Key, Instance Name)도 하드코딩하지 않습니다.**
2. **K8s Native Secret Integration**:
* 로컬 개발 환경의 `kis_secret.env` 파라미터를 읽어 메모리 상의 `Secret` 인프라 객체(`my-kis-gold-bar`)로 수동 주입합니다.
* Deployment 스펙은 `secretKeyRef`를 사용하여 런타임에 유기적으로 환경변수를 바인딩합니다.


3. **Source Control Integrity**:
* `.gitignore`가 `*.env` 및 `logs/`를 전역 차단하여 Github 등 원격 저장소 노출을 원천 방지합니다.



---

## 💾 Storage & Self-Healing Log Management

* **Host-Path Volume Binding**: Windows Docker Desktop 환경의 호스트 경로 (`/run/desktop/mnt/host/c/kis-auto-trading/logs`)와 컨테이너 내부(`/app/logs`)를 직접 연동합니다.
* **Unbuffered I/O Policy**: FastAPI 로깅 시 `f.flush()` 및 `buffering=1` 스펙을 강제 적용하여, 파드가 비정상 종료(Crash)되더라도 데이터 손실 없는 실시간 영구 기록을 보장합니다.

---

## 🛠️ Quick Start & Deployment Guide

### 1. Master Secret File Configuration

프로젝트 루트 디렉토리에 `kis_secret.env` 파일 생성:

```text
INSTANCE_NAME=SECURE-KING-BANANA-AAAA
KIS_API_URL=https://openapi.koreainvestment.com:9443

```

### 2. Container Images Build

```powershell
cd C:\kis-auto-trading\base_server
docker build -f Dockerfile.web -t kis-fastapi-web:v3 .
docker build -f Dockerfile.nginx -t kis-nginx:v4 .
cd ..

```

### 3. K8s Infrastructure Deployment

```powershell
# Create persistent host log directory
mkdir logs -ErrorAction SilentlyContinue

# Clear existing instances & inject Secret Gold Bar
kubectl delete -f kis-instances.yaml --ignore-not-found=true
kubectl delete secret my-kis-gold-bar --ignore-not-found=true
kubectl create secret generic my-kis-gold-bar --from-env-file=kis_secret.env

# Apply Manifests
kubectl apply -f kis-instances.yaml

```

### 4. Verification

```powershell
# Pod status check (Expect: 2 Nginx Pods, 3 FastAPI Pods)
kubectl get pods

# Health Probe Execution
python test.py

# Confirm execution log persistence
Get-Content C:\kis-auto-trading\logs\trading_history.log

```

---

## 🤖 Instructions for Auto-Generation AI Agents / Infrastructure Builders

If you are an AI Agent tasked with extending, cloning, or automating this infrastructure:

1. **Strict Architecture Enforcement**:
* Do NOT collapse the Nginx reverse proxy layer into FastAPI. The two-tier separation (Proxy -> Backend) is required for dynamic header injection and security boundaries.
* Maintain service exposure via `king-load-balancer` (External: `8080`, Internal Target: `80`).


2. **Decoupling Rule**:
* Any new trading strategies or API connections MUST be implemented in `base_server/service/`.
* Never embed credentials into `.yaml` manifests. Always reference `my-kis-gold-bar` or additional Secret objects.


3. **Stateless Scale-Out Guarantee**:
* All backend FastAPIs MUST remain stateless.
* Session or execution states MUST be offloaded to persistent volumes or external datastores.



---
