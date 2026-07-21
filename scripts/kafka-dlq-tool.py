#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PLATFORM_COMMON_ROOT = REPO_ROOT / "libs" / "platform-common"
for path in (REPO_ROOT, PLATFORM_COMMON_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer  # noqa: E402
from platform_common.dlq import DeadLetterEventError, build_replay_message, summarize_dead_letter_event  # noqa: E402
from platform_common.tracing import inject_trace_metadata, start_trace, traceparent_from_event  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and replay Kafka DLQ events.")
    parser.add_argument(
        "--bootstrap-servers",
        default="localhost:29092",
        help="Kafka bootstrap servers. Default: localhost:29092",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    peek_parser = subparsers.add_parser("peek", help="Read DLQ events from a Kafka topic.")
    peek_parser.add_argument("--topic", required=True, help="DLQ topic to inspect.")
    peek_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of events to read. Default: 10",
    )
    peek_parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=5.0,
        help="How long to wait for messages before stopping. Default: 5",
    )
    peek_parser.add_argument(
        "--offset-reset",
        choices=("earliest", "latest"),
        default="earliest",
        help="Where to start reading when no offsets are stored. Default: earliest",
    )
    peek_parser.add_argument(
        "--raw",
        action="store_true",
        help="Print full DLQ events instead of compact summaries.",
    )

    replay_parser = subparsers.add_parser("replay", help="Replay a DLQ event back to its source topic.")
    replay_parser.add_argument(
        "--event-file",
        type=Path,
        help="Path to a JSON file containing one dead-letter event.",
    )
    replay_parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read the dead-letter event JSON from stdin.",
    )
    replay_parser.add_argument(
        "--replayed-by",
        default="local-operator",
        help="Operator identifier to store in replay metadata. Default: local-operator",
    )
    replay_parser.add_argument(
        "--reason",
        help="Optional replay reason to store in replay metadata.",
    )
    replay_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not publish; print the replay payload instead.",
    )

    return parser


async def run_peek(args: argparse.Namespace) -> int:
    consumer = AIOKafkaConsumer(
        args.topic,
        bootstrap_servers=args.bootstrap_servers,
        enable_auto_commit=False,
        auto_offset_reset=args.offset_reset,
        group_id=f"dlq-tool-{uuid.uuid4()}",
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
    )
    await consumer.start()
    read_count = 0
    deadline = asyncio.get_running_loop().time() + args.timeout_seconds
    try:
        while read_count < args.limit and asyncio.get_running_loop().time() < deadline:
            batches = await consumer.getmany(timeout_ms=500, max_records=args.limit - read_count)
            if not batches:
                continue
            for topic_partition, messages in batches.items():
                for message in messages:
                    payload = message.value
                    output = (
                        payload
                        if args.raw
                        else {
                            "topic": topic_partition.topic,
                            "partition": message.partition,
                            "offset": message.offset,
                            **summarize_dead_letter_event(payload),
                        }
                    )
                    print(json.dumps(output, ensure_ascii=False))
                    read_count += 1
                    if read_count >= args.limit:
                        break
                if read_count >= args.limit:
                    break
    finally:
        await consumer.stop()
    return 0


async def run_replay(args: argparse.Namespace) -> int:
    dead_letter_event = load_dead_letter_event(args)
    target_topic, replay_event = build_replay_message(
        dead_letter_event,
        replayed_by=args.replayed_by,
        replay_reason=args.reason,
    )

    with start_trace(
        traceparent_from_event(dead_letter_event),
        span_name="kafka dlq replay",
        span_kind="producer",
        attributes={
            "messaging.system": "kafka",
            "messaging.operation": "publish",
            "messaging.destination.name": target_topic,
            "messaging.message.id": replay_event.get("event_id"),
            "messaging.delivery.delivery_platform.replay": True,
        },
    ):
        replay_event = inject_trace_metadata(replay_event)

        if args.dry_run:
            print(
                json.dumps(
                    {"target_topic": target_topic, "replay_event": replay_event},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        producer = AIOKafkaProducer(
            bootstrap_servers=args.bootstrap_servers,
            value_serializer=lambda value: json.dumps(value, ensure_ascii=False).encode("utf-8"),
        )
        await producer.start()
        try:
            await producer.send_and_wait(target_topic, replay_event)
        finally:
            await producer.stop()

    print(
        json.dumps(
            {
                "status": "replayed",
                "target_topic": target_topic,
                "event_id": replay_event.get("event_id"),
                "aggregate_id": replay_event.get("aggregate_id"),
            },
            ensure_ascii=False,
        )
    )
    return 0


def load_dead_letter_event(args: argparse.Namespace) -> dict[str, Any]:
    if bool(args.event_file) == bool(args.stdin):
        raise DeadLetterEventError("Use exactly one of --event-file or --stdin")

    raw_payload = args.event_file.read_text(encoding="utf-8") if args.event_file else sys.stdin.read()
    try:
        event = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise DeadLetterEventError(f"Invalid JSON payload: {exc}") from exc
    if not isinstance(event, dict):
        raise DeadLetterEventError("Dead-letter event must be a JSON object")
    return {str(key): value for key, value in event.items()}


async def async_main(args: argparse.Namespace) -> int:
    if args.command == "peek":
        return await run_peek(args)
    if args.command == "replay":
        return await run_replay(args)
    raise DeadLetterEventError(f"Unsupported command: {args.command}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return asyncio.run(async_main(args))
    except DeadLetterEventError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
