def test_package_exposes_version() -> None:
    import novelty_harness

    assert novelty_harness.__version__ == "0.1.0"
