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

import traits.api as t

algorithms_mapping = {
    "Asymmetric Least Squares": "asls ",
    "Improved Asymmetric Least Squares": "iasls",
    "Adaptive Iteratively Reweighted Penalized Least Squares": "airpls",
    "Asymmetrically Reweighted Penalized Least Squares": "arpls",
    "Doubly Reweighted Penalized Least Squares": "drpls",
    "Improved Asymmetrically Reweighted Penalized Least Squares": "iarpls",
    "Adaptive Smoothness Penalized Least Squares": "aspls",
    "Peaked Signal's Asymmetric Least Squares Algorithm": "psalsa ",
}


class BaselineRemoval:
    background_type = t.Enum(
        *algorithms_mapping.keys(),
        default="Asymmetric Least Squares",
    )
    lam = t.Range(1, 10)
    p = t.Range(1, 10)
    diff_order = t.Range(1, 10)
