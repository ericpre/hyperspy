# -*- coding: utf-8 -*-
# Copyright 2007-2016 The HyperSpy developers
#
# This file is part of  HyperSpy.
#
#  HyperSpy is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
#  HyperSpy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with  HyperSpy.  If not, see <http://www.gnu.org/licenses/>.

from hyperspy.drawing.marker import MarkerBase


class VerticalRange(MarkerBase):

    """Vertical range marker that can be added to the signal figure

    Parameters
    ----------
    x1 : array or float
        The position of the line. If float, the marker is fixed.
        If array, the marker will be updated when navigating. The array should
        have the same dimensions in the navigation axes.
    x2 : array or float
        The position of the down right corner of the rectangle in x.
        see x1 arguments
    kwargs :
        Keywords argument of axvline valid properties (i.e. recognized by
        mpl.plot).

    Example
    -------
    >>> s = hs.signals.Signal1D(np.random.random([10, 100]))
    >>> m = hs.plot.markers.VerticalRange(x1=150, x2=200, color='green')
    >>> s.add_marker(m)

    Adding a marker permanently to a signal
    >>> s = hs.signals.Signal1D(np.random.random((100, 100)))
    >>> m = hs.plot.markers.VerticalRange(x1=30, x2=50)
    >>> s.add_marker(m, permanent=True)
    """

    def __init__(self, x1, x2, **kwargs):
        MarkerBase.__init__(self)
        lp = {'color': 'red', 'alpha': 0.5}
        self.marker_properties = lp
        self.set_data(x1=x1, x2=x2)
        self.set_marker_properties(**kwargs)
        self.name = 'vertical_range'

    def __repr__(self):
        string = "<marker.{}, {} (x1={},x2={},color={})>".format(
            self.__class__.__name__,
            self.name,
            self.get_data_position('x1'),
            self.get_data_position('x2'),
            self.marker_properties['color'],
        )
        return(string)

    def update(self):
        if self.auto_update is False:
            return
        width = abs(self.get_data_position('x2') -
                    self.get_data_position('x1'))
        self.marker.set_xdata(self.get_data_position('x1'))
        self.marker.set_width(width)

    def _plot_marker(self):
        self.marker = self.ax.axvspan(self.get_data_position('x1'),
                                      self.get_data_position('x2'),
                                      **self.marker_properties)
