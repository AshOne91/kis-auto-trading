# KIS Auto Trading

KIS Auto Trading은 AutoForge가 생성한 FastAPI 골격을 실제 업무 코드와 결합하여
검증하는 수평 확장형 자동매매 서비스다. 현재 첫 수직 기능은 Identity 로그인과
Account Profile이며, Global DB, shard DB, Redis Cluster, RabbitMQ와 Transactional
Outbox를 실제 Docker 환경에서 검증한다.

## 프로젝트 관계

- `AutoForge`: 명세, Generator, Manifest, 공통 infrastructure와 검증 계약을 소유한다.
- `kis-auto-trading`: 투자 도메인 규칙, handler, 배포 설정과 실제 운영 workflow를 소유한다.
- `base_server/`: SKN12 원본 기능과 과거 K8s 프로토타입을 참고하기 위한 보존 영역이다.
- `base_server/`와 루트 `test.py`는 실행 제품이 아닌 보존 자료이므로 Ruff 대상에서
  제외한다. 제품 품질 게이트는 `src/`, `tests/`, `scripts/`, `migrations/`와 배포
  설정을 대상으로 한다.

AutoForge가 생성한 파일을 무조건 수정하지 않는다. `.autoforge/manifest.json`의
`GENERATED`, `SCAFFOLDED`, `USER_OWNED` 소유권을 기준으로 변경한다.

## 현재 실행 구조

```text
Client
  ├─ API 1 ─┐
  └─ API 2 ─┴─ Redis Cluster (3 Primary + 3 Replica)
              ├─ Identity Global PostgreSQL
              ├─ Account PostgreSQL Shard 1
              └─ Account PostgreSQL Shard 2

Profile transaction
  ├─ user_profiles 저장
  └─ outbox_events 저장
         ↓ Outbox Relay
      RabbitMQ durable topic exchange/queue
         ↓ manual ACK
      Message Worker
         ↓ event_id unique claim
      processed_messages (선택된 Account shard)
```

Redis는 session/cache/coordination, RabbitMQ는 외부 durable message transport,
PostgreSQL은 업무 상태의 원장을 담당한다. 서로의 책임을 대체하지 않는다.

## AutoForge 생성 범위

`autoforge.yaml`과 `specifications/*.yaml`을 입력으로 다음 파일을 생성한다.

- FastAPI application/module 골격
- SQLAlchemy async model/repository와 shard session registry
- Store별 Alembic 환경과 immutable baseline/outbox revision
- Redis standalone/Sentinel/Cluster session adapter
- RabbitMQ publisher/consumer와 durable topology
- Transactional Outbox writer/relay와 Processed Message Inbox
- 실행 script와 generation manifest

재생성 명령:

```powershell
python -m autoforge.main generate `
  --project autoforge.yaml `
  --specifications specifications `
  --output . `
  --validation-python .venv\\Scripts\\python.exe
```

## First safe KIS domain step

Start with the domestic current-price path before implementing strategies or
orders. Its fake-transport tests require no KIS account or credentials and
verify the complete local boundary: operator API, shared token coordinator,
short-lived Redis cache, and KIS response parsing.

```powershell
pytest -p no:cacheprovider tests/test_kis_market_data.py tests/test_operator_market_data_api.py tests/test_kis_market_data_lifespan.py -q
```

This is read-only: it does not submit an order, access a balance, or contact
KIS. Once it passes, use the opt-in check below to make exactly one real
current-price request.

## Opt-in KIS read-only integration check

The default test suite never contacts KIS. For the preferred live check, set
`KIS_API_URL`, `KIS_APP_KEY`, and `KIS_APP_SECRET` in `environment/.env`, start
the generated Compose stack, then run the verification inside the application
container:

For a first read-only check, use the KIS virtual-investment REST domain for
`KIS_API_URL`:

```text
https://openapivts.koreainvestment.com:29443
```

Create the virtual-investment app in KIS Developers and copy its App Key and
App Secret into the ignored `environment/.env` file. Do not commit them. Use
the real-investment REST domain only after the same read-only path is verified:
`https://openapi.koreainvestment.com:9443`.

```powershell
.\deploy\single-host\windows\start-compose.ps1
docker compose --env-file environment/.env -f environment/compose.integration.yml exec application python scripts/verify_kis_read_only_price.py
```

This reuses the application's existing `REDIS_URL=redis://redis:6379` container
network setting. It validates configuration before I/O, performs exactly one
current-price GET (default stock code `005930`), prints no secrets or price, and
closes its HTTP and Redis clients.

The pytest variant below is useful only when the host process has all four
values (`KIS_API_URL`, `KIS_APP_KEY`, `KIS_APP_SECRET`, and a host-reachable
`REDIS_URL`) exported explicitly:

```powershell
$env:KIS_READ_ONLY_INTEGRATION = "1"
$env:KIS_INTEGRATION_STOCK_CODE = "005930" # optional
pytest -p no:cacheprovider tests/integration/test_kis_market_data_integration.py -q
```

The check has no account, order, hash-key, WebSocket, polling, or background
behavior. It closes its HTTP and Redis clients after the one read-only request.

To run the separately opt-in domestic balance check, also export the three
`KIS_ACCOUNT_*` values below and enable it explicitly:

```powershell
$env:KIS_READ_ONLY_BALANCE_INTEGRATION = "1"
pytest -p no:cacheprovider tests/integration/test_kis_domestic_account_integration.py -q
```

It makes one read-only balance request and never prints the account number or
account summary.

## Read-only domestic balance client

`KisDomesticAccountClient` is a user-owned boundary for the official domestic
stock balance GET. The application owns its lifecycle and exposes its typed
holding list only through the internal operator-token-protected
`GET /internal/operator/portfolio/domestic-stock-holdings` route. It has no
persistence or order behavior. It requires
`KIS_ACCOUNT_NUMBER`, `KIS_ACCOUNT_PRODUCT_CODE`, and
`KIS_ACCOUNT_ENVIRONMENT` (`real` or `demo`) in addition to the existing KIS
application credentials. Generated local Compose and Kubernetes inject those
values into the application process only. The client returns typed holding
fields, not an account summary, and its default tests use fake transport only.

## Local operator access bootstrap

After applying the Identity migrations, a host operator can grant one existing
account `operator` access through the user-owned local CLI:

```powershell
python scripts/provision_operator.py `
  --email operator@example.com `
  --actor local-bootstrap
```

It requires `IDENTITY_DATABASE_URL` and `REDIS_URL`, writes one audit record,
and revokes the account's existing sessions so the user must log in again. It
only permits `user` to `operator`; administrator grants and access downgrades
are intentionally unsupported until session-version invalidation exists.

## 로컬 검증

Python 3.12 환경에서:

```powershell
python -m pip install -e ".[test]"
python -m ruff check --no-cache src tests scripts
pytest -p no:cacheprovider
```

전체 다중화 통합 검증:

```powershell
docker compose -f compose.integration.yaml up -d --build
python scripts/verify_scale_out.py
```

검증 스크립트는 다음을 실제로 수행한다.

1. API 2대의 health를 확인한다.
2. API 1 로그인 session을 API 2에서 검증한다.
3. API 2가 Profile을 선택된 shard에 저장하고 API 1이 조회한다.
4. RabbitMQ 중단 중 Profile과 pending Outbox가 함께 commit되는지 확인한다.
5. RabbitMQ 복구 후 relay 발행과 worker 소비를 확인한다.
6. 같은 event를 재발행해 Inbox row가 하나만 남는지 확인한다.
7. 실제 Redis primary를 중단해 replica 승격, 기존 읽기와 신규 쓰기를 확인한다.

통합 환경의 `kis_test` 계정과 비밀번호는 격리된 로컬 테스트 전용이다. 운영 Secret으로
재사용하지 않는다. volume 삭제가 필요할 때만 대상 Compose 프로젝트를 확인한 뒤
명시적으로 `down -v`를 실행한다.

## 현재 완료 범위

- Identity Global DB와 Account 2-shard Alembic migration
- Bearer session과 Profile shard 저장
- Redis Cluster 3 Primary + 3 Replica 장애 전환
- RabbitMQ publisher confirm, persistent message, manual ACK와 DLQ
- Profile transaction + Outbox 원자성
- relay 재시도와 consumer Inbox 멱등성
- RabbitMQ container 재생성 시 durable queue volume 복구

## 다음 순서

1. EventBus를 generic transport로 유지하면서 Job/Pipeline 실행 event를 구현한다.
2. 영속 Job 상태와 idempotent trigger/status API를 구현한다.
3. Airflow로 News 수집과 RAG 적재 workflow를 조정한다.
4. Git/Webhook/CI-CD 자동화와 AWS HA 배포 계약을 구현한다.
5. RabbitMQ cluster, DB/Redis Multi-AZ와 보안·장애 검증을 확장한다.

## 문서

- [프로젝트 역할과 경계](docs/PROJECT_BOUNDARIES.md)
- [AutoForge 적용 계획](docs/AUTOFORGE_ADOPTION_PLAN.md)
- [다중화 통합 테스트](docs/SCALE_OUT_TESTING.md)
- [SKN12 Account 현대화](docs/SKN12_ACCOUNT_MODERNIZATION.md)
- [Airflow News/RAG 전환 계획](docs/AIRFLOW_NEWS_RAG_PLAN.md)
