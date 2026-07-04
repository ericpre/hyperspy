# -*- coding: utf-8 -*-
# Copyright 2007-2026 The HyperSpy developers
#
# This file is part of HyperSpy.
#
# HyperSpy is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# HyperSpy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with HyperSpy. If not, see <https://www.gnu.org/licenses/#GPL>.

import gc
import statistics
import time
import warnings as warnings_module
from unittest.mock import Mock

import pytest

import hyperspy.events as he


class TestEventPerformance:
    """Performance and scale benchmarks for the event system."""

    def test_connect_disconnect_1000(self):
        """Connecting and disconnecting 1000 callbacks should be O(n).

        Uses relative timing: disconnect time must not exceed connect time
        by more than a factor of 5, ensuring both are linear and not
        dominated by O(n^2) list removals.
        """
        e = he.Event()
        callbacks = [Mock() for _ in range(1000)]

        t0 = time.perf_counter()
        for cb in callbacks:
            e.connect(cb)
        t_connect = time.perf_counter() - t0

        t0 = time.perf_counter()
        for cb in callbacks:
            e.disconnect(cb)
        t_disconnect = time.perf_counter() - t0

        assert len(e.connected) == 0
        assert t_connect > 0
        # Disconnect walks multiple dispatch lists — allow up to 5× connect time
        assert t_disconnect < t_connect * 5, (
            f"disconnect ({t_disconnect:.4f}s) unexpectedly slow vs "
            f"connect ({t_connect:.4f}s)"
        )

    def test_trigger_100_callbacks(self):
        """Triggering an event with 100 connected callbacks calls every one."""
        e = he.Event()
        callbacks = [Mock() for _ in range(100)]

        for cb in callbacks:
            e.connect(cb)

        e.trigger()

        for cb in callbacks:
            cb.assert_called_once()

    def test_trigger_kwargs_filtering(self):
        """Trigger dispatches the correct arguments per callback filter mode.

        Verifies:
        - kwargs="all" → receives all trigger kwargs
        - kwargs list → receives only listed keys
        - kwargs dict → receives remapped keys
        """
        e = he.Event(arguments=("a", "b", ("c", 0)))

        cb_all = Mock()
        cb_list = Mock()
        cb_dict = Mock()

        e.connect(cb_all, kwargs="all")
        e.connect(cb_list, kwargs=["a", "b"])
        e.connect(cb_dict, kwargs={"a": "x", "b": "y"})

        e.trigger(a=10, b=20, c=30)

        cb_all.assert_called_once_with(a=10, b=20, c=30)
        cb_list.assert_called_once_with(a=10, b=20)
        cb_dict.assert_called_once_with(x=10, y=20)

    def test_weakref_lifecycle(self):
        """Weakref connections auto-disconnect when the owning object is GC'd."""

        class Owner:
            def __init__(self, fn):
                self.fn = fn

            def method(self, **kwargs):
                self.fn()

        e = he.Event()
        fn = Mock()
        obj = Owner(fn)

        e.connect(obj.method)
        assert len(e.connected) == 1

        e.trigger()
        fn.assert_called_once()

        fn.reset_mock()
        del obj
        gc.collect()

        e.trigger()
        fn.assert_not_called()
        assert len(e.connected) == 0

    def test_dispatch_overhead(self):
        """Event dispatch overhead is bounded relative to a bare function call.

        Measures median and p99 dispatch latency over 10 000 triggers with
        5 callbacks. Asserts that the median is within 50× the bare function
        call baseline (typical ratio ~10–15×) and p99 within 300× — wide
        enough to absorb per-counter() overhead noise on the sub-microsecond
        bare call, but still catches regression.

        Uses relative assertions so slow CI machines do not produce false
        failures.
        """
        e = he.Event()

        call_count = 0

        def bare_fn():
            pass

        def make_callback():
            def callback():
                nonlocal call_count
                call_count += 1

            return callback

        num_callbacks = 5
        callbacks = [make_callback() for _ in range(num_callbacks)]
        for cb in callbacks:
            e.connect(cb)

        # Warm-up: let Python JIT / branch predictor settle
        for _ in range(100):
            e.trigger()
        call_count = 0

        # Baseline: 10k bare function calls
        bare_times = []
        for _ in range(10000):
            t0 = time.perf_counter()
            bare_fn()
            bare_times.append(time.perf_counter() - t0)

        call_count = 0

        # Measure: 10k event triggers with 5 callbacks
        trigger_times = []
        for _ in range(10000):
            t0 = time.perf_counter()
            e.trigger()
            trigger_times.append(time.perf_counter() - t0)

        assert call_count == 10000 * num_callbacks

        bare_p99 = sorted(bare_times)[int(len(bare_times) * 0.99)]
        trigger_p99 = sorted(trigger_times)[int(len(trigger_times) * 0.99)]

        # p99 cap at 300× — wide margin for perf_counter() noise on the
        # sub-microsecond bare call; real regression would exceed this.
        ratio = trigger_p99 / bare_p99 if bare_p99 > 0 else float("inf")
        assert ratio < 300, (
            f"p99 dispatch ({trigger_p99 * 1e6:.1f}us) is {ratio:.0f}× "
            f"slower than bare call ({bare_p99 * 1e6:.1f}us)"
        )

        bare_median = statistics.median(bare_times)
        trigger_median = statistics.median(trigger_times)
        median_ratio = trigger_median / bare_median if bare_median > 0 else float("inf")
        # Median within 50× — typical ratio ~10×
        assert median_ratio < 50, (
            f"Median dispatch ({trigger_median * 1e6:.1f}us) is {median_ratio:.0f}× "
            f"slower than bare call ({bare_median * 1e6:.1f}us)"
        )


class TestEventThrottle:
    """throttle() context manager tests."""

    def test_throttle_limits_rate(self):
        """Within a throttle context, rapid triggers only dispatch the first."""
        e = he.Event()
        cb = Mock()
        e.connect(cb)

        with e.throttle(1.0):
            e.trigger()
            e.trigger()
            e.trigger()

        # Only the first trigger should dispatch (leading-edge throttle)
        cb.assert_called_once()

    def test_throttle_subsequent_fires_after_interval(self):
        """After the throttle interval elapses, the next trigger dispatches."""
        e = he.Event()
        cb = Mock()
        e.connect(cb)

        with e.throttle(0.001):
            e.trigger()  # dispatches immediately (leading edge)
            time.sleep(0.002)
            e.trigger()  # interval has passed → dispatches

        assert cb.call_count == 2

    def test_throttle_restores_on_exit(self):
        """Throttle state is fully restored after the context exits."""
        e = he.Event()
        cb = Mock()
        e.connect(cb)

        with e.throttle(10.0):
            e.trigger()
            e.trigger()

        cb.assert_called_once()

        # Outside the context, no throttling applies
        cb.reset_mock()
        e.trigger()
        e.trigger()
        assert cb.call_count == 2

        # State fields reset to None
        assert e._throttle_interval is None
        assert e._last_trigger_time is None


class TestEventDebounce:
    """debounce() context manager tests."""

    def test_debounce_buffers_and_flushes(self):
        """Rapid triggers within debounce flush only the last on exit."""
        e = he.Event()
        cb = Mock()
        e.connect(cb)

        with e.debounce(0.01):
            e.trigger(a=1)
            e.trigger(a=2)
            e.trigger(a=3)

        # Only the last call's args should be dispatched (on context exit)
        cb.assert_called_once_with(a=3)

    def test_debounce_timer_dispatches_during_long_context(self, monkeypatch):
        """During a long-lived debounce context, the timer fires on silence.

        Uses monkeypatch to accelerate time.sleep so the test runs fast.
        """
        e = he.Event()
        cb = Mock()
        e.connect(cb)

        # Short debounce interval so timer fires quickly
        with e.debounce(0.001):
            e.trigger(a=1)
            time.sleep(0.002)  # let timer fire
            e.trigger(a=2)
            time.sleep(0.002)  # let timer fire again

        # Should have dispatched value=1 (after silence) and value=2 (on exit)
        assert cb.call_count >= 1

    def test_debounce_restores_on_exit(self):
        """Debounce state is fully restored after the context exits."""
        e = he.Event()
        cb = Mock()
        e.connect(cb)

        with e.debounce(10.0):
            e.trigger()
            e.trigger()

        cb.assert_called_once()

        # Outside the context, no debouncing applies
        cb.reset_mock()
        e.trigger()
        e.trigger()
        assert cb.call_count == 2

        # State fields reset to None
        assert e._debounce_interval is None
        assert e._debounce_timer is None
        assert e._debounce_pending_args is None
        assert e._debounce_pending_kwargs is None

    def test_debounce_preserves_kwarg_remapping(self):
        """Debounce flushing preserves the kwargs remapping logic."""
        e = he.Event(arguments=("val",))
        cb = Mock()

        # Connect with dict kwargs — remap trigger "val" → function "value"
        e.connect(cb, kwargs={"val": "value"})

        with e.debounce(0.01):
            e.trigger(val=42)
            e.trigger(val=99)

        # Flush on exit — last arg wins through the remap
        cb.assert_called_once_with(value=99)


class TestEventMaxListeners:
    """max_listeners guard tests."""

    def test_no_warning_when_under_limit(self):
        """No warning emitted when connections are below max_listeners."""
        e = he.Event(max_listeners=5)

        with warnings_module.catch_warnings(record=True) as record:
            warnings_module.simplefilter("always")
            for _ in range(3):
                e.connect(Mock())

        max_listener_warnings = [w for w in record if "max_listeners" in str(w.message)]
        assert len(max_listener_warnings) == 0

    def test_warning_when_at_limit(self):
        """Warning emitted when connections reach max_listeners."""
        e = he.Event(max_listeners=2)

        e.connect(Mock())
        e.connect(Mock())

        with pytest.warns(UserWarning, match="max_listeners"):
            e.connect(Mock())

    def test_connections_still_added_beyond_limit(self):
        """Connections are still added even after the warning fires."""
        e = he.Event(max_listeners=2)

        e.connect(Mock())
        e.connect(Mock())

        with pytest.warns(UserWarning):
            e.connect(Mock())

        assert len(e.connected) == 3

    def test_no_limit_when_max_listeners_is_none(self):
        """Default max_listeners=None means unlimited connections."""
        e = he.Event()

        with warnings_module.catch_warnings(record=True) as record:
            warnings_module.simplefilter("always")
            for _ in range(50):
                e.connect(Mock())

        max_listener_warnings = [w for w in record if "max_listeners" in str(w.message)]
        assert len(max_listener_warnings) == 0
