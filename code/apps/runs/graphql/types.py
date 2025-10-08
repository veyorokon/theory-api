"""GraphQL types for runs."""

from __future__ import annotations

from typing import List
import strawberry
from strawberry import auto

from apps.runs import models


@strawberry.django.type(models.RunOutput)
class RunOutputType:
    """RunOutput GraphQL type."""

    key: auto
    uri: auto
    path: auto
    content_type: auto
    size_bytes: auto
    etag: auto
    sha256: auto


@strawberry.django.type(models.Run)
class RunType:
    """Run GraphQL type."""

    id: auto
    ref: auto
    mode: auto
    adapter: auto
    status: auto
    error_code: auto
    error_message: auto
    image_digest_expected: auto
    image_digest_actual: auto
    drift_ok: auto
    inputs: auto
    started_at: auto
    ended_at: auto
    cost_micro: auto

    @strawberry.field
    def outputs(self) -> List[RunOutputType]:
        return self.outputs.all()

    @strawberry.field
    def duration_ms(self) -> int:
        return self.duration_ms
