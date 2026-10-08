"""Scoped synthetic observation time for reproducible native test inputs.

Provider/normalization clocks remain explicitly injected. This also controls
utc_now defaults on records whose constructors do not expose a clock parameter.
It never patches validators, hashing, transactions or monotonic timing. Use only
within isolated sequential test/profile children; original fixtures are unchanged.
"""

from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import patch


@contextmanager
def recorded_observation_clock(instant: datetime):
    if not isinstance(instant, datetime) or instant.utcoffset() is None:
        raise ValueError("recorded observation time must be timezone-aware")
    instant = instant.astimezone(UTC)

    class RecordedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz is not None else instant.replace(tzinfo=None)

    with patch("novelty_harness.domain.base.datetime", RecordedDateTime):
        yield lambda: instant
