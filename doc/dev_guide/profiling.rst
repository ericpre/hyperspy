.. _profiling_code:

Profiling code
==============
Profiling is a way to measure the performance of your code, helping you
identify bottlenecks and optimize performance.

Using cProfile
--------------

You can use the built-in ``cProfile`` module to profile your code and use
`tuna <https://github.com/nschloe/tuna>`_ to visualise the
results. Here's how to do it:

1. Generate the profiling data by running your code with `cProfile`:

   .. code-block:: python

      import cProfile
      import pstats
      import numpy as np
      import hyperspy.api as hs

      with cProfile.Profile() as pr:
         # Replace this with the code you want to profile
         # For example, creating a Signal1D object with some data
         data = np.arange(10*10*100).reshape(10, 10, 100)
         s = hs.signals.Signal1D(data)

      stats = pstats.Stats(pr)
      stats.dump_stats(filename='profiling_code.prof')

2. Run `tuna` to visualize the profiling data:

   .. code-block:: bash

      tuna profiling_code.prof

   This will open a web browser with an interactive visualization of the profiling data.


Profiling import
----------------

You can also profile the import time of your code to identify which modules take the
longest to load. This can be useful for identify a function or module, that may need
to be imported lazily or its import to be defer where it is actually needed.

1. Generate the import profiling data by running your code with the `-X importtime` option:

   .. code-block:: bash

      python -X importtime 'import hyperspy.api as hs' 2> hyperspy.log

2. Run `tuna` to visualize the import profiling data:

   .. code-block:: bash

      tuna hyperspy.log
