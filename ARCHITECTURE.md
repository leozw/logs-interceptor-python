# Clean Architecture - logs-interceptor-python

This project follows Clean Architecture and SOLID principles.

## Layers

- `domain/`: entities, value objects, interfaces/protocols.
- `application/`: orchestration use-cases (`ConfigService`, `LogService`).
- `infrastructure/`: concrete implementations (transport, buffer, filter, circuit breaker, DLQ, interceptors).
- `presentation/`: object graph factory and runtime wiring.

## Core Flow

1. User logs through API (`logger.info`, etc).
2. `LogService` builds `LogEntryEntity` with context and dynamic labels.
3. `LogFilter` applies level checks, sampling, sanitization.
4. `MemoryBuffer` stores entries with bounded-memory policies.
5. Flush pipeline pushes batches to `ResilientTransport`.
6. `ResilientTransport` applies retry + circuit breaker + DLQ fallback.
7. Loki receives logs through JSON or Snappy path.

## Resilience

- Retry with exponential backoff + jitter.
- Circuit breaker with closed/open/half-open states.
- DLQ with bounded memory/file storage and drop-oldest policy.

## Runtime Model

- Sync-first API for app safety.
- Async wrappers (`aflush`, `adestroy`) via thread offload.
- Background flush workers capped by `max_concurrent_flushes`.

## Extensibility

Add a new transport by implementing `ILogTransport` contract and wiring it in `TransportFactory`.
