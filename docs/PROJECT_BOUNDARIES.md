# 프로젝트 역할과 경계

## 전체 관계

```text
common-tool
  → 코드 생성 범위의 원형

game-server
  → 생성 결과의 Application/Domain/Service 조립 원형

SKN12 base_server
  → 현대화할 기능과 구조의 롤모델

AutoForge
  → 반복 골격과 외부 서비스 연결을 생성

kis-auto-trading
  → 생성 결과 위에 실제 자동매매 기능을 구현
```

SKN12 `base_server`는 AutoForge를 이용해 만든 프로젝트라고 가정하고 분석한다.
좋은 구조와 실제 업무 규칙은 가져오고, 임시 구현과 직접 만든 범용 인프라는
검증된 외부 서비스로 교체한다.

## AutoForge가 소유하는 것

- Project와 Module 명세
- API/Packet와 Model Generator
- Router와 Handler 골격
- Repository Protocol과 Fake
- SQLAlchemy/Alembic Adapter 생성
- Redis Service 연결 생성
- RabbitMQ Publisher/Consumer와 Worker 생성
- lifespan, dependency와 health check 생성
- Docker/Kubernetes/CI 설정 생성
- 생성 파일 Manifest와 반복 생성 안전성

## kis-auto-trading이 소유하는 것

- 투자 업무 규칙
- KIS Broker 연동 정책
- Account/Profile
- Portfolio와 Position
- Order와 체결 상태
- AutoTrade Strategy
- Risk Policy
- SignalEvent delivery intent and expiry policy: the first delivery target is a
  durable, per-subscription intent in the global automation store, not a direct
  order, SMS, email, WebSocket, or webhook. The producing KIS policy will supply
  an immutable expiry; a later worker must suppress intent creation after that
  expiry. Channel-specific delivery and retry policy remain separate KIS-owned
  decisions.
- 실제 Secret reference
- 통합 테스트와 운영 설정

## 필수 서비스

### Redis

Redis는 선택 기능이 아닌 필수 Service다.

- cache
- rate limit
- idempotency
- 짧은 수명의 상태
- 분산 coordination

### RabbitMQ

RabbitMQ는 비동기 Queue와 외부 Event Transport를 담당한다.

- ACK/NACK
- retry
- DLQ
- Worker 수평 확장

Redis에 Queue 기능을 다시 직접 구현하지 않는다.

### 관계형 Database

업무 데이터의 원장은 관계형 DB다. Redis나 RabbitMQ를 원장으로 사용하지 않는다.

## 생성 코드와 사용자 코드

```text
generated/
  → AutoForge가 관리

handlers.py, service.py
  → 최초 골격 이후 사용자 관리

domain policy와 trading strategy
  → 사용자 전용

migration
  → 생성 후 이력으로 고정
```

AutoForge는 사용자 소유 코드를 덮어쓰지 않는다.

## SKN12 코드 적용 기준

가져온다:

- 실제 Packet 필드
- Domain model과 상태
- Portfolio와 주문 흐름
- DB 배치 의도
- Redis namespace와 TTL 요구사항
- Outbox와 비동기 처리 요구사항

교체한다:

- callback Protocol
- 전역 ServiceContainer
- 직접 만든 Queue와 DLQ
- 자체 인증과 OTP
- 직접 만든 관측성
- 평문 credential 저장

버린다:

- 고정 token과 OTP secret
- 임시 응답
- 검증 우회
- 조용한 DB fallback
- 테스트로 확인되지 않는 포트폴리오 문서의 주장
