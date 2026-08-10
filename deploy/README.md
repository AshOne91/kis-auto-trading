# KIS 배포 운영 계약

## Compose 로그

`compose.integration.yaml`은 실행 프로세스마다 `/app/logs`를 별도 호스트
디렉터리에 연결한다. 기본 루트는 프로젝트의 `./logs`이며 Git에 포함하지 않는다.

| 프로세스 | 호스트 경로 |
| --- | --- |
| API replica 1 | `logs/api-1` |
| API replica 2 | `logs/api-2` |
| Message worker | `logs/message-worker` |
| Outbox relay | `logs/outbox-relay` |
| Migration | `logs/migrate` |

Windows Docker Desktop에서는 기본 상대 경로를 사용한다. Linux 운영 서버에서는
`LOG_ROOT=/opt/kis-auto-trading/logs`처럼 절대 경로를 지정한다.

```powershell
$env:LOG_ROOT = "C:/kis-auto-trading/logs"
docker compose -f compose.integration.yaml up -d --build
```

## Kubernetes 로그

생성된 `deploy/kubernetes/base-server.yaml`의 `hostPath`는 Docker Desktop 같은
단일 노드 개발 환경 전용이다. 여러 노드에서 `hostPath`는 노드마다 분리되므로
고가용성 영속 저장소가 아니다. 운영에서는 Pod stdout를 Fluent Bit/Filebeat로
중앙 수집하고, 파일 보존 정책이 있으면 replica 수에 맞는 PVC/PV 또는 EFS를
별도로 선택한다.

## ELK 준비 상태

애플리케이션 로그는 JSON Lines 형식으로 stdout와 위 파일 경로에 동시에
기록된다. Filebeat는 `LOG_ROOT/*/*.log`를 수집하면 되고, Kubernetes에서는
DaemonSet 수집기가 stdout를 수집한다. Kibana 검색 키는 `request_id`, `event_id`,
`job_id`, `instance/pod`로 통일한다.
