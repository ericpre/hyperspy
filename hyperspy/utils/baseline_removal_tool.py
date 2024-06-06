# -*- coding: utf-8 -*-
# Copyright 2007-2023 The HyperSpy developers
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

import itertools

import traits.api as t

import hyperspy
from hyperspy.ui_registry import add_gui_method

algorithms_mapping = {
    "Asymmetric Least Squares": "asls",
    "Improved Asymmetric Least Squares": "iasls",
    "Adaptive Iteratively Reweighted Penalized Least Squares": "airpls",
    "Asymmetrically Reweighted Penalized Least Squares": "arpls",
    "Doubly Reweighted Penalized Least Squares": "drpls",
    "Improved Asymmetrically Reweighted Penalized Least Squares": "iarpls",
    "Adaptive Smoothness Penalized Least Squares": "aspls",
    "Peaked Signal's Asymmetric Least Squares Algorithm": "psalsa",
}
algorithms_parameters = {
    "asls": ("lam", "p", "diff_order"),
    "iasls": ("lam", "lam_1", "p", "diff_order"),
    "airpls": ("lam", "diff_order"),
    "arpls": ("lam", "diff_order"),
    "drpls": ("lam", "eta", "diff_order"),
    "iarpls": ("lam", "diff_order"),
    "aspls": ("lam", "diff_order"),
    "psalsa": ("lam", "p", "diff_order"),
}
algorithms_mapping_inverse = {v: k for k, v in algorithms_mapping.items()}
parameters_algorithms = {}
for parameter in set(itertools.chain(*algorithms_parameters.values())):
    algorithm_list = [
        algorithms_mapping_inverse[algorithm]
        for algorithm, parameters in algorithms_parameters.items()
        if parameter in parameters
    ]
    parameters_algorithms[parameter] = algorithm_list


def _baseline_fitting(data, baseline_fitter, **kwargs):
    return data - baseline_fitter(data, **kwargs)[0]


@add_gui_method(toolkey="hyperspy.Signal1D.remove_baseline")
class BaselineRemoval(t.HasTraits):
    algorithm = t.Enum(
        *algorithms_mapping.keys(),
        default="Improved Asymmetric Least Squares",
    )
    lam = t.Range(1.0, 1e15, value=1e6)
    lam_1 = t.Range(1e-10, 1.0, value=1e-4)
    p = t.Range(0.0, 1.0, value=0.5, exclude_low=True, exclude_high=True)
    eta = t.Range(0.0, 1.0, value=0.5)
    diff_order = t.Range(1, 3, value=2)
    poly_order = t.Range(1, 10)
    half_window = t.Range(1, 200)
    # use to know if p needs to be enable or not
    # workaround for traitsui which doesn't support evaluation of more than
    # 2 conditions...
    _enable_p = t.Bool()

    def __init__(self, signal, algorithm="Asymmetric Least Squares"):
        super().__init__()
        self.signal = signal
        self.signal.plot()
        self.bl_line = None  # The baseline line
        self.estimator = None
        self.estimator_line = None
        self.set_estimator()

    def set_estimator(self):
        from pybaselines import Baseline

        self.estimator = getattr(
            Baseline(
                self.signal.axes_manager[-1].axis,
                check_finite=False,
            ),
            algorithms_mapping[self.algorithm],
        )
        self._enable_p = self.algorithm in parameters_algorithms["p"]
        self._update_lines()

    def _algorithm_changed(self, old, new):
        self.set_estimator()
        self._update_lines()

    def _get_kwargs(self):
        kwargs = {
            key: getattr(self, key)
            for key in algorithms_parameters[algorithms_mapping[self.algorithm]]
        }
        return kwargs

    def _baseline_to_plot(self, *args, **kwargs):
        return self.estimator(self.signal._get_current_data(), **self._get_kwargs())[0]

    def _create_lines(self):
        self.estimator_line = hyperspy.drawing.signal1d.Signal1DLine()
        self.estimator_line.data_function = self._baseline_to_plot
        self.estimator_line.set_line_properties(color="blue", type="line", scaley=False)
        self.signal._plot.signal_plot.add_line(self.estimator_line)
        self.estimator_line.autoscale = ""
        self.estimator_line.plot()

    @t.observe(
        ["lam", "lam_1", "p", "eta", "diff_order", "poly_order", "half_window"],
        post_init=True,
    )
    def lam_change(self, event):
        self._update_lines()

    def _update_lines(self):
        if self.estimator_line is None:
            self._create_lines()
        self.estimator_line.update(render_figure=True, update_ylimits=True)

    def apply(self):
        self.signal.remove_baseline(
            interactive=False,
            algorithm=algorithms_mapping[self.algorithm],
            inplace=True,
            **self._get_kwargs(),
        )
        self.estimator_line.close()
