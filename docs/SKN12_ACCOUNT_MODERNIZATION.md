# SKN12 Account 현대화 분석

## 목적

이 문서는 SKN12 `base_server`의 Account 기능을 실제 코드 기준으로 추적하고,
`kis-auto-trading`에서 보존할 업무 개념과 외부 시스템으로 교체할 인프라를
구분한다.

분석 기준 파일은 다음과 같다.

- `application/base_web_server/routers/account.py`
- `template/account/common/account_model.py`
- `template/account/common/account_serialize.py`
- `template/account/common/account_protocol.py`
- `template/account/account_template_impl.py`
- `template/base/template_service.py`
- `service/security/security_utils.py`
- `service/db/database_service.py`
- `db_scripts/drop_all_tables_and_recreate.sql`

포트폴리오 분석 문서의 예제는 실제 구현과 다를 수 있으므로 위 소스에서 확인한
기능만 구현 사실로 취급한다.

## 기존 호출 흐름

```text
FastAPI Router
  → Pydantic Request
  → AccountProtocol Controller
  → Callback
  → AccountTemplateImpl
  → ServiceContainer
  → DatabaseService/CacheService
  → Global DB/Shard DB/Redis
```

`AccountProtocol`은 외부 통신 규격보다는 Router와 Template을 연결하는 callback
dispatcher 역할을 한다. 현대 FastAPI 구조에서는 Router가 Application Handler를
dependency로 받아 직접 호출한다.

## 실제 구현 상태

### 구현된 기능

- bcrypt password hash와 검증
- 기존 SHA-256 hash 호환
- 회원가입 stored procedure 호출
- 사용자와 계정 상태 조회
- 로그인 시간과 횟수 갱신
- 사용자 shard 조회와 modulo 기반 할당
- Redis session 저장과 조회
- Profile 저장, 조회와 수정
- Shard DB의 투자 계좌와 초기 현금 Portfolio 생성
- 사용자별 외부 API key 저장

### 임시 또는 미완성 기능

- 이메일 인증 코드를 실제 발송하지 않고 로그에 기록
- 모든 사용자에게 동일한 고정 OTP secret 반환
- OTP 검증을 수행하지 않고 성공 처리
- access token과 refresh token이 고정 문자열
- token validation이 session 존재 여부만 확인
- 회원가입의 이메일 인증 단계를 개발용으로 생략
- Portfolio 초기화 실패를 Profile 성공 이후 무시
- KIS App Key와 Secret을 Global DB에 평문 저장
- 요청의 `X-Forwarded-For` 값을 신뢰 프록시 검증 없이 사용

따라서 기존 Account 기능을 완성된 인증 시스템으로 복사하지 않는다.

## 책임 재분리

기존 Account Template에는 서로 다른 책임이 섞여 있다.

```text
Identity
  회원가입, 로그인, password, OTP, token

User Profile
  투자 경험, 위험 성향, 투자 목표, 월 예산

Brokerage Connection
  KIS 계정 연결과 Secret 참조

Trading Account
  거래 계좌 상태

Portfolio
  현금과 보유 Position

Data Placement
  Global/Shard routing
```

### 외부 Identity Provider 책임

- 회원가입과 로그인
- password 저장과 정책
- 이메일 확인
- OTP
- access/refresh token
- token 폐기와 계정 잠금

FastAPI는 OIDC token을 검증하고 외부 subject를 내부 `user_id`와 연결한다.

### kis-auto-trading 책임

- 투자 Profile
- Broker 연결 상태
- 투자 가능 여부와 위험 정책
- Portfolio와 Order의 소유 관계
- Domain Event

## Secret 정책

외부 API credential 값을 Account 또는 Profile 테이블에 저장하지 않는다.

```text
BrokerageConnection
├── user_id
├── provider
├── account_alias
├── secret_ref
└── status
```

실제 credential은 Secrets Manager 또는 Vault에 저장한다. Git, AutoForge 명세,
Manifest와 애플리케이션 로그에는 값을 남기지 않는다.

## 첫 수직 기능

첫 구현은 Identity 전체가 아니라 투자 Profile에 한정한다.

```text
Fake Identity Dependency
  → Account Router
  → Profile Handler
  → UserProfileRepository
  → Fake Repository
```

외부 Identity Provider와 SQLAlchemy Adapter가 추가되어도 Handler와 Domain
계약은 유지한다.

## 원본 기능 처리 정책

| 원본 기능 | 처리 |
|---|---|
| Account/Profile Packet 필드 | 요구사항을 검토해 명세로 이전 |
| 투자 성향과 예산 | UserProfile Domain으로 보존 |
| bcrypt와 OTP | 외부 Identity Provider로 교체 |
| Redis session | OIDC token 검증과 필요한 최소 cache로 교체 |
| callback Protocol | Application Handler 호출로 교체 |
| Global/Shard 배치 | DataPlacementSpec으로 표현 |
| stored procedure | Repository Adapter와 migration으로 교체 |
| API key 평문 테이블 | Secret reference로 교체 |
| Profile 완료 후 Portfolio 생성 | 별도 Application workflow와 Event로 분리 |

## 후속 순서

1. AutoForge ModuleSpec으로 Account/Profile 명세를 검증한다.
2. Repository Protocol과 Fake Repository를 생성한다.
3. 생성된 Handler 골격에서 Profile 유스케이스를 구현한다.
4. SQLAlchemy/Alembic Plugin을 추가한다.
5. 외부 Identity Provider Adapter를 추가한다.
6. BrokerageConnection과 SecretProvider 계약을 추가한다.
7. Portfolio 초기화를 Profile transaction에서 분리하고 Event로 연결한다.
