# Airflow News 수집과 RAG 적재 전환 계획

작성 기준일: 2026-08-03

## 목적

SKN12 `base_server`에서 외부 AWS scheduler/Lambda가 Crawler API를 호출하던 뉴스 수집을
Airflow workflow로 현대화한다. 단순히 호출 주체만 바꾸지 않고 장기 실행 HTTP 요청,
메모리 작업 상태, 부분 실패와 중복 실행 문제를 함께 제거한다.

## 원본 코드에서 확인한 흐름

```text
POST /api/crawler/execute
  → CrawlerTemplateImpl
  → Redis 분산 lock
  → Yahoo Finance 뉴스 수집
  → 제목 MD5 중복 제거
  → OpenSearch 저장
  → S3 JSON 업로드
  → Bedrock Knowledge Base ingestion
```

RAG 서비스는 수집기가 아니다. Crawler가 문서를 적재하고, `RagService`가
OpenSearch BM25 결과와 VectorDB 결과를 결합해 조회한다.

현재 원본은 수백 종목과 외부 저장 작업이 끝날 때까지 HTTP 요청을 유지한다.
`v_active_tasks`와 중복 hash는 프로세스 메모리에 있으며 실제 status 경로와 일치하지
않는다. OpenSearch 또는 VectorDB 부분 실패도 전체 성공으로 보일 수 있다.

## 목표 구조

```text
Airflow DAG
  → POST /internal/jobs/news-collection (짧은 202 응답)
  → JobRecord + OutboxEvent (같은 DB transaction)
  → RabbitMQ
  → News Collection Worker
  → canonical news DB/S3
  → OpenSearch index
  → Bedrock Knowledge Base ingestion
  → 영속 Job 단계와 완료 event
  → Airflow status sensor와 notification
```

Airflow는 schedule, dependency, timeout, retry와 운영 관찰을 담당한다. 뉴스 parser,
종목 선택, 정규화와 저장 규칙은 KIS worker가 담당한다. 업무 코드를 DAG에 복사하지 않는다.

## 멱등성과 상태 계약

- `(job_type, run_key)`를 unique로 둔다.
- `run_key`는 `news:yahoo:{data_interval_start_utc}`처럼 결정적으로 만든다.
- Airflow retry와 수동 재실행은 같은 Job을 재사용한다.
- 뉴스는 정규화한 source URL, provider, publish time 기반 identity로 upsert한다.
- 상태는 `requested → collecting → collected → indexing → rag_ingesting → completed`로 둔다.
- 각 단계는 처리 수, artifact 위치, attempt와 마지막 오류를 영속 저장한다.
- 알 수 없는 event와 poison message는 성공 처리하지 않고 DLQ로 보낸다.

## 첫 DAG

```text
create_run_key
  → trigger_news_collection
  → wait_for_completion
  → verify_result
  → notify
```

초기 운영 정책은 `catchup=False`, `max_active_runs=1`, 명시적 execution timeout과
provider별 Airflow Pool이다. trigger API 인증은 사용자 access token이 아니라 내부
service identity를 사용하며, 운영에서는 private network와 mTLS/OIDC/IAM 방식을 선택한다.

## AutoForge와 KIS 책임

AutoForge가 생성할 공통 범위:

- 영속 Job 명세와 repository 골격
- idempotent trigger/status API 골격
- Job lifecycle event와 Outbox 연결
- Airflow DAG scaffold와 로컬 배포 blueprint
- timeout/retry/idempotency/observability validator

KIS가 작성할 업무 범위:

- 뉴스 source와 symbol 정책
- parser와 normalization
- canonical news schema와 index mapping
- S3/Bedrock 문서 변환
- 시장 휴장일, 실행 주기와 알림 정책

## 구현 순서

1. RabbitMQ/Outbox와 Event/Pipeline 기반을 완료한다.
2. JobRecord와 lifecycle event를 구현한다.
3. trigger/status API와 News worker의 최소 수직 기능을 구현한다.
4. 로컬 Docker Airflow DAG로 재시도·중복·부분 실패를 검증한다.
5. Kubernetes 실행은 KubernetesPodOperator/EKS operator를 비교한다.
6. AWS 운영은 Amazon MWAA와 EKS self-managed Airflow의 비용·제어권을 비교해 확정한다.

Airflow는 Redis, RabbitMQ 또는 AutoForge EventBus를 대체하지 않는다. 각각 workflow
control plane, durable transport, process 내부 event 전달이라는 서로 다른 책임을 가진다.
