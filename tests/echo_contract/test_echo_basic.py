from pytaf.transport.echo import EchoConfig, EchoTransport
from pytaf.transport.spi import Budgets

B = Budgets(write_ms=200, complete_ms=200, read_ms=200, total_ms=800)


def test_open_close_transact_identity() -> None:
    t = EchoTransport("pytaf+echo://local", EchoConfig(latency_ms=1))
    t.open()
    out = t.transact(b"*IDN?", budgets=B)
    assert out == b"*IDN?"
    t.close()


def test_fragmentation_and_trailer() -> None:
    t = EchoTransport(
        "pytaf+echo://local", EchoConfig(latency_ms=1, fragment_bytes=2, delayed_trailer_ms=1)
    )
    t.open()
    out = t.transact(b"ABCDEFGH", budgets=B)
    assert out == b"ABCDEFGH"
    t.close()


def test_rst_abort_closes_transport() -> None:
    t = EchoTransport("pytaf+echo://local", EchoConfig(latency_ms=1, rst_after_bytes=3))
    t.open()
    try:
        t.transact(b"HELLO", budgets=B)
        raise AssertionError("ConnectionError expected")
    except ConnectionError:
        pass
    try:
        t.transact(b"*IDN?", budgets=B)
        raise AssertionError("RuntimeError expected after RST")
    except RuntimeError:
        pass
