from kis_auto_trading.infrastructure.database.session import AsyncSessionRegistry
from kis_auto_trading.infrastructure.durable_jobs.worker import DurableJobExecution


class ApplicationDurableJobHandler:
    async def handle(
        self, execution: DurableJobExecution
    ) -> dict[str, object] | None:
        raise NotImplementedError('implement the durable job business handler')


def create_durable_job_handler(
    session_registry: AsyncSessionRegistry,
) -> ApplicationDurableJobHandler:
    del session_registry
    return ApplicationDurableJobHandler()
