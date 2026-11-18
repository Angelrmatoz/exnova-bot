"""Tests de la senal exhaustion de normal_five: la regla de trading activa."""

from bot.scripts.normal_five import entry_hour, exhaustion_signal


def _hist(mode="alt", n=59, final=None):
    t = 1794816000
    close = 1.1000
    rows = []
    for i in range(n):
        op = close
        if mode == "up":
            delta = 0.0002
        else:
            delta = 0.0002 if i % 2 == 0 else -0.0002
        cl = round(op + delta, 6)
        rows.append({
            "time": t,
            "open": op,
            "close": cl,
            "high": round(max(op, cl) + 0.0001, 6),
            "low": round(min(op, cl) - 0.0001, 6),
        })
        close = cl
        t += 300
    if final is not None:
        d_close, extra_hi, extra_lo = final
        op = close
        cl = round(op + d_close, 6)
        rows.append({
            "time": t,
            "open": op,
            "close": cl,
            "high": round(max(op, cl) + extra_hi, 6),
            "low": round(min(op, cl) - extra_lo, 6),
        })
    return rows


def test_exhaustion_put_con_z():
    sig = exhaustion_signal(_hist(final=(0.0020, 0.0001, 0.0001)))
    assert sig is not None
    side, z = sig
    assert side == "put"
    assert z > 2.0


def test_exhaustion_call_con_z():
    sig = exhaustion_signal(_hist(final=(-0.0020, 0.0001, 0.0001)))
    assert sig is not None
    side, z = sig
    assert side == "call"
    assert z > 2.0


def test_exhaustion_bloquea_rsi_extremo():
    assert exhaustion_signal(_hist(mode="up", final=(0.0040, 0.0002, 0.0002))) is None


def test_exhaustion_bloquea_cuerpo_chico():
    sig = exhaustion_signal(_hist(final=(0.0010, 0.0035, 0.0005)))
    assert sig is None


def test_exhaustion_bloquea_cuerpo_chico_bajista():
    sig = exhaustion_signal(_hist(final=(-0.0010, 0.0005, 0.0035)))
    assert sig is None


def test_exhaustion_bloquea_vela_plana():
    assert exhaustion_signal(_hist(final=(0.0000, 0.0001, 0.0001))) is None


def test_exhaustion_historia_corta():
    assert exhaustion_signal(_hist(n=10)) is None


def test_entry_hour_usa_apertura_siguiente():
    assert entry_hour(28500) == 8
    assert entry_hour(35970) == 10
    assert entry_hour(46770) == 13
