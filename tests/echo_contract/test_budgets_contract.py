from pytaf.transport.spi import Budgets


def test_budgets_non_none():
    b = Budgets(write_ms=0, complete_ms=0, read_ms=0, total_ms=0)
    assert b.write_ms == 0 and b.total_ms == 0
