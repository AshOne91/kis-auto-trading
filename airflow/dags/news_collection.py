"""Generated Airflow orchestration for a durable job."""

import json
import os
import time
from datetime import UTC, datetime, timedelta
from urllib.request import Request, urlopen

from airflow.operators.python import PythonOperator, get_current_context

from airflow import DAG

JOB_TYPE = 'news_collection'
PAYLOAD_ENV = 'DURABLE_JOB_NEWS_COLLECTION_PAYLOAD_JSON'
POLL_SECONDS = int(os.getenv('DURABLE_JOB_POLL_SECONDS', '5'))
TIMEOUT_SECONDS = int(os.getenv('DURABLE_JOB_TIMEOUT_SECONDS', '3600'))


def _request(method: str, path: str, body: dict[str, object] | None = None) -> dict[str, object]:
    base_url = os.environ['DURABLE_JOB_API_URL'].rstrip('/')
    api_token = os.environ['DURABLE_JOB_API_TOKEN']
    data = json.dumps(body).encode() if body is not None else None
    request = Request(
        f'{base_url}{path}', data=data, method=method,
        headers={
            'Authorization': f'Bearer {api_token}',
            'Content-Type': 'application/json',
        },
    )
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise TypeError('durable job API response must be an object')
    return payload


def _payload() -> dict[str, object]:
    payload = json.loads(os.getenv(PAYLOAD_ENV, '{}'))
    if not isinstance(payload, dict):
        raise TypeError(f'{PAYLOAD_ENV} must contain a JSON object')
    return payload


def trigger_job() -> str:
    data_interval_start = get_current_context()['data_interval_start']
    if data_interval_start is None:
        raise RuntimeError('Airflow data interval start is required')
    run_key = f'{JOB_TYPE}:{data_interval_start.isoformat()}'
    response = _request(
        'POST', f'/internal/jobs/{JOB_TYPE}',
        {'run_key': run_key, 'payload': _payload()},
    )
    return str(response['job_id'])


def wait_for_job(ti) -> None:
    job_id = str(ti.xcom_pull(task_ids='trigger'))
    while True:
        response = _request('GET', f'/internal/jobs/{JOB_TYPE}/{job_id}')
        status = str(response['status'])
        if status == 'succeeded':
            return
        if status == 'failed':
            raise RuntimeError(str(response.get('error') or 'durable job failed'))
        time.sleep(POLL_SECONDS)


with DAG(
    dag_id='durable_job_news_collection',
    schedule='0 * * * *',
    start_date=datetime(2024, 1, 1, tzinfo=UTC),
    catchup=False,
    default_args={'retries': 3, 'retry_delay': timedelta(minutes=1)},
) as dag:
    trigger = PythonOperator(task_id='trigger', python_callable=trigger_job)
    wait = PythonOperator(
        task_id='wait',
        python_callable=wait_for_job,
        execution_timeout=timedelta(seconds=TIMEOUT_SECONDS),
    )
    trigger >> wait
