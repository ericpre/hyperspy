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

import inspect
import os
import re
import threading
import time
import warnings
import weakref as _weakref_module
from collections.abc import Iterable
from contextlib import ExitStack, contextmanager

import psygnal

from hyperspy.exceptions import VisibleDeprecationWarning

# Set to True after all internal trigger()/suppress()/suppress_callback() calls
# are migrated to emit()/blocked()/guard-flag pattern (todo 13).
# When False, the deprecated methods work as silent aliases without warnings.
_EMIT_DEPRECATION_WARNINGS = True  # Enabled after internal migration complete


class Events:
    """
    Events container.

    All available events are attributes of this class.

    """

    def __init__(self):
        self._events = {}

    @contextmanager
    def blocked(self):
        """
        Use this function with a 'with' statement to temporarily suppress
        all callbacks of all events in the container. When the 'with' lock
        completes, the old suppression values will be restored.

        Examples
        --------
        >>> with obj.events.blocked(): # doctest: +SKIP
        ...     # Any events triggered by assignments are prevented:
        ...     obj.val_a = a
        ...     obj.val_b = b
        >>> # Trigger one event instead:
        >>> obj.events.values_changed.emit() # doctest: +SKIP

        See Also
        --------
        Event.blocked
        Event.suppress_callback
        """
        with ExitStack() as stack:
            for e in self._events.values():
                stack.enter_context(e.blocked())
            yield

    @contextmanager
    def suppress(self):
        """
        Use this function with a 'with' statement to temporarily suppress
        all callbacks of all events in the container. When the 'with' lock
        completes, the old suppression values will be restored.

        .. deprecated:: 3.0
            Use :meth:`blocked` instead.

        Examples
        --------
        >>> with obj.events.suppress(): # doctest: +SKIP
        ...     # Any events triggered by assignments are prevented:
        ...     obj.val_a = a
        ...     obj.val_b = b
        >>> # Trigger one event instead:
        >>> obj.events.values_changed.trigger() # doctest: +SKIP

        See Also
        --------
        Event.suppress
        Event.suppress_callback
        blocked
        """
        if _EMIT_DEPRECATION_WARNINGS:
            warnings.warn(
                "Events.suppress() is deprecated, use Events.blocked() instead. "
                "Will be removed in HyperSpy 3.0.",
                VisibleDeprecationWarning,
                stacklevel=2,
            )
        with self.blocked():
            yield

    def _update_doc(self):
        """
        Updates the doc to reflect the events that are contained
        """
        new_doc = self.__class__.__doc__
        new_doc += "\n\tEvents:\n\t-------\n"
        for name, e in self._events.items():
            edoc = inspect.getdoc(e) or ""
            doclines = edoc.splitlines()
            e_short = doclines[0] if len(doclines) > 0 else edoc
            new_doc += "\t%s :\n\t\t%s\n" % (name, e_short)
        new_doc = new_doc.replace("\t", "    ")
        self.__doc__ = new_doc

    def __setattr__(self, name, value):
        """
        Magic to enable having `Event`s as attributes, and keeping them
        separate from other attributes.

        If it's an `Event`, store it in self._events, otherwise set attribute
        in normal way.
        """
        if isinstance(value, Event):
            self._events[name] = value
            self._update_doc()
        else:
            super(Events, self).__setattr__(name, value)

    def __getattr__(self, name):
        """
        Magic to enable having `Event`s as attributes, and keeping them
        separate from other attributes.

        Returns Event attribute `name` (__getattr__ is only called if attribute
        could not be found in the normal way).
        """
        return self._events[name]

    def __delattr__(self, name):
        """
        Magic to enable having `Event`s as attributes, and keeping them
        separate from other attributes.

        Deletes attribute from self._events if present, otherwise delete
        attribute in normal way.
        """
        if name in self._events:
            del self._events[name]
            self._update_doc()
        else:
            super(Events, self).__delattr__(name)

    def __dir__(self):
        """
        Magic to enable having `Event`s as attributes, and keeping them
        separate from other attributes.

        Makes sure tab-completion works in IPython etc.
        """
        d = dir(type(self))
        d.extend(self.__dict__.keys())
        d.extend(self._events.keys())
        return sorted(set(d))

    def __iter__(self):
        """
        Allows iteration of all events in the container
        """
        return self._events.values().__iter__()

    def __repr__(self):
        return "<hyperspy.events.Events: " + repr(self._events) + ">"


class Event:
    """
    Events class

    """

    _re_arg_name = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")

    def __init__(self, doc="", arguments=None, max_listeners=None):
        """
        Parameters
        ----------
        doc : str
            Optional docstring for the new Event.
        arguments : iterable
            Pass to define the arguments of the trigger() function. Each
            element must either be an argument name, or a tuple containing
            the argument name and the argument's default value.
        max_listeners : int or None, default None
            Maximum number of connected callbacks. If set, a warning is
            emitted when connecting beyond this limit. None means no limit.

        Examples
        --------
        >>> from hyperspy.events import Event
        >>> Event()
        <hyperspy.events.Event: set()>
        >>> Event(doc="This event has a docstring!").__doc__
        'This event has a docstring!'
        >>> e1 = Event()
        >>> e2 = Event(arguments=('arg1', ('arg2', None)))
        >>> e1.trigger(arg1=12, arg2=43, arg3='str', arg4=4.3)  # Can trigger with whatever
        >>> e2.trigger(arg1=11, arg2=22, arg3=3.4) # doctest: +SKIP
        Traceback (most recent call last):
            ...
        TypeError: trigger() got an unexpected keyword argument 'arg3'

        """
        if arguments is not None:
            warnings.warn(
                "The 'arguments' parameter is deprecated and will be removed "
                "in HyperSpy 3.0. Use psygnal.Signal with type annotations "
                "instead.",
                VisibleDeprecationWarning,
                stacklevel=2,
            )
        self.__doc__ = doc
        self._arguments = tuple(arguments) if arguments else None
        self._signal = psygnal.Signal()
        self._wrappers = {}  # function → wrapper function
        self._weakref_data = {}  # wrapper → weakref.WeakMethod (for weak connections)
        self._suppressed_wrappers = set()  # set of wrapper functions
        self._suppress_count = 0
        self.max_listeners = max_listeners
        # Dispatch-order lists: "all" wrappers first, then list, then dict.
        # Order matters — one failing callback aborts remaining dispatch,
        # and consumers rely on "all"-connected callbacks failing first.
        self._dispatch_all = []
        self._dispatch_some = []
        self._dispatch_map = []
        # Throttle state: when _throttle_interval is set, trigger() fires at
        # most once per interval (seconds). _last_trigger_time is the
        # perf_counter() value of the last successful dispatch.
        self._throttle_interval = None
        self._last_trigger_time = None
        # Debounce state: when _debounce_interval is set, trigger() buffers
        # args/kwargs and dispatches on context exit (or after the timer fires
        # during a long-lived context).
        self._debounce_interval = None
        self._debounce_timer = None
        self._debounce_pending_args = None
        self._debounce_pending_kwargs = None

        if arguments:
            self._arg_names = []
            self._arg_defaults = {}
            for arg in arguments:
                if isinstance(arg, (tuple, list)):
                    if len(self._arg_defaults) == 0 and len(self._arg_names) > 0:
                        # First default encountered; mark that defaults have begun.
                        pass
                    name = arg[0]
                    default = arg[1]
                    m = self._re_arg_name.match(name)
                    if m is None or m.end() != len(name):
                        raise ValueError("Argument name invalid: %s" % name)
                    self._arg_names.append(name)
                    self._arg_defaults[name] = default
                else:
                    if self._arg_defaults:
                        raise SyntaxError(
                            "non-default argument follows default argument"
                        )
                    m = self._re_arg_name.match(arg)
                    if m is None or m.end() != len(arg):
                        raise ValueError("Argument name invalid: %s" % arg)
                    self._arg_names.append(arg)
        else:
            self._arg_names = None
            self._arg_defaults = None

    @property
    def arguments(self):
        return self._arguments

    @property
    def _suppress(self):
        """Backward-compatible boolean view of suppression state."""
        return self._suppress_count > 0

    @_suppress.setter
    def _suppress(self, value):
        """Backward-compatible setter: True = ensure >= 1, False = reset to 0."""
        if value:
            self._suppress_count = max(self._suppress_count, 1)
        else:
            self._suppress_count = 0

    @contextmanager
    def blocked(self):
        """
        Use this function with a 'with' statement to temporarily suppress
        all callbacks of the event. When the 'with' lock completes, the old
        suppression values will be restored.

        Examples
        --------
        >>> with obj.events.myevent.blocked(): # doctest: +SKIP
        ...     # These would normally both trigger myevent:
        ...     obj.val_a = a
        ...     obj.val_b = b

        Trigger manually once:
        >>> obj.events.myevent.emit() # doctest: +SKIP

        See Also
        --------
        suppress_callback
        Events.blocked
        """
        self._suppress_count += 1
        try:
            yield
        finally:
            self._suppress_count -= 1

    @contextmanager
    def suppress(self):
        """
        Use this function with a 'with' statement to temporarily suppress
        all events in the container. When the 'with' lock completes, the old
        suppression values will be restored.

        .. deprecated:: 3.0
            Use :meth:`blocked` instead.

        Examples
        --------
        >>> with obj.events.myevent.suppress(): # doctest: +SKIP
        ...     # These would normally both trigger myevent:
        ...     obj.val_a = a
        ...     obj.val_b = b

        Trigger manually once:
        >>> obj.events.myevent.trigger() # doctest: +SKIP

        See Also
        --------
        suppress_callback
        Events.suppress
        blocked
        """
        if _EMIT_DEPRECATION_WARNINGS:
            warnings.warn(
                "suppress() is deprecated, use blocked() instead. "
                "Will be removed in HyperSpy 3.0.",
                VisibleDeprecationWarning,
                stacklevel=2,
            )
        with self.blocked():
            yield

    @contextmanager
    def suppress_callback(self, function):
        """
        Use this function with a 'with' statement to temporarily suppress
        a single callback from being called. All other connected callbacks
        will trigger. When the 'with' lock completes, the old suppression value
        will be restored.

        Examples
        --------

        >>> with obj.events.myevent.suppress_callback(f): # doctest: +SKIP
        ...     # Events will trigger as normal, but `f` will not be called
        ...     obj.val_a = a
        ...     obj.val_b = b
        >>> # Here, `f` will be called as before:
        >>> obj.events.myevent.trigger() # doctest: +SKIP

        See Also
        --------
        suppress
        Events.suppress
        """
        if _EMIT_DEPRECATION_WARNINGS:
            warnings.warn(
                "suppress_callback() is deprecated. Use the guard-flag pattern "
                "instead: the callback checks its own flag and returns early. "
                "Will be removed in HyperSpy 3.0.",
                VisibleDeprecationWarning,
                stacklevel=2,
            )
        # Silently allow suppressing an unconnected function — no-op.
        wrapper = self._wrappers.get(function)
        if wrapper is None:
            # Check weak connections
            for w, wm in self._weakref_data.items():
                if wm() == function:
                    wrapper = w
                    break
        if wrapper is None:
            yield
            return
        was_suppressed = wrapper in self._suppressed_wrappers
        if not was_suppressed:
            self._suppressed_wrappers.add(wrapper)
        try:
            yield
        finally:
            if not was_suppressed:
                self._suppressed_wrappers.discard(wrapper)

    @contextmanager
    def throttle(self, interval):
        """Context manager that limits ``trigger()`` to at most once per interval.

        While active, repeated ``trigger()`` calls within *interval* seconds
        are silently ignored — only the first call dispatches, then the timer
        must elapse before the next dispatch.

        Parameters
        ----------
        interval : float
            Minimum seconds between allowed dispatches.

        Notes
        -----
        Uses ``psygnal.throttled`` semantics (leading edge by default).
        For the psygnal-level decorator, see ``psygnal.throttled()`` which
        wraps individual callbacks rather than the event as a whole.
        """
        old_interval = self._throttle_interval
        old_last = self._last_trigger_time
        self._throttle_interval = interval
        self._last_trigger_time = None
        try:
            yield
        finally:
            self._throttle_interval = old_interval
            self._last_trigger_time = old_last

    @contextmanager
    def debounce(self, interval):
        """Context manager that defers ``trigger()`` dispatch until silence.

        While active, ``trigger()`` calls are buffered: only the last call's
        arguments are dispatched, and only after *interval* seconds have
        passed without a new trigger. On context exit, any pending dispatch
        is flushed immediately.

        Parameters
        ----------
        interval : float
            Seconds of silence required before dispatching.

        Notes
        -----
        Debounce uses a ``threading.Timer`` for delayed dispatch during
        long-lived contexts. On context exit the timer is cancelled and
        the last pending trigger is flushed synchronously.
        For the psygnal-level decorator, see ``psygnal.debounced()`` which
        wraps individual callbacks rather than the event as a whole.
        """
        old_interval = self._debounce_interval
        old_timer = self._debounce_timer
        old_args = self._debounce_pending_args
        old_kwargs = self._debounce_pending_kwargs
        self._debounce_interval = interval
        self._debounce_timer = None
        self._debounce_pending_args = None
        self._debounce_pending_kwargs = None
        try:
            yield
        finally:
            # Cancel any pending timer so it doesn't fire after we exit
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
                self._debounce_timer = None
            # Flush the last pending trigger synchronously
            if (
                self._debounce_pending_args is not None
                or self._debounce_pending_kwargs is not None
            ):
                saved_args = self._debounce_pending_args or ()
                saved_kwargs = self._debounce_pending_kwargs or {}
                self._debounce_pending_args = None
                self._debounce_pending_kwargs = None
                # Bypass debounce and throttle during flush so dispatch
                # actually happens — otherwise flush deadlocks itself.
                saved_debounce = self._debounce_interval
                saved_throttle = self._throttle_interval
                self._debounce_interval = None
                self._throttle_interval = None
                try:
                    self.emit(*saved_args, **saved_kwargs)
                finally:
                    self._debounce_interval = saved_debounce
                    self._throttle_interval = saved_throttle
            # Restore outer context state (supports nesting)
            self._debounce_interval = old_interval
            self._debounce_timer = old_timer
            self._debounce_pending_args = old_args
            self._debounce_pending_kwargs = old_kwargs

    def _debounce_timer_callback(self):
        """Callback fired by threading.Timer when debounce silence elapses.

        Dispatches the last buffered trigger args synchronously, bypassing
        throttle/debounce guards so the dispatch actually executes.
        """
        args = self._debounce_pending_args or ()
        kwargs = self._debounce_pending_kwargs or {}
        self._debounce_timer = None
        self._debounce_pending_args = None
        self._debounce_pending_kwargs = None
        # Bypass both throttle and debounce so dispatch is not re-guarded
        saved_debounce = self._debounce_interval
        saved_throttle = self._throttle_interval
        self._debounce_interval = None
        self._throttle_interval = None
        try:
            self.emit(*args, **kwargs)
        finally:
            self._debounce_interval = saved_debounce
            self._throttle_interval = saved_throttle

    @property
    def connected(self):
        """Connected functions.

        For weakref connections, only functions whose owner object is still
        alive are included.
        """
        result = set(self._wrappers.keys())
        for wrapper in self._weakref_data:
            wm = self._weakref_data[wrapper]
            fn = wm()
            if fn is not None:
                result.add(fn)
        return result

    def connect(self, function, kwargs="all", weakref=None):
        """
        Connects a function to the event.

        Parameters
        ----------
        function : callable
            The function to call when the event triggers.
        kwargs : tuple or list, dict, str {``'all'`` | ``'auto'``}, default ``"all"``
            If ``"all"``, all the trigger keyword arguments are passed to the
            function. If a list or tuple of strings, only those keyword
            arguments that are in the tuple or list are passed. If empty,
            no keyword argument is passed. If dictionary, the keyword arguments
            of trigger are mapped as indicated in the dictionary. For example,
            ``{"a" : "b"}`` maps the trigger argument "a" to the function argument
            "b".
        weakref : bool or None, default None
            If ``True`` and ``function`` is a bound method with ``kwargs="all"``,
            uses ``weakref.WeakMethod`` so the connection is automatically
            removed when the object is garbage collected.
            If ``True`` and ``function`` is a plain function or lambda, a
            strong reference is used (plain functions cannot be weak
            referenced).
            If ``kwargs`` is a dict or list, ``weakref`` has no effect because
            the wrapper closure holds the function strongly regardless.
            If ``None`` (default), the effective value is determined by the
            ``HS_EVENT_WEAKREF`` environment variable (default ``True``). Set
            ``HS_EVENT_WEAKREF=0`` to disable weak references globally.

        See Also
        --------
        disconnect

        """
        if not callable(function):
            raise TypeError("Only callables can be registered")
        if function in self._wrappers:
            raise ValueError("Function %s already connected to %s." % (function, self))

        if kwargs != "all":
            warnings.warn(
                "The 'kwargs' parameter with non-'all' values is deprecated "
                "and will be removed in HyperSpy 3.0. "
                "Use explicit wrapper functions instead.",
                VisibleDeprecationWarning,
                stacklevel=2,
            )

        # Check max_listeners before connecting
        if self.max_listeners is not None:
            current_count = len(self._wrappers) + len(self._weakref_data)
            if current_count >= self.max_listeners:
                warnings.warn(
                    f"Event has reached max_listeners ({self.max_listeners}). "
                    f"New connections will still be added but consider "
                    f"disconnecting unused callbacks.",
                    stacklevel=2,
                )

        # Resolve "auto" mode by inspecting the function signature
        resolved_kwargs = kwargs
        if kwargs == "auto":
            spec = inspect.signature(function)
            _has_args = False
            _has_kwargs = False
            _normal_params = []
            for name, par in spec.parameters.items():
                if par.kind == par.VAR_POSITIONAL:
                    _has_args = True
                elif par.kind == par.VAR_KEYWORD:
                    _has_kwargs = True
                else:
                    _normal_params.append(name)
            if _has_args and not _has_kwargs:
                raise NotImplementedError(
                    "Connecting to variable argument "
                    "functions is not supported in auto "
                    "connection mode."
                )
            elif _has_kwargs:
                resolved_kwargs = "all"
            else:
                resolved_kwargs = _normal_params

        # Determine effective weakref setting
        weakref_explicitly_false = weakref is False
        if weakref is None:
            env_val = os.environ.get("HS_EVENT_WEAKREF", "1")
            weakref = env_val != "0"

        if weakref_explicitly_false:
            warnings.warn(
                "The 'weakref=False' option is deprecated and will be "
                "removed in HyperSpy 3.0. Use the HS_EVENT_WEAKREF=0 "
                "environment variable for debugging.",
                VisibleDeprecationWarning,
                stacklevel=2,
            )

        # Weakref only applies to kwargs="all" with bound methods.
        # Plain functions/lambdas cannot be weak-referenced.
        # For dict/list kwargs, the wrapper closure holds the function
        # strongly regardless of weakref.
        use_weakref = (
            weakref and resolved_kwargs == "all" and inspect.ismethod(function)
        )

        # Create the wrapper function based on the kwargs mode
        if resolved_kwargs == "all":
            if use_weakref:
                ref = _weakref_module.WeakMethod(function)

                def wrapper(**event_kwargs):
                    fn = ref()
                    if fn is not None:
                        fn(**event_kwargs)

                self._dispatch_all.append(wrapper)
                self._weakref_data[wrapper] = ref
            else:

                def wrapper(**event_kwargs):
                    function(**event_kwargs)

                self._dispatch_all.append(wrapper)
                self._wrappers[function] = wrapper

        elif isinstance(resolved_kwargs, dict):
            rename_map = resolved_kwargs

            def wrapper(**event_kwargs):
                function(**{fn: event_kwargs[tn] for tn, fn in rename_map.items()})

            self._dispatch_map.append(wrapper)
            self._wrappers[function] = wrapper

        elif isinstance(resolved_kwargs, (tuple, list)):
            kw_list = tuple(resolved_kwargs)

            def wrapper(**event_kwargs):
                function(**{kw: event_kwargs.get(kw, None) for kw in kw_list})

            self._dispatch_some.append(wrapper)
            self._wrappers[function] = wrapper

        else:
            raise ValueError("Invalid value passed to kwargs.")

        return function

    def disconnect(self, function):
        """
        Disconnects a function from the event. The passed function will be
        disconnected irregardless of which 'nargs' argument was passed to
        connect().

        If you only need to temporarily prevent a function from being called,
        single callback suppression is supported by the `suppress_callback`
        context manager.

        Parameters
        ----------
        function: function
        return_connection_kwargs: bool, default False
            If True, returns the kwargs that would reconnect the function as
            it was.

        See Also
        --------
        connect
        suppress_callback
        """
        # Check strong connections first
        if function in self._wrappers:
            wrapper = self._wrappers[function]
            self._suppressed_wrappers.discard(wrapper)
            for lst in (
                self._dispatch_all,
                self._dispatch_some,
                self._dispatch_map,
            ):
                if wrapper in lst:
                    lst.remove(wrapper)
                    break
            self._weakref_data.pop(wrapper, None)
            del self._wrappers[function]
            return

        # Check weak connections
        for wrapper, wm in list(self._weakref_data.items()):
            if wm() == function:
                self._suppressed_wrappers.discard(wrapper)
                for lst in (
                    self._dispatch_all,
                    self._dispatch_some,
                    self._dispatch_map,
                ):
                    if wrapper in lst:
                        lst.remove(wrapper)
                        break
                del self._weakref_data[wrapper]
                return

        raise ValueError("The %s function is not connected to %s." % (function, self))

    def _dispatch(self, **kwargs):
        """Internal dispatch loop: iterate connected callbacks in order.

        Dispatch order:
        1. "all" callbacks first  → fail-early for unexpected kwargs
        2. list-filter callbacks  → each receives a subset of kwargs
        3. dict-rename callbacks  → remap trigger names to function names

        A failing callback aborts the remaining dispatch (no try/except).
        """
        connected_all = [
            w for w in self._dispatch_all if w not in self._suppressed_wrappers
        ]
        for wrapper in connected_all:
            wrapper(**kwargs)

        for wrapper in list(self._dispatch_some):
            if wrapper not in self._suppressed_wrappers:
                wrapper(**kwargs)

        for wrapper in list(self._dispatch_map):
            if wrapper not in self._suppressed_wrappers:
                wrapper(**kwargs)

    def emit(self, *args, **kwargs):
        """
        Triggers the event. If the event is suppressed, this does nothing.
        Otherwise it calls all the connected functions with the arguments as
        specified when connected.

        Positional arguments are mapped to argument names via ``_arguments``
        when the event was created with named arguments.

        See Also
        --------
        blocked
        suppress_callback
        Events.blocked
        throttle
        debounce
        trigger
        """
        if self._suppress_count > 0:
            return

        # Throttle guard: skip dispatch if called within the throttle interval
        # since the last successful trigger. Uses time.perf_counter() for
        # monotonic, high-resolution timing.
        if self._throttle_interval is not None:
            now = time.perf_counter()
            if (
                self._last_trigger_time is not None
                and now - self._last_trigger_time < self._throttle_interval
            ):
                return
            self._last_trigger_time = now

        # Debounce guard: buffer the last args/kwargs and defer dispatch.
        # A threading.Timer fires after _debounce_interval seconds of silence;
        # on context exit, the buffer is flushed synchronously.
        if self._debounce_interval is not None:
            self._debounce_pending_args = args
            self._debounce_pending_kwargs = kwargs
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(
                self._debounce_interval,
                self._debounce_timer_callback,
            )
            self._debounce_timer.start()
            return

        # Clean up dead weakref connections before dispatching
        dead_wrappers = [w for w, wm in self._weakref_data.items() if wm() is None]
        for wrapper in dead_wrappers:
            for lst in (
                self._dispatch_all,
                self._dispatch_some,
                self._dispatch_map,
            ):
                if wrapper in lst:
                    lst.remove(wrapper)
            del self._weakref_data[wrapper]

        # Map positional arguments to named arguments.
        # Consumers like hyperspy/interactive.py:137 call trigger(obj)
        # where 'obj' is the first argument in self._arguments.
        if self._arguments is not None and args:
            for i, value in enumerate(args):
                if i < len(self._arg_names):
                    name = self._arg_names[i]
                    if name in kwargs:
                        raise TypeError(
                            "emit() got multiple values for argument '%s'" % name
                        )
                    kwargs[name] = value

        # Validate arguments if the event has named arguments
        if self._arguments is not None:
            for key in kwargs:
                if key not in self._arg_names:
                    raise TypeError(
                        "emit() got an unexpected keyword argument '%s'" % key
                    )
            # Apply default values for args not provided in the trigger call
            if self._arg_defaults:
                for name, default in self._arg_defaults.items():
                    if name not in kwargs:
                        kwargs[name] = default

        self._dispatch(**kwargs)

    def trigger(self, *args, **kwargs):
        """
        Triggers the event. If the event is suppressed, this does nothing.
        Otherwise it calls all the connected functions with the arguments as
        specified when connected.

        .. deprecated:: 3.0
            Use :meth:`emit` instead.

        See Also
        --------
        emit
        blocked
        suppress_callback
        Events.blocked
        throttle
        debounce
        """
        if _EMIT_DEPRECATION_WARNINGS:
            warnings.warn(
                "trigger() is deprecated, use emit() instead. "
                "Will be removed in HyperSpy 3.0.",
                VisibleDeprecationWarning,
                stacklevel=2,
            )
        return self.emit(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        """Alias for :meth:`emit`.

        Allows calling the event object directly as a function:
        ``event(arg1, arg2, kw=val)`` is equivalent to
        ``event.emit(arg1, arg2, kw=val)``.
        """
        return self.emit(*args, **kwargs)

    def __deepcopy__(self, memo):
        dc = type(self)(doc=self.__doc__, arguments=self._arguments)
        memo[id(self)] = dc
        return dc

    def __str__(self):
        if self.__doc__:
            edoc = inspect.getdoc(self) or ""
            doclines = edoc.splitlines()
            e_short = doclines[0] if len(doclines) > 0 else edoc
            text = (
                "<hyperspy.events.Event: " + e_short + ": " + str(self.connected) + ">"
            )
        else:
            text = self.__repr__()
        return text

    def __repr__(self):
        return "<hyperspy.events.Event: " + repr(self.connected) + ">"


class EventSuppressor(object):
    """
    Object to enforce a variety of suppression types simultaneously

    Targets to be suppressed can be added by the function `add()`, or given
    in the constructor. Valid targets are:

    * `Event`: The entire Event will be suppressed
    * `Events`: All events in th container will be suppressed
    * (Event, callback): The callback will be suppressed in Event
    * (Events, callback): The callback will be suppressed in each event in
      Events where it is connected.
    * Any iterable collection of the above target types

    Examples
    --------
    >>> es = EventSuppressor((event1, callback1), (event1, callback2)) # doctest: +SKIP
    >>> es.add(event2, callback2) # doctest: +SKIP
    >>> es.add(event3) # doctest: +SKIP
    >>> es.add(events_container1) # doctest: +SKIP
    >>> es.add(events_container2, callback1) # doctest: +SKIP
    >>> es.add(event4, (events_container3, callback2)) # doctest: +SKIP

    >>> with es.suppress(): # doctest: +SKIP
    ...     do_something()
    """

    def __init__(self, *to_suppress):
        self._cms = []
        if len(to_suppress) > 0:
            self.add(*to_suppress)

    def _add_single(self, target):
        # Identify and initializes the CM, but doesn't enter it
        if self._is_tuple_target(target):
            if isinstance(target[0], Event):
                cm = target[0].suppress_callback(target[1])
                self._cms.append(cm)
            else:
                # Don't check for function presence in event now:
                # suppress_callback does this when entering
                for e in target[0]:
                    self._cms.append(e.suppress_callback(target[1]))
        else:
            cm = target.suppress()
            self._cms.append(cm)

    def _is_tuple_target(self, candidate):
        v = (
            isinstance(candidate, Iterable)
            and not isinstance(candidate, Events)
            and len(candidate) == 2
            and isinstance(candidate[0], (Event, Events))
            and callable(candidate[1])
        )
        return v

    def _is_target(self, candidate):
        v = isinstance(candidate, (Event, Events)) or self._is_tuple_target(candidate)
        return v

    def add(self, *to_suppress):
        """
        Add one or more targets to be suppressed

        Valid targets are:
         - `Event`: The entire Event will be suppressed
         - `Events`: All events in the container will be suppressed
         - (Event, callback): The callback will be suppressed in Event
         - (Events, callback): The callback will be suppressed in each event
           in Events where it is connected.
         - Any iterable collection of the above target types
        """
        # Remove useless layers of iterables:
        while (
            isinstance(to_suppress, Iterable)
            and not isinstance(to_suppress, Events)
            and len(to_suppress) == 1
        ):
            to_suppress = to_suppress[0]
        # If single target passed, add directly:
        if self._is_target(to_suppress):
            self._add_single(to_suppress)
        elif isinstance(to_suppress, Iterable):
            if len(to_suppress) == 0:
                raise ValueError("No viable suppression targets added!")
            for t in to_suppress:
                if self._is_target(t):
                    self._add_single(t)
        else:
            raise ValueError("No viable suppression targets added!")

    @contextmanager
    def suppress(self):
        """
        Use this function with a 'with' statement to temporarily suppress
        all events added. When the 'with' lock completes, the old suppression
        values will be restored.

        See Also
        --------
        Events.suppress
        Event.suppress
        Event.suppress_callback
        """
        # We don't suppress any exceptions, so we can use simple CM management:
        cms = []
        try:
            for cm in self._cms:
                cm.__enter__()
                cms.append(cm)  # Only add entered CMs to list
            yield
        finally:
            # Completed succefully or exception occured, unwind all
            for cm in reversed(cms):
                # We don't use exception info, so simply pass blanks
                cm.__exit__(None, None, None)
