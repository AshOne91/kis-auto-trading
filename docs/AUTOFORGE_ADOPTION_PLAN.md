# AutoForge 적용 계획

## 목적

`kis-auto-trading`은 AutoForge의 첫 실제 적용 프로젝트다. SKN12
`base_server`의 기능을 그대로 복사하는 대신, `common-tool`의 반복 코드 생성
방식과 `game-server`의 수평 확장 원칙을 Python/FastAPI 구조로 현대화한다.

AutoForge와 이 저장소는 독립 Git 저장소로 유지한다.

- AutoForge: 명세 모델, Generator, Plugin, Manifest와 검증
- kis-auto-trading: 실제 명세, 생성 결과, KIS 연동과 거래 업무 규칙

두 저장소의 상세 책임은 `PROJECT_BOUNDARIES.md`를 따른다.

## 현재 상태

현재 서버는 `/ping`으로 Kubernetes, Nginx와 FastAPI 연결을 확인하는
프로토타입이다.

- Python 3.10 기반
- 단일 FastAPI `main.py`
- `StockService`와 공통 응답 Template
- Nginx 2개와 FastAPI 3개 replica를 선언한 Kubernetes manifest
- 정식 Domain, Application Handler, Repository와 DB 계층은 아직 없음
- `test.py`는 pytest가 아니라 실행 중인 서버를 호출하는 수동 probe

기존 프로토타입은 첫 생성 검증이 끝날 때까지 삭제하거나 덮어쓰지 않는다.

## 참고 프로젝트에서 가져올 경계

### common-tool

- Packet, Protocol과 Model의 반복 생성
- Application과 Template 연결 코드 생성
- DBTable, Load/Save와 SQL 생성

### game-server

- Application, Domain과 Service 책임 분리
- Global/User/Log 데이터 역할
- 사용자 키 기반 수평 데이터 배치

### SKN12 base_server

- FastAPI Application과 Router
- 재사용 가능한 Domain Template과 Service
- async DB pool과 lifespan
- Global/Shard DB와 Outbox 개념

다음 구현은 그대로 복사하지 않는다.

- 전역 ServiceContainer
- 하나의 거대한 `main.py`
- 세션 내부에 숨은 shard routing
- 잘못된 shard를 Global DB로 자동 대체
- 명세나 DB catalog에 평문 비밀번호 저장

## 목표 구조

```text
src/kis_auto_trading/
├── application/
│   ├── app_factory.py
│   └── generated/module_registry.py
├── modules/
│   └── account/
│       ├── generated/
│       │   ├── models.py
│       │   ├── schemas.py
│       │   ├── router.py
│       │   └── repository.py
│       ├── handlers.py
│       └── service.py
├── infrastructure/
│   └── database/
└── main.py
```

`generated`는 AutoForge가 소유하고 `handlers.py`, `service.py`와 프로젝트 고유
거래 정책은 사용자가 소유한다.

## 첫 수직 기능: Account/Profile

기존 SKN12 Account는 Identity, Profile, Broker credential, Trading Account와
Portfolio 책임이 섞여 있다. 첫 기능은 외부 인증 시스템이 정해지기 전에도
검증할 수 있는 투자 Profile로 제한한다.

```text
HTTP Packet
  → Account Router
  → Profile Handler
  → UserProfile Domain
  → UserProfileRepository Protocol
  → Fake Repository
```

Identity는 첫 단계에서 Fake dependency로 제공하고 이후 OIDC Identity Provider
Adapter로 교체한다. 실제 증권 계좌번호, KIS App Key와 Secret은 저장하지 않는다.
외부 자격 증명은 이후 Secret Provider의 참조로만 연결한다.

### Database 계약 초안

DatabaseSpec의 기술 중립 계약은 `specifications/identity.yaml`과
`specifications/account.yaml`에 선언한다. PostgreSQL 재현 SQL 생성까지
완료했으며 SQLAlchemy Runtime 연결은 아직 포함하지 않는다.

```yaml
database:
  provider: agnostic
  tables:
    - name: user_profiles
  repositories:
    - name: UserProfileRepository
  placements:
    - table: user_profiles
      store: profile
      mode: sharded
      partition_key: user_id
```

## 적용 순서

1. AutoForge에서 DatabaseSpec과 Repository Protocol의 최소 계약을 구현한다.
2. Account Module 명세를 AutoForge 모델로 검증한다.
3. dry-run으로 생성 파일과 소유권을 확인한다.
4. 격리 Workspace에서 생성하고 import와 pytest를 실행한다.
5. 성공한 결과만 이 저장소에 적용한다.
6. 실제 SQLAlchemy/Alembic Adapter는 별도 Plugin 단계에서 추가한다.
7. 필수 Redis Service를 cache와 coordination 용도로 연결한다.
8. 필수 RabbitMQ Transport와 Worker를 연결한다.
9. Outbox Relay로 DB 변경과 RabbitMQ 발행을 연결한다.
10. Account 검증 후 Portfolio와 AutoTrade Module로 확장한다.

현재 1단계와 2단계가 완료되었다. AutoForge의 Repository Generator가 실제
`specifications/account.yaml`에서 다음 출력을 렌더링하고 Python 문법을
검증했다.

```text
src/kis_auto_trading/modules/account/generated/repository.py
src/kis_auto_trading/modules/account/generated/fake_repository.py
```

아직 실제 프로젝트 소스 트리에 적용하지 않았으며, SQLAlchemy/Alembic 경계와
Project Scaffold 적용 순서를 확정한 뒤 격리 Workspace 검증을 거쳐 반영한다.

### 2026-07-31 Global/Shard Database 기준선

- `specifications/identity.yaml`: 로그인 인증정보를 Global 저장소에 배치한다.
- `specifications/account.yaml`: 개인정보 Profile을 `user_id` 기준 Shard에 배치한다.
- AutoForge가 생성한 PostgreSQL SQL을 `database/global/`과
  `database/sharded/`에 저장하여 다른 로컬 환경에서도 스키마를 재현한다.
- Shard 라우팅 실패는 오류이며 Global DB로 자동 대체하지 않는다.
- SQLAlchemy Session, 실행 시점의 ShardRouter와 Alembic 적용은 다음 단계다.
- 로그인 API, JWT 또는 외부 Identity Provider 연동은 아직 구현하지 않았다.

## 완료 조건

- 같은 명세의 반복 생성 결과가 동일하다.
- 사용자 소유 Handler와 Service가 덮어써지지 않는다.
- 생성된 프로젝트가 Python 3.12에서 import된다.
- pytest, lint와 package build가 통과한다.
- Secret이 명세, Manifest, Git diff와 로그에 포함되지 않는다.
- AutoForge와 kis-auto-trading의 commit은 저장소별로 분리된다.
