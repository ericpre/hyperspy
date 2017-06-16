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

import numpy as np
import matplotlib.pyplot as plt
import matplotlib as mpl
from mpl_toolkits.axes_grid1 import make_axes_locatable

import hyperspy
from hyperspy.drawing.figure import BlittedFigure
from hyperspy.drawing import utils
from hyperspy.drawing.widgets import RangeWidget
from hyperspy.events import Event, Events


class RangeWidgetsContainer(object):
    """ Container to add and remove widgets to a figure. When the figure is
        closed, the widgets are saved as marker in the metadata.

    Attributes
    ----------
    widgets : list
        List of widgets

    Methods
    -------
    add_widgets: add widget by using a list of object or a single object. The
        object can be a 2-tuple corresponding to the start and end position, a 
        range widget or a marker having a 'x1' and 'x2' data.

    remove_widget: remove a widget from the plot and from the widget_list.

    add_widgets_to_metadata: Add widgets (as markers) to the given node name
        of the given metadata.

    create_widgets_from_metadata: add widgets to the figure from the given node
        name of the given metadata.

    add_widgets_interactively: add widget interactively: use the control `key` 
        to widget and the `delete` key to remove widget.
    """

    def __init__(self, SpanSelector_kwargs={}):
        super().__init__()
        self.signal = None
        self._SpanSelector_kwargs = SpanSelector_kwargs
        self.widget_list = []
        self._add_new_widget = False
        self._is_add_widget_interactive = False
        # Default name of the metadata node to store widget as marker
        self.metadata_node_name = 'Widgets'
        # TODO: fix issue with overlaying span

    def add_widgets(self, obj):
        """
        Add one or several widgets.

        Parameters
        ----------
        obj : add widget by using a list of object or a single object. The
            object can be a 2-tuple corresponding to the start and end 
            position, a range widget or a marker having a 'x1' and 'x2' data.
        """
        if type(obj) is list:
            for ob in obj:
                self._add_widget(ob)
        else:
            self._add_widget(obj)

    def _add_widget(self, obj=None):
        if isinstance(obj, RangeWidget):
            self.widget_list.append(obj)
        else:
            widget = self._create_widget()
            marker_class = hyperspy.utils.markers.__dict__[widget._marker_type]
            if isinstance(obj, marker_class):
                position = (obj.get_data_position('x1'),
                            obj.get_data_position('x2'))
                # update matplotlib artists of the widget
                plt.setp(widget.span.rect, **obj.marker_properties)
            else:
                # in case of a tuple
                position = obj
            if position is not None:
                widget.span.set_initial(position)
                # manual first sync of spin with widget
                widget._span_changed(widget.span)
                self._add_new_widget = False
            self.widget_list.append(widget)

    def remove_widget(self, obj):
        """Remove a widget. The widget can be selected either by providing
        itself or its index in the widget_list.
        """
        if type(obj) is int:
            obj = self.widget_list[obj]
        elif not isinstance(obj, RangeWidget):
            return
        obj.disconnect()
        self.widget_list.remove(obj)

    def _create_widget(self):
        return RangeWidget(self.axes_manager, ax=self.ax, signal=self.signal,
                           **self._SpanSelector_kwargs)

    def _is_navigation_plot(self):
        """ Return if this is a navigation or signal figure"""
        # If it has a pointer, it is a navigation plot
        return hasattr(self, 'pointer')

    def add_widgets_to_metadata(self, metadata, node_name=None,
                                remove_widgets=False):
        """ Add all widgets to metadata as marker. """
        if node_name is None:
            node_name = self.metadata_node_name
        for i, widget in enumerate(self.widget_list):
            marker = widget.to_marker()
            marker._plot_on_signal = not self._is_navigation_plot()
            metadata.set_item("{}.range{}".format(node_name, i),
                              marker)
        if remove_widgets:
            self.widget_list = []

    def create_widgets_from_metadata(self, metadata, node_name=None):
        """ Create widgets from the markers saved in metadata. Use the 
            node_name to specify the location of the markers."""
        if node_name is None:
            node_name = self.metadata_node_name
        if not metadata.has_item(node_name):
            return
        marker_node = metadata.get_item(node_name)
        for key in marker_node.keys():
            self._add_widget(marker_node[key])

    def add_widgets_interactively(self, is_interactive=True):
        self._add_widget_toggled(is_interactive)
        if self._is_add_widget_interactive:
            self.keyPress = self.figure.canvas.mpl_connect('key_press_event',
                                                           self._onKeyPress)
            self.buttonRelease = self.figure.canvas.mpl_connect('button_release_event',
                                                                self._onRelease)
        else:
            self.figure.canvas.mpl_disconnect(self.keyPress)
            self.figure.canvas.mpl_disconnect(self.buttonPress)

    def _onKeyPress(self, event):
        """ Add widget by pressing on 'control' key, delete span by pressing 
        'delete' key.
        """
        if not self._is_add_widget_interactive:
            return
        on_widget, widget = self._mouse_on_widget(event)
        if event.key == 'control' and not self._add_new_widget:
            # if the mouse is on a widget, deactivate it 
            if on_widget:
                widget.active = False
            self._add_widget()
            self._add_new_widget = True
            # reactivate the widget that have just been deactivated
            if on_widget:
                widget.active = False
        elif event.key == 'delete':
            if on_widget:
                self.remove_widget(widget)

    def _onRelease(self, event):
        self._add_new_widget = False

    def _mouse_on_widget(self, event):
        """ Return a (True, widget) if the mouse on a widget 
        else (False, None)"""
        for widget in self.widget_list:
            if widget.mouse_on_widget(event):
                return True, widget
        return False, None

    def _add_widget_toggled(self, is_interactive):
        self._is_add_widget_interactive = is_interactive
        # switch off matplotlib navigate mode when necessary
        if self._is_add_widget_interactive:
            toolbar = self.figure.canvas.toolbar
            if toolbar._active == "PAN":
                toolbar.pan()
            elif toolbar._active == "ZOOM":
                toolbar.zoom()
            toolbar.set_message('Add widget')


class Signal1DFigure(BlittedFigure, RangeWidgetsContainer):

    """
    """

    def __init__(self, title=""):
        super().__init__()
        self.figure = None
        self.ax = None
        self.signal = None
        self.right_ax = None
        self.ax_lines = list()
        self.right_ax_lines = list()
        self.ax_markers = list()
        self.axes_manager = None
        self.right_axes_manager = None

        # Labels
        self.xlabel = ''
        self.ylabel = ''
        self.title = title
        self.create_figure()
        self.create_axis()

        # Color cycles
        self._color_cycles = {
            'line': utils.ColorCycle(),
            'step': utils.ColorCycle(),
            'scatter': utils.ColorCycle(), }

    def create_figure(self):
        self.figure = utils.create_figure(
            window_title="Figure " + self.title if self.title
            else None)
        utils.on_figure_window_close(self.figure, self._on_close)
        self.figure.canvas.mpl_connect('draw_event', self._on_draw)
        self.figure.canvas.mpl_connect('key_press_event', self._on_key)

    def create_axis(self):
        self.ax = self.figure.add_subplot(111)
        animated = self.figure.canvas.supports_blit
        self.ax.yaxis.set_animated(animated)
        self.ax.xaxis.set_animated(animated)
        self.ax.hspy_fig = self

    def create_right_axis(self):
        if self.ax is None:
            self.create_axis()
        if self.right_ax is None:
            self.right_ax = self.ax.twinx()
            self.right_ax.hspy_fig = self
            self.right_ax.yaxis.set_animated(
                self.figure.canvas.supports_blit)
        plt.tight_layout()

    def add_line(self, line, ax='left'):
        if ax == 'left':
            line.ax = self.ax
            if line.axes_manager is None:
                line.axes_manager = self.axes_manager
            self.ax_lines.append(line)
            line.sf_lines = self.ax_lines
        elif ax == 'right':
            line.ax = self.right_ax
            self.right_ax_lines.append(line)
            line.sf_lines = self.right_ax_lines
            if line.axes_manager is None:
                line.axes_manager = self.right_axes_manager
        line.axis = self.axis
        # Automatically asign the color if not defined
        if line.color is None:
            line.color = self._color_cycles[line.type]()
        # Or remove it from the color cycle if part of the cycle
        # in this round
        else:
            rgba_color = mpl.colors.colorConverter.to_rgba(line.color)
            if rgba_color in self._color_cycles[line.type].color_cycle:
                self._color_cycles[line.type].color_cycle.remove(
                    rgba_color)

    def plot(self):
        self.ax.set_xlabel(self.xlabel)
        self.ax.set_ylabel(self.ylabel)
        self.ax.set_title(self.title)
        x_axis_upper_lims = []
        x_axis_lower_lims = []
        self._set_background()
        for line in self.ax_lines:
            line.plot()
            x_axis_lower_lims.append(line.axis.axis[0])
            x_axis_upper_lims.append(line.axis.axis[-1])
        for marker in self.ax_markers:
            marker.plot()
        plt.xlim(np.min(x_axis_lower_lims), np.max(x_axis_upper_lims))
        # To be discussed
        self.axes_manager.events.indices_changed.connect(self.update, [])
        self.events.closed.connect(
            lambda: self.axes_manager.events.indices_changed.disconnect(
                self.update), [])
        if hasattr(self.figure, 'tight_layout'):
            try:
                self.figure.tight_layout()
            except:
                # tight_layout is a bit brittle, we do this just in case it
                # complains
                pass

    def _on_close(self):
        if self.figure is None:
            return  # Already closed
        for line in self.ax_lines + self.right_ax_lines:
            line.close()
        if len(self.widget_list) > 0:
            self.add_widgets_to_metadata(self.signal.metadata,
                                         remove_widgets=True)
        super(Signal1DFigure, self)._on_close()

    def update(self):
        for marker in self.ax_markers:
            marker.update()
        for line in self.ax_lines + \
                self.right_ax_lines:
            line.update()

    def _on_key(self, event):
        if event.key == 'i':
            self._is_add_widget_interactive = not self._is_add_widget_interactive
            self.add_widgets_interactively(self._is_add_widget_interactive)


class Signal1DLine(object):

    """Line that can be added to Signal1DFigure.

    Attributes
    ----------
    type : {'scatter', 'step', 'line'}
        Select the line drawing style.
    line_properties : dictionary
        Accepts a dictionary of valid (i.e. recognized by mpl.plot)
        containing valid line properties. In addition it understands
        the keyword `type` that can take the following values:
        {'scatter', 'step', 'line'}

    Methods
    -------
    set_line_properties
        Enables setting the line_properties attribute using keyword
        arguments.

    Raises
    ------
    ValueError
        If an invalid keyword value is passed to line_properties.

    """

    def __init__(self):
        self.events = Events()
        self.events.closed = Event("""
            Event that triggers when the line is closed.

            Arguments:
                obj:  Signal1DLine instance
                    The instance that triggered the event.
            """, arguments=["obj"])
        self.sf_lines = None
        self.ax = None
        # Data attributes
        self.data_function = None
        self.axis = None
        self.axes_manager = None
        self.auto_update = True
        self.get_complex = False

        # Properties
        self.line = None
        self.autoscale = False
        self.plot_indices = False
        self.text = None
        self.text_position = (-0.1, 1.05,)
        self._line_properties = {}
        self.type = "line"

    @property
    def line_properties(self):
        return self._line_properties

    @line_properties.setter
    def line_properties(self, kwargs):
        if 'type' in kwargs:
            self.type = kwargs['type']
            del kwargs['type']

        if 'color' in kwargs:
            color = kwargs['color']
            del kwargs['color']
            self.color = color

        for key, item in kwargs.items():
            if item is None and key in self._line_properties:
                del self._line_properties[key]
            else:
                self._line_properties[key] = item
        if self.line is not None:
            plt.setp(self.line, **self.line_properties)
            self.ax.figure.canvas.draw_idle()

    def set_line_properties(self, **kwargs):
        self.line_properties = kwargs

    @property
    def type(self):
        return self._type

    @type.setter
    def type(self, value):
        lp = {}
        if value == 'scatter':
            lp['marker'] = 'o'
            lp['linestyle'] = 'None'
            lp['markersize'] = 1

        elif value == 'line':
            lp['linestyle'] = '-'
            lp['marker'] = "None"
            lp['drawstyle'] = "default"
        elif value == 'step':
            lp['drawstyle'] = 'steps-mid'
            lp['marker'] = "None"
        else:
            raise ValueError(
                "`type` must be one of "
                "{\'scatter\', \'line\', \'step\'}"
                "but %s was given" % value)
        self._type = value
        self.line_properties = lp
        if self.color is not None:
            self.color = self.color

    @property
    def color(self):
        if 'color' in self.line_properties:
            return self.line_properties['color']
        elif 'markeredgecolor' in self.line_properties:
            return self.line_properties['markeredgecolor']
        else:
            return None

    @color.setter
    def color(self, color):
        if self._type == 'scatter':
            self.set_line_properties(markeredgecolor=color)
            if 'color' in self._line_properties:
                del self._line_properties['color']
        else:
            if color is None and 'color' in self._line_properties:
                del self._line_properties['color']
            else:
                self._line_properties['color'] = color
            self.set_line_properties(markeredgecolor=None)

        if self.line is not None:
            plt.setp(self.line, **self.line_properties)
            self.ax.figure.canvas.draw_idle()

    def plot(self, data=1):
        f = self.data_function
        if self.get_complex is False:
            data = f(axes_manager=self.axes_manager).real
        else:
            data = f(axes_manager=self.axes_manager).imag
        if self.line is not None:
            self.line.remove()
        self.line, = self.ax.plot(self.axis.axis, data,
                                  **self.line_properties)
        self.line.set_animated(self.ax.figure.canvas.supports_blit)
        self.axes_manager.events.indices_changed.connect(self.update, [])
        self.events.closed.connect(
            lambda: self.axes_manager.events.indices_changed.disconnect(
                self.update), [])
        if not self.axes_manager or self.axes_manager.navigation_size == 0:
            self.plot_indices = False
        if self.plot_indices is True:
            if self.text is not None:
                self.text.remove()
            self.text = self.ax.text(*self.text_position,
                                     s=str(self.axes_manager.indices),
                                     transform=self.ax.transAxes,
                                     fontsize=12,
                                     color=self.line.get_color(),
                                     animated=self.ax.figure.canvas.supports_blit)
        self.ax.figure.canvas.draw_idle()

    def update(self, force_replot=False):
        """Update the current spectrum figure"""
        if self.auto_update is False:
            return
        if force_replot is True:
            self.close()
            self.plot()
        if self.get_complex is False:
            ydata = self.data_function(axes_manager=self.axes_manager).real
        else:
            ydata = self.data_function(axes_manager=self.axes_manager).imag

        old_xaxis = self.line.get_xdata()
        if len(old_xaxis) != self.axis.size or \
                np.any(np.not_equal(old_xaxis, self.axis.axis)):
            self.ax.set_xlim(self.axis.axis[0], self.axis.axis[-1])
            self.line.set_data(self.axis.axis, ydata)
        else:
            self.line.set_ydata(ydata)

        if self.autoscale is True:
            self.ax.relim()
            y1, y2 = np.searchsorted(self.axis.axis,
                                     self.ax.get_xbound())
            y2 += 2
            y1, y2 = np.clip((y1, y2), 0, len(ydata - 1))
            clipped_ydata = ydata[y1:y2]
            y_max, y_min = (np.nanmax(clipped_ydata),
                            np.nanmin(clipped_ydata))
            if self.get_complex:
                yreal = self.data_function(axes_manager=self.axes_manager).real
                clipped_yreal = yreal[y1:y2]
                y_min = min(y_min, clipped_yreal.min())
                y_max = max(y_max, clipped_yreal.max())
            self.ax.set_ylim(y_min, y_max)
        if self.plot_indices is True:
            self.text.set_text(self.axes_manager.indices)
        if self.ax.figure.canvas.supports_blit:
            self.ax.hspy_fig._draw_animated()
        else:
            self.ax.figure.canvas.draw_idle()

    def close(self):
        if self.line in self.ax.lines:
            self.ax.lines.remove(self.line)
        if self.text and self.text in self.ax.texts:
            self.ax.texts.remove(self.text)
        if self.sf_lines and self in self.sf_lines:
            self.sf_lines.remove(self)
        self.events.closed.trigger(obj=self)
        for f in self.events.closed.connected:
            self.events.closed.disconnect(f)
        try:
            self.ax.figure.canvas.draw_idle()
        except:
            pass


def _plot_component(factors, idx, ax=None, cal_axis=None,
                    comp_label='PC'):
    if ax is None:
        ax = plt.gca()
    if cal_axis is not None:
        x = cal_axis.axis
        plt.xlabel(cal_axis.units)
    else:
        x = np.arange(factors.shape[0])
        plt.xlabel('Channel index')
    ax.plot(x, factors[:, idx], label='%s %i' % (comp_label, idx))
    return ax


def _plot_loading(loadings, idx, axes_manager, ax=None,
                  comp_label='PC', no_nans=True, calibrate=True,
                  cmap=plt.cm.gray):
    if ax is None:
        ax = plt.gca()
    if no_nans:
        loadings = np.nan_to_num(loadings)
    if axes_manager.navigation_dimension == 2:
        extent = None
        # get calibration from a passed axes_manager
        shape = axes_manager._navigation_shape_in_array
        if calibrate:
            extent = (axes_manager._axes[0].low_value,
                      axes_manager._axes[0].high_value,
                      axes_manager._axes[1].high_value,
                      axes_manager._axes[1].low_value)
        im = ax.imshow(loadings[idx].reshape(shape), cmap=cmap, extent=extent,
                       interpolation='nearest')
        div = make_axes_locatable(ax)
        cax = div.append_axes("right", size="5%", pad=0.05)
        plt.colorbar(im, cax=cax)
    elif axes_manager.navigation_dimension == 1:
        if calibrate:
            x = axes_manager._axes[0].axis
        else:
            x = np.arange(axes_manager._axes[0].size)
        ax.step(x, loadings[idx])
    else:
        raise ValueError('View not supported')
