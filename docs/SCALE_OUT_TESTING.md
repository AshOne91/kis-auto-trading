# 다중화 우선 개발과 통합 테스트

KIS Auto Trading은 단일 서버에서 먼저 완성한 뒤 확장하지 않는다. 모든 상태 저장 기능은
처음부터 여러 API 인스턴스가 같은 외부 상태를 공유한다는 조건으로 설계한다.

## 최소 통합 토폴로지

```text
API instance 1 ─┬─ Redis Cluster (3 Primary + 3 Replica)
API instance 2 ─┤
                ├─ Identity Global PostgreSQL
                ├─ Automation Global PostgreSQL
                ├─ Account PostgreSQL Shard 1
                └─ Account PostgreSQL Shard 2
```

API 컨테이너는 서로의 메모리를 공유하지 않는다. 세션은 Redis에, 계정 정보와 자동화
Job/Outbox 메타데이터는 각각 Global DB에, 개인정보는 선택된 shard DB에 저장한다. 어느
API가 요청을 받아도 동일한 사용자 세션과 shard 위치를 찾아야 한다.

## 실행

```powershell
$env:DURABLE_JOB_API_TOKEN = "replace-with-local-integration-token"
docker compose -f compose.integration.yaml up --build --wait
python scripts/verify_scale_out.py
docker compose -f compose.integration.yaml down -v
```

The profile runs `airflow-init`, `airflow-webserver`, and `airflow-scheduler`.
Airflow is available on `http://localhost:18080`. Generated durable-job DAGs
start paused and use the token-protected internal API; inspect them with
`docker compose -f compose.integration.yaml exec airflow-webserver airflow dags list`.
`scripts/verify_scale_out.py` also creates and cancels a Durable Job while the
worker is paused, then verifies the generated DAG's cancellation branch inside
the Airflow container. Its success path creates a deterministic `news_index`
Job by executing the generated Airflow `trigger_job`, waits for the real worker
to complete its zero-article handler path, then executes the complete generated
DAG with Airflow `dag.test()` and verifies normal return through real
TaskInstance/XCom context. It verifies the scheduler process is live but does
not unpause a cron DAG in the shared metadata database, because that could
create unrelated scheduled runs. It does not invoke an external news provider
or validate a production schedule.

## Isolated generated Airflow scheduler check

The generated environment itself is validated separately so that its Airflow
metadata, PostgreSQL, RabbitMQ, and Docker volume are not shared with the
scale-out profile. It uses the fixed local-only port block `59400`: application
`59400`, PostgreSQL `59410`, RabbitMQ `59430`/`59431`, and Airflow `59440`.

```powershell
python scripts/verify_generated_airflow_scheduler.py
```

The script uses a unique Compose project, waits for scheduler metadata
registration before unpausing the DAG, triggers one historical logical date,
cancels only the resulting Durable Job before worker claim, and removes its
own containers, network, and volume in `finally`.

## Isolated generated PostgreSQL HA check

The generated local environment can use `postgres_mode: ha`. This check creates
its own Compose project, validates the generated migrations, confirms one Patroni
leader and two streaming replicas, stops the active leader, verifies the HAProxy
writer endpoint reaches the promoted leader, then confirms the stopped node
rejoins as a replica.

```powershell
python scripts/verify_generated_postgres_ha.py
```

It removes only the containers, network, and named volumes created for its unique
Compose project. It is a single-host Docker integration check, not production
multi-host database HA validation.

The same check starts the generated FastAPI application and waits for both its
Compose healthcheck and `GET /health`. After the Patroni leader is stopped, it
waits for HAProxy to select the promoted writer and confirms that the original
application container keeps the same container ID and becomes healthy again.
The application image is not rebuilt during failover. This proves the local
database failover path used by the generated application; it does not claim
application-level retry guarantees for every long-running request.

`down -v`는 `kis-scale-out-test` Compose 프로젝트가 만든 테스트 컨테이너와 volume만
제거한다. 로컬 개발 DB나 다른 Compose 프로젝트는 대상으로 삼지 않는다.

## 테스트 계층

1. 단위 테스트는 Fake로 규칙과 실패 원인을 빠르게 검증한다.
2. 생성 테스트는 Global/Shard/Redis 설정과 생성 코드의 결정성을 검증한다.
3. 통합 테스트는 위 토폴로지를 실제로 실행한다.
4. 로그인 수직 기능은 한 API에서 만든 세션을 다른 API에서 읽어야 완료다.
5. shard 기능은 서로 다른 사용자가 shard 1과 shard 2에 분리 저장되는지 검증한다.
6. 장애 테스트는 API 한 대 종료, shard 한 대 장애, Redis 장애를 각각 검증한다.

검증 스크립트는 API 1에서 회원가입과 로그인을 수행하고, 발급된 Redis session을 API 2가
조회해 같은 `user_id`와 `shard_id`를 반환하는지 확인한다. 이는 API 로컬 메모리가 아니라
공유 Redis와 Global DB를 사용한다는 최소 교차 인스턴스 증거다. 이어서 API 2가 Bearer
session의 `user_id`와 `shard_id`로 Profile을 선택된 Account DB에 저장하고 API 1이 같은
Profile을 조회한다. 스크립트는 선택된 shard의 `user_profiles`에만 1행이 있고 반대
shard에는 0행인 것도 직접 확인한다.

세션 ID는 `사용자 routing tag.랜덤 secret` 형식이며 routing tag는 URL-safe Base64로
인코딩한다. 세션 본문 키와 사용자별 session index 키는 동일한 `{routing-tag}`를 포함해
Redis Cluster의 같은 hash slot에 배치된다. 따라서 생성·갱신·폐기 transaction이
`CROSSSLOT` 없이 원자적으로 실행된다.

## 환경과 볼륨의 경계

통합 환경은 `APP_ENV=integration`을 사용한다. 두 API에는 각각 `INSTANCE_ID=api-1`,
`INSTANCE_ID=api-2`를 부여하지만, 인스턴스 식별자는 관찰용일 뿐 데이터 분기 조건으로
사용하지 않는다. 두 인스턴스는 완전히 같은 애플리케이션 이미지를 실행한다.

PostgreSQL 데이터는 Compose named volume에 저장하고 초기 스키마 SQL은 읽기 전용으로
마운트하지 않는다. `migrate` Job이 Global DB와 모든 Shard DB에 store별 Alembic
revision을 적용하고 성공한 뒤에만 API가 시작한다. 생성 SQL은 검토와 별도 설치 도구를
위한 재현 산출물로 저장소에 계속 보존한다. 컨테이너만 재시작해도 데이터와
`alembic_version`은 유지되며, 깨끗한 초기화가 필요할 때만
이 Compose 프로젝트에 한정해 `down -v`를 실행한다. 애플리케이션 컨테이너에는 영속
볼륨을 두지 않는다.

## AWS 운영 환경으로 옮길 때

이 Compose 파일은 다중화 계약을 로컬에서 검증하기 위한 것이며 운영 배포 파일이 아니다.
운영에서는 다음과 같이 역할을 교체한다.

| 통합 환경 | AWS 운영 환경 |
|---|---|
| API 컨테이너 2개 | ALB 뒤의 ECS/EKS/EC2 Auto Scaling 인스턴스 |
| PostgreSQL 컨테이너 | RDS 또는 Aurora와 별도 shard 인스턴스 |
| Redis 컨테이너 | ElastiCache for Redis |
| Compose named volume | RDS/Aurora 관리형 스토리지 |
| 로컬 환경변수 | Parameter Store와 Secrets Manager |
| 컨테이너 로그 | 표준 출력과 CloudWatch Logs |

`base_server`의 환경별 설정 선택, 읽기 전용 설정 마운트, DB 초기화 SQL 보존,
헬스체크 후 배포 원칙은 유지한다. 반면 호스트 로그 디렉터리 공유, 이미지 안의 비밀번호,
API 서버별 로컬 DB/Redis는 수평 확장 시 상태가 갈라지므로 계승하지 않는다.

## Redis Cluster 고가용성

현재 통합 환경은 Redis Cluster Primary 3대와 각 Primary의 Replica 1대, 총 6개 노드를
실행한다. 초기화 Job은 16,384 slot 전체가 세 Primary에 배치됐는지 확인하며 기존 volume의
Cluster가 있으면 재생성하지 않고 정상 상태를 기다린다.

검증 스크립트는 로그인 session의 실제 hash slot과 담당 Primary/Replica를 동적으로 찾는다.
해당 Primary를 중지한 뒤 Replica 승격, 기존 session 읽기, 새 session 쓰기를 검증한다.
검증 당시 3개 Primary의 slot 수는 5,461/5,462/5,461개였고 전체 slot coverage가
확인됐다. 이전 단계의 Primary 1대, Replica 1대, Sentinel 3대 장애 전환 검증 이력과
설정 파일은 비교·회귀 근거로 보존한다.

AWS에서는 자체 Cluster 노드 대신 ElastiCache Cluster Mode와 Multi-AZ Automatic
Failover로 교체한다. 애플리케이션은 `SessionStore`와 Cluster endpoint만 사용하고 개별
노드 주소나 역할을 업무 코드에서 알지 않는다.

AutoForge는 `SessionStore` 업무 계약을 유지하면서 standalone, sentinel, cluster,
managed 연결 공급자를 선택할 수 있게 생성해야 한다. Redis 배치 방식이 Identity Handler나
Account Handler의 업무 코드로 새어 나가면 안 된다.

## RabbitMQ와 Transactional Outbox

현재 통합 토폴로지는 RabbitMQ 1대, Outbox Relay 1대와 Message Worker 1대를 추가로
실행한다. 이 단계는 broker 자체 cluster 검증 전의 전달 신뢰성 수직 슬라이스다.

Profile 저장과 `outbox_events` 추가는 선택된 Account shard의 같은 SQLAlchemy
transaction에서 수행한다. API는 RabbitMQ에 직접 연결하지 않으므로 broker가 중단되어도
업무 저장은 성공하고 event는 `pending`으로 남는다.

Outbox Relay는 `FOR UPDATE SKIP LOCKED`로 batch를 선점하고 publisher confirm이 성공한
event만 `published`로 바꾼다. Worker는 manual ACK 전에 같은 shard의
`processed_messages`에 event ID를 `ON CONFLICT DO NOTHING`으로 claim한다. relay가
confirm 직후 DB commit 전에 죽어 같은 message를 다시 보내도 두 번째 처리는 건너뛴다.

`scripts/verify_scale_out.py`는 실제로 RabbitMQ를 중단한 상태에서 Profile 저장,
pending Outbox 확인, broker 재시작 후 발행/소비, 같은 event 재발행 후 Inbox 한 행 유지를
수행한다. RabbitMQ node name은 `rabbit@rabbitmq`로 고정하고 named volume을 사용하므로
컨테이너를 재생성해도 durable queue가 복구된다.

RabbitMQ cluster와 quorum queue 복제는 후속 전체 HA 단계에서 별도로 검증한다. 현재
검증 결과를 broker 다중화 완료로 과장하지 않는다.
