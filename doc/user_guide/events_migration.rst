.. _events_migration:

Events system migration guide
=============================

HyperSpy 3.0 introduces a new events system based on `psygnal <https://github.com/pyapp-kit/psygnal>`_.
This replaces the legacy internal events system with a more robust, type-annotated, and performant implementation.

What changes in 3.0
-------------------

The core classes and methods have been renamed or replaced to align with the psygnal API:

*   ``Event``, ``Events``, and ``EventSuppressor`` are replaced by psygnal's ``Signal`` and ``SignalGroup``.
*   ``trigger()`` is replaced by ``emit()``.
*   ``suppress()`` is replaced by ``blocked()``.
*   The ``connect()`` method no longer supports the ``kwargs`` parameter. Explicit wrappers (like ``lambda``) should be used instead.
*   Signal arguments are now explicitly defined via type annotations in the Signal definition.
*   The ``weakref`` parameter is removed; psygnal uses weak references by default for instance methods.
*   The internal ``_trigger_maker`` has been removed.

Migration guide
---------------

Common patterns from HyperSpy 2.x and their 3.0 equivalents are shown below.

Triggering events
^^^^^^^^^^^^^^^^^

.. code-block:: python

    # 2.5 (old)
    obj.events.data_changed.trigger(obj=self)

    # 3.0 (new)
    obj.data_changed.emit(self)

Connecting to events
^^^^^^^^^^^^^^^^^^^^

In 3.0, if you need to map signal arguments to specific function arguments, use a ``lambda`` or a wrapper function.

.. code-block:: python

    # 2.5 (old)
    obj.events.data_changed.connect(f, kwargs=["obj"])

    # 3.0 (new)
    obj.data_changed.connect(lambda obj: f(obj=obj))

Blocking events
^^^^^^^^^^^^^^^

The context manager for temporarily disabling events has changed from ``suppress()`` to ``blocked()``.

.. code-block:: python

    # 2.5 (old)
    with obj.events.suppress():
        # do something without triggering events
        ...

    # 3.0 (new)
    with obj.data_changed.blocked():
        # do something without triggering events
        ...

Suppressing specific callbacks (guard-flag pattern)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``suppress_callback()`` is removed in 3.0. The replacement is a **guard-flag**
pattern: a simple boolean flag that callbacks check before executing.

**Old (2.5):**

.. code-block:: python

    with obj.events.data_changed.suppress_callback(my_callback):
        # my_callback is temporarily disabled
        obj.data += 1

**New (3.0):**

.. code-block:: python

    from contextlib import contextmanager

    _suppress_flag = False

    @contextmanager
    def suppress_my_callback():
        global _suppress_flag
        _suppress_flag = True
        try:
            yield
        finally:
            _suppress_flag = False

    def my_callback(*args):
        if _suppress_flag:
            return
        # normal callback logic...

    with suppress_my_callback():
        obj.data += 1

This pattern is more explicit and does not require the event system to track
which callbacks should be suppressed.

New 3.0 features
----------------

The migration to psygnal brings several new capabilities to the HyperSpy ecosystem:

*   **EventedObjectProxy**: A proxy wrapper that can detect mutations in underlying objects, such as numpy arrays, and emit signals automatically.
*   **EventedModel**: Integration with Pydantic v2 for creating data models that automatically emit signals when fields change.
*   **Async dispatch**: Support for asynchronous signal emission, useful for live processing and non-blocking UI updates.
*   **Type-annotated signals**: Signals now carry type information, providing better IDE support, autocompletion, and static type checking.

Timeline
--------

*   **HyperSpy 2.5**: Introduced a psygnal-backed adapter. The legacy API remains functional but issues deprecation warnings.
*   **HyperSpy 3.0**: The legacy events system is removed. All code must use the new psygnal-based API.
