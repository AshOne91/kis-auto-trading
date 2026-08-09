from kis_auto_trading.infrastructure.durable_jobs.worker import DurableJobExecution


class ApplicationDurableJobHandler:
    async def handle(
        self, execution: DurableJobExecution
    ) -> dict[str, object] | None:
        raise NotImplementedError('implement the durable job business handler')
