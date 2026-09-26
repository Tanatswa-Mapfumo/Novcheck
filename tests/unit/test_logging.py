import json
import logging
from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest

from novelty_harness.runtime.logging import configure_logging


@pytest.fixture
def logger() -> Iterator[logging.Logger]:
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    try:
        yield logging.getLogger("test.exception")
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers = handlers
        root.setLevel(level)


def test_logger_exception_preserves_traceback_in_single_json_line(
    logger: logging.Logger, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging("INFO")
    try:
        raise ValueError("fixture failure")
    except ValueError:
        logger.exception("failed %s", "operation")

    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 1, "\n".join(lines)
    record = json.loads(lines[0])
    assert record["message"] == "failed operation"
    assert record["level"] == "ERROR"
    assert record["logger"] == "test.exception"
    assert datetime.fromisoformat(record["timestamp"]).utcoffset() == timedelta(0)
    assert "Traceback (most recent call last):" in record["exception"]
    assert "test_logger_exception_preserves_traceback_in_single_json_line" in record["exception"]
    assert "ValueError: fixture failure" in record["exception"]

    logger.info("recovered")
    plain_record = json.loads(capsys.readouterr().err)
    assert plain_record["message"] == "recovered"
    assert "exception" not in plain_record


@pytest.mark.parametrize("explicit_cause", [True, False], ids=["cause", "context"])
def test_logger_exception_preserves_exception_chain(
    logger: logging.Logger,
    capsys: pytest.CaptureFixture[str],
    explicit_cause: bool,
) -> None:
    configure_logging("INFO")
    try:
        try:
            raise ValueError("fixture root cause")
        except ValueError as cause:
            if explicit_cause:
                raise RuntimeError("fixture outer failure") from cause
            raise RuntimeError("fixture outer failure")
    except RuntimeError:
        logger.exception("chained failure")

    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["message"] == "chained failure"
    exception = record["exception"]
    assert exception.count("Traceback (most recent call last):") == 2
    assert exception.index("ValueError: fixture root cause") < exception.index(
        "RuntimeError: fixture outer failure"
    )
    if explicit_cause:
        assert "The above exception was the direct cause of the following exception:" in exception
    else:
        assert "During handling of the above exception, another exception occurred:" in exception
