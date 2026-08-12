import json
import logging

from kis_auto_trading.application.observability import JsonFormatter


def test_json_formatter_records_safe_durable_job_fields() -> None:
    record = logging.LogRecord(
        "kis_auto_trading.application.durable_job_handler",
        logging.ERROR,
        __file__,
        1,
        "news collection retries exhausted",
        (),
        None,
    )
    record.event_type = "news_collection_retries_exhausted"
    record.job_type = "news_collection"
    record.job_id = "job-3"
    record.run_key = "news:yahoo:test:retry:2"
    record.attempt = 3
    record.max_attempts = 3

    payload = json.loads(JsonFormatter().format(record))

    assert payload["event_type"] == "news_collection_retries_exhausted"
    assert payload["job_type"] == "news_collection"
    assert payload["job_id"] == "job-3"
    assert payload["run_key"] == "news:yahoo:test:retry:2"
    assert payload["attempt"] == 3
    assert payload["max_attempts"] == 3
