"""Prometheus-compatible metrics service for Prism LLM Gateway."""

import time
from collections import defaultdict
from threading import Lock


class MetricsRegistry:
    """Thread-safe Prometheus metrics registry."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[str, dict[tuple, float]] = defaultdict(lambda: defaultdict(float))
        self._histograms: dict[str, list[float]] = defaultdict(list)

    def increment_counter(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Increment a labeled counter metric."""
        label_tuple = tuple(sorted((labels or {}).items()))
        with self._lock:
            self._counters[name][label_tuple] += value

    def observe_duration(self, name: str, duration_seconds: float) -> None:
        """Record a latency observation in seconds."""
        with self._lock:
            # Keep a bounded rolling list of recent observations
            observations = self._histograms[name]
            observations.append(duration_seconds)
            if len(observations) > 10000:
                self._histograms[name] = observations[-5000:]

    def format_prometheus(self) -> str:
        """Generate Prometheus exposition text format (0.0.4)."""
        lines: list[str] = [
            "# HELP prism_requests_total Total number of chat completion requests handled by Prism.",
            "# TYPE prism_requests_total counter",
        ]

        with self._lock:
            # Format counters
            for name, labeled_values in sorted(self._counters.items()):
                if name != "prism_requests_total":
                    lines.append(f"# HELP {name} Prism gateway metric {name}.")
                    lines.append(f"# TYPE {name} counter")

                for label_pairs, value in sorted(labeled_values.items()):
                    if label_pairs:
                        label_str = ",".join(
                            f'{k}="{v}"' for k, v in label_pairs
                        )
                        lines.append(f"{name}{{{label_str}}} {value}")
                    else:
                        lines.append(f"{name} {value}")

            # Latency summary
            if "prism_request_duration_seconds" in self._histograms:
                durations = self._histograms["prism_request_duration_seconds"]
                count = len(durations)
                total = sum(durations)
                lines.append("# HELP prism_request_duration_seconds Request duration in seconds.")
                lines.append("# TYPE prism_request_duration_seconds summary")
                lines.append(f"prism_request_duration_seconds_count {count}")
                lines.append(f"prism_request_duration_seconds_sum {total:.6f}")
                if count > 0:
                    sorted_durations = sorted(durations)
                    p50 = sorted_durations[int(count * 0.50)]
                    p95 = sorted_durations[min(int(count * 0.95), count - 1)]
                    p99 = sorted_durations[min(int(count * 0.99), count - 1)]
                    lines.append(f'prism_request_duration_seconds{{quantile="0.5"}} {p50:.6f}')
                    lines.append(f'prism_request_duration_seconds{{quantile="0.95"}} {p95:.6f}')
                    lines.append(f'prism_request_duration_seconds{{quantile="0.99"}} {p99:.6f}')

        return "\n".join(lines) + "\n"


# Global singleton metrics registry
metrics_registry = MetricsRegistry()

