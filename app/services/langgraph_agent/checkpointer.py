from __future__ import annotations

import base64
import json
import logging
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any, Optional
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    SerializerProtocol,
    get_checkpoint_id,
    get_checkpoint_metadata,
)
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days retention for chat sessions


class RedisSaver(BaseCheckpointSaver[str]):
    """Stateful, multi-tenant persistent Checkpoint Saver for LangGraph backed by Redis.
    
    Uses text-safe JSON & Base64 serialization compatible with decode_responses=True Redis clients.
    """

    def __init__(
        self,
        redis_client: Redis,
        *,
        ttl: int = DEFAULT_TTL_SECONDS,
        serde: SerializerProtocol | None = None,
    ) -> None:
        super().__init__(serde=serde)
        self.redis = redis_client
        self.ttl = ttl

    def _make_key(self, *parts: str) -> str:
        return ":".join(["grag", "ckpt"] + [p for p in parts if p])

    def _encode_typed(self, typed_val: tuple[str, bytes]) -> str:
        """Encode (type_str, bytes) into JSON string."""
        type_str, data_bytes = typed_val
        b64 = base64.b64encode(data_bytes).decode("ascii")
        return json.dumps({"type": type_str, "data": b64})

    def _decode_typed(self, encoded_str: str) -> tuple[str, bytes]:
        """Decode JSON string back to (type_str, bytes)."""
        obj = json.loads(encoded_str)
        type_str = obj["type"]
        data_bytes = base64.b64decode(obj["data"].encode("ascii"))
        return (type_str, data_bytes)

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Asynchronously retrieve a checkpoint tuple from Redis."""
        thread_id: str = config["configurable"]["thread_id"]
        checkpoint_ns: str = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = get_checkpoint_id(config)

        if not checkpoint_id:
            # Fetch latest checkpoint_id from thread index
            index_key = self._make_key("index", thread_id, checkpoint_ns)
            members = await self.redis.zrevrange(index_key, 0, 0)
            if not members:
                return None
            checkpoint_id = members[0] if isinstance(members[0], str) else members[0].decode()

        ckpt_key = self._make_key("data", thread_id, checkpoint_ns, checkpoint_id)
        raw_data = await self.redis.get(ckpt_key)
        if not raw_data:
            return None

        try:
            record_obj = json.loads(raw_data)
            checkpoint_typed = self._decode_typed(record_obj["checkpoint"])
            metadata_typed = self._decode_typed(record_obj["metadata"])
            parent_checkpoint_id = record_obj.get("parent_id")
        except Exception as exc:
            logger.warning(f"Could not parse checkpoint data for {ckpt_key}: {exc}")
            return None

        checkpoint_: Checkpoint = self.serde.loads_typed(checkpoint_typed)
        metadata = self.serde.loads_typed(metadata_typed)

        # Load channel blob values
        channel_values: dict[str, Any] = {}
        for channel, ver in checkpoint_.get("channel_versions", {}).items():
            blob_key = self._make_key("blob", thread_id, checkpoint_ns, channel, str(ver))
            raw_blob = await self.redis.get(blob_key)
            if raw_blob:
                try:
                    blob_typed = self._decode_typed(raw_blob)
                    if blob_typed[0] != "empty":
                        channel_values[channel] = self.serde.loads_typed(blob_typed)
                except Exception:
                    pass

        # Load pending writes
        writes_key = self._make_key("writes", thread_id, checkpoint_ns, checkpoint_id)
        raw_writes = await self.redis.hgetall(writes_key)
        pending_writes = []
        for _, raw_w in raw_writes.items():
            try:
                w_obj = json.loads(raw_w)
                task_id = w_obj["task_id"]
                c = w_obj["channel"]
                val_typed = self._decode_typed(w_obj["val"])
                pending_writes.append((task_id, c, self.serde.loads_typed(val_typed)))
            except Exception:
                pass

        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                }
            },
            checkpoint={
                **checkpoint_,
                "channel_values": channel_values,
            },
            metadata=metadata,
            pending_writes=pending_writes,
            parent_config=(
                {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": parent_checkpoint_id,
                    }
                }
                if parent_checkpoint_id
                else None
            ),
        )

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Asynchronously store a checkpoint and its channel blobs in Redis."""
        c = checkpoint.copy()
        thread_id: str = config["configurable"]["thread_id"]
        checkpoint_ns: str = config["configurable"].get("checkpoint_ns", "")
        values: dict[str, Any] = c.pop("channel_values")  # type: ignore[misc]

        # Store updated channel blobs
        for k, v in new_versions.items():
            blob_typed = (
                self.serde.dumps_typed(values[k]) if k in values else ("empty", b"")
            )
            blob_key = self._make_key("blob", thread_id, checkpoint_ns, k, str(v))
            await self.redis.set(blob_key, self._encode_typed(blob_typed), ex=self.ttl)

        # Store checkpoint record as JSON
        parent_id = config["configurable"].get("checkpoint_id")
        record_obj = {
            "checkpoint": self._encode_typed(self.serde.dumps_typed(c)),
            "metadata": self._encode_typed(self.serde.dumps_typed(get_checkpoint_metadata(config, metadata))),
            "parent_id": parent_id,
        }
        ckpt_key = self._make_key("data", thread_id, checkpoint_ns, checkpoint["id"])
        await self.redis.set(ckpt_key, json.dumps(record_obj), ex=self.ttl)

        # Update thread checkpoint index (ordered by numeric timestamp or length)
        index_key = self._make_key("index", thread_id, checkpoint_ns)
        try:
            score = float(checkpoint["id"].split(".")[0])
        except Exception:
            score = float(len(checkpoint["id"]))
        await self.redis.zadd(index_key, {checkpoint["id"]: score})
        await self.redis.expire(index_key, self.ttl)

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint["id"],
            }
        }

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Asynchronously store task writes linked to a checkpoint in Redis."""
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"]["checkpoint_id"]

        writes_key = self._make_key("writes", thread_id, checkpoint_ns, checkpoint_id)
        mapping = {}
        for idx, (c, v) in enumerate(writes):
            inner_field = f"{task_id}:{WRITES_IDX_MAP.get(c, idx)}"
            w_obj = {
                "task_id": task_id,
                "channel": c,
                "val": self._encode_typed(self.serde.dumps_typed(v)),
                "task_path": task_path,
            }
            mapping[inner_field] = json.dumps(w_obj)

        if mapping:
            await self.redis.hset(writes_key, mapping=mapping)
            await self.redis.expire(writes_key, self.ttl)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """Asynchronously list checkpoints."""
        if not config:
            return

        thread_id: str = config["configurable"]["thread_id"]
        checkpoint_ns: str = config["configurable"].get("checkpoint_ns", "")
        index_key = self._make_key("index", thread_id, checkpoint_ns)

        members = await self.redis.zrevrange(index_key, 0, (limit or 50) - 1)
        for mem in members:
            ckpt_id = mem if isinstance(mem, str) else mem.decode()
            tuple_config: RunnableConfig = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": ckpt_id,
                }
            }
            res = await self.aget_tuple(tuple_config)
            if res:
                yield res

    # Synchronous fallbacks
    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        raise NotImplementedError("Use async aget_tuple in RedisSaver")

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        raise NotImplementedError("Use async aput in RedisSaver")

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        raise NotImplementedError("Use async aput_writes in RedisSaver")

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        raise NotImplementedError("Use async alist in RedisSaver")
