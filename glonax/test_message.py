from glonax.message import Engine, EngineState


def test_engine():
    engine = Engine(
        actual_engine=48,
        driver_demand=92,
        rpm=1290,
        state=EngineState.REQUEST,
    )

    assert engine.is_running() == True
    assert engine.to_bytes() == b"\\0\x05\n\x10"
    assert Engine.from_bytes(engine.to_bytes()) == engine
