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

import copy
import gc
import warnings
import weakref
from unittest.mock import Mock

import pytest

import hyperspy.events as he


class EventsBase:
    def on_trigger(self, **kwargs):
        self.triggered = True

    def on_trigger2(self, **kwargs):
        self.triggered2 = True

    def trigger_check(self, trigger, should_trigger, **kwargs):
        self.triggered = False
        trigger(**kwargs)
        assert self.triggered == should_trigger

    def trigger_check2(self, trigger, should_trigger, **kwargs):
        self.triggered2 = False
        trigger(**kwargs)
        assert self.triggered2 == should_trigger


class TestEventsSuppression(EventsBase):
    def setup_method(self, method):
        self.events = he.Events()

        self.events.a = he.Event()
        self.events.b = he.Event()
        self.events.c = he.Event()

        self.events.a.connect(self.on_trigger)
        self.events.a.connect(self.on_trigger2)
        self.events.b.connect(self.on_trigger)
        self.events.c.connect(self.on_trigger)

    def test_simple_suppression(self):
        with self.events.a.suppress():
            self.trigger_check(self.events.a.trigger, False)
            self.trigger_check(self.events.b.trigger, True)

        with self.events.suppress():
            self.trigger_check(self.events.a.trigger, False)
            self.trigger_check(self.events.b.trigger, False)
            self.trigger_check(self.events.c.trigger, False)

        self.trigger_check(self.events.a.trigger, True)
        self.trigger_check(self.events.b.trigger, True)
        self.trigger_check(self.events.c.trigger, True)

    def test_suppression_restore(self):
        with self.events.a.suppress():
            with self.events.suppress():
                self.trigger_check(self.events.a.trigger, False)
                self.trigger_check(self.events.b.trigger, False)
                self.trigger_check(self.events.c.trigger, False)

            self.trigger_check(self.events.a.trigger, False)
            self.trigger_check(self.events.b.trigger, True)
            self.trigger_check(self.events.c.trigger, True)

    def test_suppresion_nesting(self):
        with self.events.a.suppress():
            with self.events.suppress():
                self.events.c._suppress = False
                self.trigger_check(self.events.a.trigger, False)
                self.trigger_check(self.events.b.trigger, False)
                self.trigger_check(self.events.c.trigger, True)

                with self.events.suppress():
                    self.trigger_check(self.events.a.trigger, False)
                    self.trigger_check(self.events.b.trigger, False)
                    self.trigger_check(self.events.c.trigger, False)

                self.trigger_check(self.events.a.trigger, False)
                self.trigger_check(self.events.b.trigger, False)
                self.trigger_check(self.events.c.trigger, True)

            self.trigger_check(self.events.a.trigger, False)
            self.trigger_check(self.events.b.trigger, True)
            self.trigger_check(self.events.c.trigger, True)

    def test_suppression_single(self):
        with self.events.b.suppress():
            with self.events.a.suppress_callback(self.on_trigger):
                self.trigger_check(self.events.a.trigger, False)
                self.trigger_check2(self.events.a.trigger, True)
                self.trigger_check(self.events.b.trigger, False)
                self.trigger_check(self.events.c.trigger, True)

            self.trigger_check(self.events.a.trigger, True)
            self.trigger_check2(self.events.a.trigger, True)
            self.trigger_check(self.events.b.trigger, False)
            self.trigger_check(self.events.c.trigger, True)

        # Reverse order:
        with self.events.a.suppress_callback(self.on_trigger):
            with self.events.b.suppress():
                self.trigger_check(self.events.a.trigger, False)
                self.trigger_check2(self.events.a.trigger, True)
                self.trigger_check(self.events.b.trigger, False)
                self.trigger_check(self.events.c.trigger, True)

            self.trigger_check(self.events.a.trigger, False)
            self.trigger_check2(self.events.a.trigger, True)
            self.trigger_check(self.events.b.trigger, True)
            self.trigger_check(self.events.c.trigger, True)

    def test_exception_event(self):
        with pytest.raises(ValueError):
            try:
                with self.events.a.suppress():
                    self.trigger_check(self.events.a.trigger, False)
                    self.trigger_check(self.events.b.trigger, True)
                    self.trigger_check(self.events.c.trigger, True)
                    raise ValueError()
            finally:
                self.trigger_check(self.events.a.trigger, True)
                self.trigger_check(self.events.b.trigger, True)
                self.trigger_check(self.events.c.trigger, True)

    def test_exception_events(self):
        with pytest.raises(ValueError):
            try:
                with self.events.suppress():
                    self.trigger_check(self.events.a.trigger, False)
                    self.trigger_check(self.events.b.trigger, False)
                    self.trigger_check(self.events.c.trigger, False)
                    raise ValueError()
            finally:
                self.trigger_check(self.events.a.trigger, True)
                self.trigger_check(self.events.b.trigger, True)
                self.trigger_check(self.events.c.trigger, True)

    def test_exception_single(self):
        with pytest.raises(ValueError):
            try:
                with self.events.a.suppress_callback(self.on_trigger):
                    self.trigger_check(self.events.a.trigger, False)
                    self.trigger_check2(self.events.a.trigger, True)
                    self.trigger_check(self.events.b.trigger, True)
                    self.trigger_check(self.events.c.trigger, True)
                    raise ValueError()
            finally:
                self.trigger_check(self.events.a.trigger, True)
                self.trigger_check2(self.events.a.trigger, True)
                self.trigger_check(self.events.b.trigger, True)
                self.trigger_check(self.events.c.trigger, True)

    def test_exception_nested(self):
        with pytest.raises(ValueError):
            try:
                with self.events.a.suppress_callback(self.on_trigger):
                    try:
                        with self.events.a.suppress():
                            try:
                                with self.events.suppress():
                                    self.trigger_check(self.events.a.trigger, False)
                                    self.trigger_check2(self.events.a.trigger, False)
                                    self.trigger_check(self.events.b.trigger, False)
                                    self.trigger_check(self.events.c.trigger, False)
                                    raise ValueError()
                            finally:
                                self.trigger_check(self.events.a.trigger, False)
                                self.trigger_check2(self.events.a.trigger, False)
                                self.trigger_check(self.events.b.trigger, True)
                                self.trigger_check(self.events.c.trigger, True)
                    finally:
                        self.trigger_check(self.events.a.trigger, False)
                        self.trigger_check2(self.events.a.trigger, True)
                        self.trigger_check(self.events.b.trigger, True)
                        self.trigger_check(self.events.c.trigger, True)
            finally:
                self.trigger_check(self.events.a.trigger, True)
                self.trigger_check2(self.events.a.trigger, True)
                self.trigger_check(self.events.b.trigger, True)
                self.trigger_check(self.events.c.trigger, True)

    def test_suppress_wrong(self):
        with self.events.a.suppress_callback(f_a):
            self.trigger_check(self.events.a.trigger, True)
            self.trigger_check2(self.events.a.trigger, True)

    def test_suppressor_init_args(self):
        with self.events.b.suppress():
            es = he.EventSuppressor((self.events.a, self.on_trigger), self.events.c)
            with es.suppress():
                self.trigger_check(self.events.a.trigger, False)
                self.trigger_check2(self.events.a.trigger, True)
                self.trigger_check(self.events.b.trigger, False)
                self.trigger_check(self.events.c.trigger, False)
                with self.events.a.suppress_callback(self.on_trigger2):
                    self.trigger_check2(self.events.a.trigger, False)
                self.trigger_check2(self.events.a.trigger, True)

            self.trigger_check(self.events.a.trigger, True)
            self.trigger_check2(self.events.a.trigger, True)
            self.trigger_check(self.events.b.trigger, False)
            self.trigger_check(self.events.c.trigger, True)

        self.trigger_check(self.events.a.trigger, True)
        self.trigger_check2(self.events.a.trigger, True)
        self.trigger_check(self.events.b.trigger, True)
        self.trigger_check(self.events.c.trigger, True)

    def test_suppressor_add_args(self):
        with self.events.b.suppress():
            es = he.EventSuppressor()
            es.add((self.events.a, self.on_trigger), self.events.c)
            with es.suppress():
                self.trigger_check(self.events.a.trigger, False)
                self.trigger_check2(self.events.a.trigger, True)
                self.trigger_check(self.events.b.trigger, False)
                self.trigger_check(self.events.c.trigger, False)
                with self.events.a.suppress_callback(self.on_trigger2):
                    self.trigger_check2(self.events.a.trigger, False)
                self.trigger_check2(self.events.a.trigger, True)

            self.trigger_check(self.events.a.trigger, True)
            self.trigger_check2(self.events.a.trigger, True)
            self.trigger_check(self.events.b.trigger, False)
            self.trigger_check(self.events.c.trigger, True)

        self.trigger_check(self.events.a.trigger, True)
        self.trigger_check2(self.events.a.trigger, True)
        self.trigger_check(self.events.b.trigger, True)
        self.trigger_check(self.events.c.trigger, True)

    def test_suppressor_all_callback_in_events(self):
        with self.events.b.suppress():
            es = he.EventSuppressor()
            es.add(
                (self.events, self.on_trigger),
            )
            with es.suppress():
                self.trigger_check(self.events.a.trigger, False)
                self.trigger_check2(self.events.a.trigger, True)
                self.trigger_check(self.events.b.trigger, False)
                self.trigger_check(self.events.c.trigger, False)
                with self.events.a.suppress_callback(self.on_trigger2):
                    self.trigger_check2(self.events.a.trigger, False)
                self.trigger_check2(self.events.a.trigger, True)

            self.trigger_check(self.events.a.trigger, True)
            self.trigger_check2(self.events.a.trigger, True)
            self.trigger_check(self.events.b.trigger, False)
            self.trigger_check(self.events.c.trigger, True)

        self.trigger_check(self.events.a.trigger, True)
        self.trigger_check2(self.events.a.trigger, True)
        self.trigger_check(self.events.b.trigger, True)
        self.trigger_check(self.events.c.trigger, True)

    def test_suppressor_events_container(self):
        es = he.EventSuppressor()
        es.add(self.events)
        with es.suppress():
            self.trigger_check(self.events.a.trigger, False)
            self.trigger_check(self.events.b.trigger, False)
            self.trigger_check(self.events.c.trigger, False)

        self.trigger_check(self.events.a.trigger, True)
        self.trigger_check(self.events.b.trigger, True)
        self.trigger_check(self.events.c.trigger, True)


def f_a(**kwargs):
    pass


def f_b(**kwargs):
    pass


def f_c(**kwargs):
    pass


def f_d(a, b, c):
    pass


class TestEventsSignatures(EventsBase):
    def setup_method(self, method):
        self.events = he.Events()
        self.events.a = he.Event()

    def test_trigger_kwarg_validity(self):
        self.events.a.connect(lambda **kwargs: 0)
        self.events.a.connect(lambda: 0, [])
        self.events.a.connect(lambda one: 0, ["one"])
        self.events.a.connect(lambda one, two: 0, ["one", "two"])

        def lambda1(one, two=988):
            assert two == 988

        def lambda2(one, two=988):
            assert two != 988

        def lambda3(A, B=988):
            assert A != 988

        self.events.a.connect(lambda1, ["one"])
        self.events.a.connect(lambda2, ["one", "two"])
        self.events.a.connect(lambda3, {"one": "A", "two": "B"})
        self.events.a.trigger(one=2, two=5)
        self.events.a.trigger(one=2, two=5, three=8)
        self.events.a.connect(
            lambda one, two: 0,
        )
        with pytest.raises(TypeError):
            self.events.a.trigger(three=None)
        with pytest.raises(TypeError):
            self.events.a.trigger(one=2)

    def test_connected_and_disconnect(self):
        self.events.a.connect(f_a)
        self.events.a.connect(f_b, ["A", "B"])
        self.events.a.connect(f_c, {"a": "A", "b": "B"})
        self.events.a.connect(f_d, "auto")
        assert self.events.a.connected == set([f_a, f_b, f_c, f_d])
        self.events.a.disconnect(f_a)
        self.events.a.disconnect(f_b)
        self.events.a.disconnect(f_c)
        self.events.a.disconnect(f_d)
        assert self.events.a.connected == set([])

    def test_type(self):
        with pytest.raises(TypeError):
            self.events.a.connect("f_a")


def test_events_container_magic_attributes():
    events = he.Events()
    event = he.Event()
    events.event = event
    events.a = 3
    assert "event" in events.__dir__()
    assert "a" in events.__dir__()
    assert (
        repr(events) == "<hyperspy.events.Events: "
        "{'event': <hyperspy.events.Event: set()>}>"
    )
    del events.event
    del events.a
    assert "event" not in events.__dir__()
    assert "a" not in events.__dir__()


class TestTriggerArgResolution(EventsBase):
    def setup_method(self, method):
        self.events = he.Events()
        self.events.a = he.Event(arguments=["A", "B"])
        self.events.b = he.Event(arguments=["A", "B", ("C", "vC")])
        self.events.c = he.Event()

    def test_wrong_default_order(self):
        with pytest.raises(SyntaxError):
            self.events.d = he.Event(arguments=["A", ("C", "vC"), "B"])

    def test_wrong_kwarg_name(self):
        with pytest.raises(ValueError):
            self.events.d = he.Event(arguments=["A", "B+"])

    def test_arguments(self):
        assert self.events.a.arguments == ("A", "B")
        assert self.events.b.arguments == ("A", "B", ("C", "vC"))
        assert self.events.c.arguments is None

    def test_some_kwargs_resolution(self):
        def lambda1(x=None):
            assert x is None

        def lambda2(A):
            assert A == "vA"

        def lambda3(A, B):
            assert (A, B) == ("vA", "vB")

        def lambda4(A, B):
            assert (A, B) == ("vA", "vB")

        def lambda5(**kwargs):
            assert (kwargs["A"], kwargs["B"]) == ("vA", "vB")

        def lambda6(A, B=None, C=None):
            assert (A, B, C) == ("vA", "vB", None)

        def lambda7(A, B=None, C=None):
            assert (A, B, C) == ("vA", "vB", "vC")

        self.events.a.connect(lambda1, [])
        self.events.a.connect(lambda2, ["A"])
        self.events.a.connect(lambda3, ["A", "B"])
        self.events.a.connect(lambda4, "auto")
        with pytest.raises(NotImplementedError):
            self.events.a.connect(function=lambda *args: 0, kwargs="auto")

        self.events.a.connect(lambda5, "auto")
        self.events.a.connect(lambda6, ["A", "B"])
        # Test default argument
        self.events.b.connect(lambda7)
        self.events.a.trigger(A="vA", B="vB")
        self.events.b.trigger(A="vA", B="vB")
        with pytest.raises(TypeError):
            self.events.a.trigger(A="vA", B="vB", C="vC")
        self.events.a.trigger(A="vA", B="vB")
        self.events.a.trigger(B="vB", A="vA")
        with pytest.raises(TypeError):
            self.events.a.trigger(A="vA", C="vC", B="vB", D="vD")

    def test_not_connected(self):
        with pytest.raises(ValueError):
            self.events.a.disconnect(lambda: 0)

    def test_already_connected(self):
        def f():
            pass

        self.events.a.connect(f)
        with pytest.raises(ValueError):
            self.events.a.connect(f)

    def test_deepcopy(self):
        def f():
            pass

        self.events.a.connect(f)
        assert f not in copy.deepcopy(self.events.a).connected

    def test_all_kwargs_resolution(self):
        def lambda1(A, B):
            assert (A, B) == ("vA", "vB")

        def lambda2(x=None, y=None, A=None, B=None):
            assert (x, y, A, B) == (None, None, "vA", "vB")

        self.events.a.connect(lambda1)
        self.events.a.connect(lambda2)
        self.events.a.trigger(A="vA", B="vB")


# ─── Regression tests for psygnal-backed Event adapter ──────────────


def test_duplicate_connect_raises_valueerror():
    """Re-connecting the same function raises ValueError."""
    e = he.Event()
    fn = Mock()
    e.connect(fn)
    with pytest.raises(ValueError, match="already connected"):
        e.connect(fn)


def test_disconnect_unconnected_raises_valueerror():
    """Disconnecting an unconnected function raises ValueError."""
    e = he.Event()
    fn = Mock()
    with pytest.raises(ValueError, match="not connected"):
        e.disconnect(fn)


def test_exception_abort():
    """Exception in one callback aborts remaining callbacks."""
    e = he.Event()
    fn_b = Mock()

    def boom(**kw):
        raise RuntimeError("x")

    e.connect(boom)
    e.connect(fn_b)
    with pytest.raises(RuntimeError):
        e.trigger()
    fn_b.assert_not_called()


def test_dict_rename():
    """Dict kwargs mapping renames trigger kwargs to function kwargs."""
    e = he.Event()
    fn = Mock()
    e.connect(fn, {"obj": "widget"})
    e.trigger(obj=123)
    fn.assert_called_with(widget=123)


def test_suppress_callback():
    """suppress_callback temporarily disables then restores a callback."""
    e = he.Event()
    fn = Mock()
    e.connect(fn)
    with e.suppress_callback(fn):
        e.trigger()
        assert fn.call_count == 0
    e.trigger()
    assert fn.call_count == 1


def test_event_suppressor_with_events_and_callback():
    """EventSuppressor with (Events, callback) and (Event, callback) targets."""
    ev = he.Events()
    ev.a = he.Event()
    fn = Mock()
    ev.a.connect(fn)
    es = he.EventSuppressor((ev, fn), (ev.a, fn))
    with es.suppress():
        ev.a.trigger()
        assert fn.call_count == 0


def test_events_dynamic_registration():
    """Dynamic event registration via attribute assignment on Events."""
    ev = he.Events()
    ev.custom = he.Event()
    assert "custom" in dir(ev)
    assert ev.custom is ev.custom


def test_arguments_validation():
    """Event with restricted arguments rejects unknown kwargs."""
    e = he.Event(arguments=["obj"])
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        e.trigger(bad=1)


def test_kwargs_auto_mode():
    """'auto' mode passes only matching params, filters extra kwargs."""
    recorded = {}

    def fn(a, b=0):
        recorded["a"] = a
        recorded["b"] = b

    e = he.Event()
    e.connect(fn, kwargs="auto")
    e.trigger(a=1, b=2, extra=99)
    assert recorded == {"a": 1, "b": 2}


def test_deepcopy_no_connections():
    """Deep-copied Event has no connected callbacks."""
    e = he.Event()
    fn = Mock()
    e.connect(fn)
    e2 = copy.deepcopy(e)
    assert len(e2.connected) == 0


def test_kwargs_list_filter():
    """List/tuple filter passes only named kwargs with None for missing."""
    e = he.Event()
    fn = Mock()
    e.connect(fn, ["obj"])
    e.trigger(obj=123)
    fn.assert_called_with(obj=123)

    fn2 = Mock()
    e.connect(fn2, ["obj", "missing"])
    e.trigger(obj=456)
    fn2.assert_called_with(obj=456, missing=None)


def test_suppress_nesting():
    """Nested suppress contexts: inner exit does NOT restore; outer exit does."""
    e = he.Event()
    fn = Mock()
    e.connect(fn)
    with e.suppress():
        with e.suppress():
            e.trigger()
            assert fn.call_count == 0
        # Inner suppress exited but outer is still active
        e.trigger()
        assert fn.call_count == 0
    e.trigger()
    assert fn.call_count == 1


# ─── Weakref connection tests ───────────────────────────────────────


class TestWeakref:
    """Tests for weakref=True default behavior of Event.connect()."""

    def test_weakref_bound_method_auto_disconnect(self):
        """Bound method with default weakref=True auto-disconnects on GC."""
        e = he.Event()
        fn = Mock()

        class Obj:
            def method(self, **kwargs):
                fn()

        obj = Obj()
        e.connect(obj.method)
        assert len(e.connected) == 1

        del obj
        gc.collect()
        e.trigger()

        assert fn.call_count == 0
        # After trigger, dead weakrefs are cleaned up
        assert len(e.connected) == 0

    def test_weakref_lambda_strong_ref(self):
        """Lambda with weakref=True still gets a strong reference."""
        e = he.Event()
        fn = Mock()

        e.connect(lambda **kw: fn())
        e.trigger()

        assert fn.call_count == 1

    def test_weakref_false_preserves_strong_ref(self):
        """weakref=False keeps the object alive via a strong reference."""
        e = he.Event()
        fn = Mock()

        class Obj:
            def method(self, **kwargs):
                fn()

        obj = Obj()
        e.connect(obj.method, weakref=False)
        assert len(e.connected) == 1

        del obj
        gc.collect()
        e.trigger()

        # Object is still alive (held by strong ref in _wrappers)
        assert fn.call_count == 1
        assert len(e.connected) == 1

    def test_weakref_kill_switch(self):
        """HS_EVENT_WEAKREF=0 disables weakref, restores strong-ref behavior."""
        e = he.Event()
        fn = Mock()

        class Obj:
            def method(self, **kwargs):
                fn()

        obj = Obj()
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("HS_EVENT_WEAKREF", "0")
            e.connect(obj.method)

        assert len(e.connected) == 1

        del obj
        gc.collect()
        e.trigger()

        # Kill-switch active: strong reference preserved
        assert fn.call_count == 1
        assert len(e.connected) == 1


class TestWeakrefLeakDetection:
    def test_leak_bound_method_gone(self):
        e = he.Event()
        fn = Mock()

        class Obj:
            def method(self, **kwargs):
                fn()

        obj = Obj()
        e.connect(obj.method)
        assert len(e.connected) == 1

        del obj
        gc.collect()
        e.trigger()

        assert fn.call_count == 0
        assert len(e.connected) == 0

    def test_leak_strong_ref_keeps_callback(self):
        e = he.Event()
        fn = Mock()

        class Obj:
            def method(self, **kwargs):
                fn()

        obj = Obj()
        e.connect(obj.method)
        strong = obj  # noqa: F841
        del obj
        gc.collect()
        e.trigger()

        assert fn.call_count == 1
        assert len(e.connected) == 1

    def test_leak_weakref_direct(self):
        e = he.Event()
        fn = Mock()

        class Obj:
            def method(self, **kwargs):
                fn()

        obj = Obj()
        wm = weakref.WeakMethod(obj.method)
        e.connect(wm)
        assert len(e.connected) == 1
        # The wrapper calls wm() but discards the returned bound method,
        # so fn is never invoked
        e.trigger()
        assert fn.call_count == 0

        del obj
        gc.collect()
        e.trigger()
        assert fn.call_count == 0
        assert len(e.connected) == 1

    def test_leak_kill_switch_restores_strong(self, monkeypatch):
        e = he.Event()
        fn = Mock()

        class Obj:
            def method(self, **kwargs):
                fn()

        obj = Obj()
        monkeypatch.setenv("HS_EVENT_WEAKREF", "0")
        e.connect(obj.method)
        assert len(e.connected) == 1

        del obj
        gc.collect()
        e.trigger()

        assert fn.call_count == 1
        assert len(e.connected) == 1

    def test_leak_multiple_connections(self):
        e = he.Event()
        fn1 = Mock()
        fn2 = Mock()
        fn3 = Mock()

        class Obj:
            def __init__(self, fn):
                self.fn = fn

            def method(self, **kwargs):
                self.fn()

        obj1 = Obj(fn1)
        obj2 = Obj(fn2)
        obj3 = Obj(fn3)

        e.connect(obj1.method)
        e.connect(obj2.method)
        e.connect(obj3.method)
        assert len(e.connected) == 3

        del obj2
        gc.collect()
        e.trigger()

        fn1.assert_called_once()
        fn2.assert_not_called()
        fn3.assert_called_once()
        assert len(e.connected) == 2


def test_arguments_still_works():
    """Test that Event(arguments=...) still works without errors."""
    e = he.Event(arguments=["obj"])
    f = Mock()
    e.connect(f)
    e.trigger(obj=1)
    f.assert_called_once_with(obj=1)


# ─── Deprecation warning tests ───────────────────────────────────────


def test_deprecation_arguments():
    """Test that Event(arguments=...) no longer emits a deprecation warning.

    The deprecation was premature — psygnal.Signal type annotations are not active yet,
    so ``arguments`` is still the primary way to define event signatures during the
    transition. The warning is deferred to a future migration phase.
    """

    from hyperspy.exceptions import VisibleDeprecationWarning

    with warnings.catch_warnings():
        warnings.simplefilter("error", VisibleDeprecationWarning)
        he.Event(arguments=["obj"])


def test_deprecation_kwargs_non_all():
    """Test that connect(f, kwargs=...) with non-'all' emits warning."""
    from hyperspy.exceptions import VisibleDeprecationWarning

    e = he.Event()
    with pytest.warns(VisibleDeprecationWarning, match="kwargs.*deprecated"):
        e.connect(lambda **k: None, kwargs=["obj"])


def test_deprecation_weakref_false():
    """Test that connect(f, weakref=False) emits warning."""
    from hyperspy.exceptions import VisibleDeprecationWarning

    e = he.Event()
    with pytest.warns(VisibleDeprecationWarning, match="weakref=False.*deprecated"):
        e.connect(lambda **k: None, weakref=False)


def test_no_deprecation_on_default_path():
    """Test that default connect() path does NOT emit warnings."""
    import warnings

    e = he.Event()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        e.connect(lambda **k: None)  # should NOT warn


# ─── Regression tests for new dual API (emit/blocked/call) ──────────


def test_emit_basic():
    """Test that emit() dispatches to callback with positional args."""
    from unittest.mock import Mock

    from hyperspy.events import Event

    e = Event(arguments=["obj"])
    cb = Mock()
    e.connect(cb)
    e.emit(42)
    cb.assert_called_once_with(obj=42)


def test_emit_multiple_args():
    """Test emit() with multiple positional args."""
    from unittest.mock import Mock

    from hyperspy.events import Event

    e = Event(arguments=["obj", "value"])
    cb = Mock()
    e.connect(cb)
    e.emit(1, 99)
    cb.assert_called_once_with(obj=1, value=99)


def test_call_alias():
    """Test that __call__ is equivalent to emit()."""
    from unittest.mock import Mock

    from hyperspy.events import Event

    e = Event(arguments=["obj"])
    cb = Mock()
    e.connect(cb)
    e(42)
    cb.assert_called_once_with(obj=42)


def test_blocked_context():
    """Test that blocked() suppresses dispatch."""
    from unittest.mock import Mock

    from hyperspy.events import Event

    e = Event(arguments=["obj"])
    cb = Mock()
    e.connect(cb)
    with e.blocked():
        e.emit(42)
    cb.assert_not_called()


def test_blocked_nested():
    """Test nested blocked() context managers."""
    from unittest.mock import Mock

    from hyperspy.events import Event

    e = Event(arguments=["obj"])
    cb = Mock()
    e.connect(cb)
    with e.blocked():
        with e.blocked():
            e.emit(42)
        e.emit(43)
    e.emit(44)
    cb.assert_called_once_with(obj=44)


def test_trigger_still_works():
    """Test that trigger() still works as alias (no warning when flag is False)."""
    from unittest.mock import Mock

    from hyperspy.events import Event

    e = Event(arguments=["obj"])
    cb = Mock()
    e.connect(cb)
    e.trigger(obj=42)
    cb.assert_called_once_with(obj=42)


def test_events_container_blocked():
    """Test Events.blocked() suppresses all contained events."""
    from unittest.mock import Mock

    from hyperspy.events import Event, Events

    ev = Events()
    ev.test = Event(arguments=["obj"])
    cb = Mock()
    ev.test.connect(cb)
    with ev.blocked():
        ev.test.emit(42)
    cb.assert_not_called()


def test_emit_no_deprecation_warning():
    """Test that emit() does NOT emit VisibleDeprecationWarning."""
    import warnings

    from hyperspy.events import Event
    from hyperspy.exceptions import VisibleDeprecationWarning

    e = Event()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        e.emit()
        assert not any(issubclass(x.category, VisibleDeprecationWarning) for x in w), (
            "emit() should not emit VisibleDeprecationWarning"
        )


def test_blocked_no_deprecation_warning():
    """Test that blocked() does NOT emit VisibleDeprecationWarning."""
    import warnings

    from hyperspy.events import Event
    from hyperspy.exceptions import VisibleDeprecationWarning

    e = Event()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        with e.blocked():
            pass
        assert not any(issubclass(x.category, VisibleDeprecationWarning) for x in w), (
            "blocked() should not emit VisibleDeprecationWarning"
        )


def test_call_alias_no_deprecation_warning():
    """Test that __call__() does NOT emit VisibleDeprecationWarning."""
    import warnings

    from hyperspy.events import Event
    from hyperspy.exceptions import VisibleDeprecationWarning

    e = Event()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        e()
        assert not any(issubclass(x.category, VisibleDeprecationWarning) for x in w), (
            "__call__() should not emit VisibleDeprecationWarning"
        )


def test_emit_preserves_exception_abort():
    """Test that if callback A raises, callback B is NOT called."""
    from unittest.mock import Mock

    import pytest

    from hyperspy.events import Event

    e = Event(arguments=["obj"])

    def boom(**kw):
        raise RuntimeError("boom")

    cb_b = Mock()
    e.connect(boom)
    e.connect(cb_b)
    with pytest.raises(RuntimeError, match="boom"):
        e.emit(42)
    cb_b.assert_not_called()


def test_emit_with_no_arguments():
    """Test emit() with no arguments= set -- accepts any args."""
    from unittest.mock import Mock

    from hyperspy.events import Event

    e = Event()
    cb = Mock()
    e.connect(cb)
    e.emit(42, foo="bar")
    cb.assert_called_once()


def test_trigger_deprecation_warning():
    """Test that trigger() emits VisibleDeprecationWarning when flag is True."""
    import pytest

    import hyperspy.events as events_mod
    from hyperspy.events import Event
    from hyperspy.exceptions import VisibleDeprecationWarning

    old_flag = events_mod._EMIT_DEPRECATION_WARNINGS
    events_mod._EMIT_DEPRECATION_WARNINGS = True
    try:
        e = Event()
        with pytest.warns(VisibleDeprecationWarning, match="trigger.*deprecated"):
            e.trigger()
    finally:
        events_mod._EMIT_DEPRECATION_WARNINGS = old_flag


def test_suppress_deprecation_warning():
    """Test that suppress() emits VisibleDeprecationWarning when flag is True."""
    import pytest

    import hyperspy.events as events_mod
    from hyperspy.events import Event
    from hyperspy.exceptions import VisibleDeprecationWarning

    old_flag = events_mod._EMIT_DEPRECATION_WARNINGS
    events_mod._EMIT_DEPRECATION_WARNINGS = True
    try:
        e = Event()
        with pytest.warns(VisibleDeprecationWarning, match="suppress.*deprecated"):
            with e.suppress():
                pass
    finally:
        events_mod._EMIT_DEPRECATION_WARNINGS = old_flag


def test_suppress_callback_deprecation_warning():
    """Test that suppress_callback() emits VisibleDeprecationWarning when flag is True."""
    import pytest

    import hyperspy.events as events_mod
    from hyperspy.events import Event
    from hyperspy.exceptions import VisibleDeprecationWarning

    old_flag = events_mod._EMIT_DEPRECATION_WARNINGS
    events_mod._EMIT_DEPRECATION_WARNINGS = True
    try:
        e = Event()

        def f(**k):
            pass

        e.connect(f)
        with pytest.warns(
            VisibleDeprecationWarning, match="suppress_callback.*deprecated"
        ):
            with e.suppress_callback(f):
                pass
    finally:
        events_mod._EMIT_DEPRECATION_WARNINGS = old_flag
