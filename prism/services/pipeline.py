"""Pipeline orchestrator for the Prism LLM Gateway."""

from collections.abc import Awaitable, Callable

from prism.domain.errors import PrismError
from prism.domain.models import RequestContext


PipelineStage = Callable[
    [RequestContext],
    Awaitable[RequestContext],
]


class Pipeline:
    """Execute request-processing stages sequentially."""

    def __init__(
        self,
        stages: list[PipelineStage] | None = None,
    ) -> None:
        self.stages = stages or []

    async def run(
        self,
        context: RequestContext,
        stages: list[PipelineStage] | None = None,
    ) -> RequestContext:
        """
        Execute stages in order.

        Each stage receives the context and must return the updated
        context. A PrismError stops the pipeline immediately.
        """

        ordered_stages = (
            stages if stages is not None else self.stages
        )

        for stage in ordered_stages:
            stage_name = stage.__name__

            try:
                context = await stage(context)

            except PrismError:
                context.decision_trace.append(
                    f"{stage_name} failed"
                )
                raise

            context.decision_trace.append(
                f"{stage_name} completed"
            )

        return context
