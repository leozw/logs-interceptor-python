from __future__ import annotations

from ...config import ResolvedLogsInterceptorConfig
from ...domain.interfaces import ICircuitBreaker, IDeadLetterQueue, ILogTransport
from ...utils import internal_debug, internal_warn
from .loki_json_transport import LokiJsonTransport
from .loki_protobuf_transport import LokiProtobufTransport
from .resilient_transport import ResilientTransport, ResilientTransportConfig


class TransportFactory:
    @staticmethod
    def create(
        config: ResolvedLogsInterceptorConfig,
        circuit_breaker: ICircuitBreaker | None = None,
        dlq: IDeadLetterQueue | None = None,
    ) -> ILogTransport:
        base_transport: ILogTransport

        if config.transport.compression == "snappy":
            try:
                internal_debug("Selected LokiProtobufTransport")
                base_transport = LokiProtobufTransport(config.transport)
            except Exception as exc:
                internal_warn("Falling back to LokiJsonTransport because snappy/protobuf is unavailable", exc)
                base_transport = LokiJsonTransport(config.transport)
        else:
            internal_debug("Selected LokiJsonTransport")
            base_transport = LokiJsonTransport(config.transport)

        return ResilientTransport(
            base_transport,
            ResilientTransportConfig(
                max_retries=config.transport.max_retries,
                retry_delay=config.transport.retry_delay,
            ),
            circuit_breaker,
            dlq,
        )
