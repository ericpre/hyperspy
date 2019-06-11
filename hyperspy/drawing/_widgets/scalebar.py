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

import traits.api as t
from matplotlib_scalebar.scalebar import ScaleBar as _ScaleBar

from hyperspy.drawing.widgets import Widget2DBase


class ScaleBar(Widget2DBase):

    def __init__(self, axes_manager, units, pixel_size=None, color='black', 
                 frameon=True, alpha=0.75, location=3, length_fraction=None, 
                 label_loc='top', animated=False):
        """Add a scale bar to an image.

        Parameteres
        -----------
        axes_manager
            The axes manager of the signal.
        units : string
            The units of the pixel.
        pixel_size : float
            The size of the pixel.
        color : a valid matplotlib color.

        """
        super().__init__(axes_manager, color=color)

        self.axes_manager = axes_manager
        self.units = units
        self.pixel_size = pixel_size
        self.frameon = frameon
        self.alpha = alpha
        self.location = location
        self.length_fraction = length_fraction
        self.label_loc = label_loc
        self.animated = animated

        # TODO: improve this adding support for more units in matplotlib-scalebar 
        self.dimension = 'si-length'
        if self.units == t.Undefined:
            self.units = "px"
            self.dimension = "pixel-length"

    def _add_patch_to(self, ax):
        """Create and add the matplotlib patches to 'ax'
        """
        self.patch = [_ScaleBar(
                dx=self.pixel_size,
                units=self.units,
                dimension=self.dimension,
                length_fraction=self.length_fraction,
                location= self.location,
                frameon=self.frameon,
                color=self.color,
                box_alpha=self.alpha,
                label_loc=self.label_loc,
                use_blit=self.animated)]
        ax.add_artist(self.patch[0])
