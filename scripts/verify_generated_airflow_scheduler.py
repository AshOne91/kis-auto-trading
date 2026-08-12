from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from uuid import uuid4

COMPOSE_FILE = "environment/compose.integration.yml"
DAG_ID = "durable_job_news_collection"
PORT_BASE = 59400
APPLICATION_PORT = PORT_BASE
POSTGRES_PORT = PORT_BASE + 10
RABBITMQ_AMQP_PORT = PORT_BASE + 30
RABBITMQ_MANAGEMENT_PORT = PORT_BASE + 31
AIRFLOW_PORT = PORT_BASE + 40
MAX_ATTEMPTS = 60
SCHEDULER_ATTEMPTS = 300
RETRY_SECONDS = 1.0


def _environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "LOCAL_BIND_ADDRESS": "127.0.0.1",
            "POSTGRES_USER": "autoforge",
            "POSTGRES_PASSWORD": "change-me",
            "POSTGRES_PORT": str(POSTGRES_PORT),
            "RABBITMQ_USER": "autoforge",
            "RABBITMQ_PASSWORD": "change-me",
            "RABBITMQ_URL": "amqp://autoforge:change-me@rabbitmq:5672/",
            "RABBITMQ_AMQP_PORT": str(RABBITMQ_AMQP_PORT),
            "RABBITMQ_MANAGEMENT_PORT": str(RABBITMQ_MANAGEMENT_PORT),
            "APPLICATION_PORT": str(APPLICATION_PORT),
            "AIRFLOW_PORT": str(AIRFLOW_PORT),
            "DURABLE_JOB_API_TOKEN": "generated-scheduler-test-token",
            "RAG_NETWORK_NAME": "kis_auto_trading-rag",
        }
    )
    return environment


class GeneratedEnvironment:
    def __init__(self) -> None:
        self.project_name = f"generated-airflow-test-{uuid4().hex[:8]}"
        self.environment = _environment()
        self.command = (
            "docker",
            "compose",
            "--project-name",
            self.project_name,
            "-f",
            COMPOSE_FILE,
        )

    def run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            (*self.command, *arguments),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=self.environment,
            timeout=180,
        )
        if result.returncode:
            raise RuntimeError(
                f"Compose command failed: {arguments!r}\n{result.stdout}\n{result.stderr}"
            )
        return result

    def close(self) -> None:
        try:
            self.run("down", "--volumes", "--remove-orphans")
        except RuntimeError as error:
            print(f"isolated Compose cleanup failed for {self.project_name}: {error}")


def _request_json(method: str, path: str) -> dict[str, object]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{APPLICATION_PORT}{path}",
        headers={
            "Authorization": "Bearer generated-scheduler-test-token",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _wait_for_application() -> None:
    for _ in range(MAX_ATTEMPTS):
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{APPLICATION_PORT}/health", timeout=2
            ) as response:
                if response.read() == b'{"status":"ok"}':
                    return
        except OSError:
            pass
        time.sleep(RETRY_SECONDS)
    raise RuntimeError("The generated application did not become healthy")


def _wait_for_dag_discovery(environment: GeneratedEnvironment) -> None:
    for _ in range(MAX_ATTEMPTS):
        try:
            result = environment.run(
                "exec", "-T", "airflow-webserver", "airflow", "dags", "list", "--output", "json"
            )
            if any(item.get("dag_id") == DAG_ID for item in json.loads(result.stdout)):
                return
        except RuntimeError:
            pass
        time.sleep(RETRY_SECONDS)
    raise RuntimeError("The generated Airflow DAG was not discovered")


def _dag_pause_state(environment: GeneratedEnvironment) -> str:
    return environment.run(
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "autoforge",
        "-d",
        "airflow",
        "-At",
        "-c",
        f"SELECT is_paused FROM dag WHERE dag_id = '{DAG_ID}'",
    ).stdout.strip()


def _wait_for_dag_registered(environment: GeneratedEnvironment) -> None:
    for _ in range(MAX_ATTEMPTS):
        if _dag_pause_state(environment) in {"t", "f"}:
            return
        time.sleep(RETRY_SECONDS)
    raise RuntimeError("The generated Airflow DAG was not registered by the scheduler")


def _wait_for_dag_unpaused(environment: GeneratedEnvironment) -> None:
    for _ in range(MAX_ATTEMPTS):
        if _dag_pause_state(environment) == "f":
            return
        time.sleep(RETRY_SECONDS)
    raise RuntimeError("The generated Airflow DAG remained paused")


def _job_id_for_run(
    environment: GeneratedEnvironment, *, run_id: str
) -> str:
    interval_result = environment.run(
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "autoforge",
        "-d",
        "airflow",
        "-At",
        "-c",
        "SELECT to_char(data_interval_start AT TIME ZONE 'UTC', "
        "'YYYY-MM-DD\"T\"HH24:MI:SS\"+00:00\"') "
        f"FROM dag_run WHERE dag_id = '{DAG_ID}' AND run_id = '{run_id}'",
    )
    interval_start = interval_result.stdout.strip()
    if not interval_start:
        raise RuntimeError("The isolated Airflow run metadata was not created")
    query = "SELECT job_id FROM durable_jobs " f"WHERE run_key = 'news_collection:{interval_start}'"
    for _ in range(SCHEDULER_ATTEMPTS):
        result = environment.run(
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "autoforge",
            "-d",
            "automation",
            "-At",
            "-c",
            query,
        )
        job_id = result.stdout.strip()
        if job_id:
            return job_id
        time.sleep(RETRY_SECONDS)
    task_states = environment.run(
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "autoforge",
        "-d",
        "airflow",
        "-At",
        "-c",
        "SELECT task_id || ':' || COALESCE(state, 'none') "
        f"FROM task_instance WHERE dag_id = '{DAG_ID}' AND run_id = '{run_id}'",
    ).stdout.strip()
    run_state = environment.run(
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "autoforge",
        "-d",
        "airflow",
        "-At",
        "-c",
        "SELECT state FROM dag_run "
        f"WHERE dag_id = '{DAG_ID}' AND run_id = '{run_id}'",
    ).stdout.strip()
    jobs = environment.run(
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "autoforge",
        "-d",
        "automation",
        "-At",
        "-c",
        "SELECT run_key || ':' || status FROM durable_jobs "
        "ORDER BY requested_at DESC LIMIT 3",
    ).stdout.strip()
    raise RuntimeError(
        "The isolated Airflow scheduler did not create the expected Job: "
        f"interval_start={interval_start!r}, run_state={run_state!r}, "
        f"task_states={task_states!r}, jobs={jobs!r}"
    )


def main() -> None:
    environment = GeneratedEnvironment()
    run_id = f"generated-airflow-scheduler-{uuid4()}"
    execution_date = (
        datetime.now(UTC) - timedelta(days=30, seconds=uuid4().int % 3600)
    ).replace(microsecond=0).isoformat()
    try:
        print(f"starting isolated generated environment: {environment.project_name}")
        environment.run("up", "--build", "--detach")
        print("waiting for generated application and Airflow DAG")
        _wait_for_application()
        _wait_for_dag_discovery(environment)
        _wait_for_dag_registered(environment)
        print("triggering isolated Airflow scheduler run")
        environment.run("stop", "durable-job-worker")
        environment.run("exec", "-T", "airflow-webserver", "airflow", "dags", "unpause", DAG_ID)
        _wait_for_dag_unpaused(environment)
        environment.run(
            "exec",
            "-T",
            "airflow-webserver",
            "airflow",
            "dags",
            "trigger",
            DAG_ID,
            "--run-id",
            run_id,
            "--exec-date",
            execution_date,
        )
        job_id = _job_id_for_run(environment, run_id=run_id)
        cancelled = _request_json("DELETE", f"/internal/jobs/news_collection/{job_id}")
        if cancelled.get("status") != "cancelled":
            raise RuntimeError(f"Expected cancelled Job, got {cancelled!r}")
        print(f"generated Airflow scheduler verified: job_id={job_id}")
    finally:
        environment.close()


if __name__ == "__main__":
    main()
