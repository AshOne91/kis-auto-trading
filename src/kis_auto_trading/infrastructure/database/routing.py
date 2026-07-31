from dataclasses import dataclass
from typing import Protocol


class ShardRoutingError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ShardTarget:
    store: str
    shard_id: str | None = None

    @property
    def is_global(self) -> bool:
        return self.shard_id is None


class ShardRouter(Protocol):
    async def resolve(
        self, store: str, partition_key: object | None,
    ) -> ShardTarget: ...
