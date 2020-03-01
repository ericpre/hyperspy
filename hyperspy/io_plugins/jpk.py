import os
import logging
import numpy as np
import pint
import traits.api as t
import afmformats


_logger = logging.getLogger(__name__)
_ureg = pint.UnitRegistry()


# Plugin characteristics
# ----------------------
format_name = 'jpk'
description = ''
full_support = False
# Recognised file extension
file_extensions = ['jpk', 'JPK', 'jpk-force', 'JPK-FORCE',
                   'jpk-force-map', 'jpk-qi-data']
default_extension = 0

# Writing capabilities:
writes = False

mapping = {'date': ('General.date', None),
           'time': ('General.time', None)}


class JPKReader:

    def __init__(self, filename, load_segment=None,
                 abscisse='height (measured)', conversion=True):
        self.afm_data = afmformats.load_data(filename,
                                             load_segment=load_segment,
                                             conversion=conversion)
        self.abscisse = abscisse

    def read_single_pixel(self, segment=None, columns=None):

        afm_data = self.afm_data[0]
        dictionaries = []

        om = afm_data.metadata

        if columns is None:
            # Read what are the columns
            columns = afm_data.columns

        if segment is None:
            segment = ['approach', 'retract']
        elif not isinstance(segment, list):
            segment = [segment]

        for seg in segment:
            for col in columns:
                dictionaries.append(self._read_segment(afm_data, seg, col, om))

        return dictionaries

    def _read_segment(self, afm_data, segment, column, om):
        if segment == 'approach':
            seg = afm_data.appr
        elif segment == 'retract':
            seg = afm_data.retr
        else:
            raise ValueError("'segment' must be 'approach' or 'retract'.")
        data = seg[column]

        height = seg[self.abscisse]
        size = len(height)
        scale = (height[1:] - height[:1]).mean()
        units = 'm'

        if segment == 'approach':
            offset = height[-1]
            scale = -scale
            data = data[::-1]
        else:
            offset = height[0]

        axes = [{'size': size,
                 'name': self.abscisse,
                 'offset': offset,
                 'scale': scale,
                 'units': units}]

        meta_gen = {}
        meta_gen['original_filename'] = os.path.split(om['path'])[1]
        meta_gen['title'] = f"{segment}, {column}"
        meta_gen['date'] = om['date']
        meta_gen['time'] = om['time']

        meta_sig = {'signal_type': ''}

        return {'data': data,
                'axes': axes,
                'metadata': {'General': meta_gen, 'Signal': meta_sig},
                'original_metadata': om,
                'mapping': mapping
                }

    def read_map(self, segment=None, columns=None):
        # Get grid shape and calibration
        afm_data0 = self.afm_data[0]

        if columns is None:
            # Read what are the columns
            columns = afm_data0.columns
        print("columns", columns)

        x_size = afm_data0.metadata['grid shape x']
        y_size = afm_data0.metadata['grid shape y']
        x_scale = afm_data0.metadata['grid size x'] / x_size
        y_scale = afm_data0.metadata['grid size y'] / y_size
        sig_size = len(afm_data0.retr[columns[0]])
        units = 'm'

        axes_list = [{'index_in_array': 0,
                      'size': y_size,
                      'name': 'y',
                      'offset': 0,
                      'scale': y_scale,
                      'units': units,
                      'navigate': True},
                     {'index_in_array': 1,
                      'size': x_size,
                      'name': 'x',
                      'offset': 0,
                      'scale': x_scale,
                      'units': units,
                      'navigate': True}
                     ]
        dictionaries = []

        om = afm_data0.metadata

        if segment is None:
            segment = ['approach', 'retract']
        elif not isinstance(segment, list):
            segment = [segment]

        for col in columns:
            for seg in segment:
                if seg == 'approach':
                    _seg = 'appr'
                if seg == 'retract':
                    _seg = 'retr'
                arr = np.stack([getattr(afm_datum, _seg)[col]
                                for afm_datum in self.afm_data])
                axes_dict, md = self._read_segment_metdata_axis(
                    afm_data0, seg, col, om)
                axes = axes_list.copy()
                axes.extend(axes_dict)
                dictionaries.append(
                    {'data': arr.reshape((x_size, y_size, sig_size)),
                     'axes': axes,
                     'metadata': md,
                     'original_metadata': om,
                     'mapping': mapping
                     }
                )

        return dictionaries

    def _read_segment_metdata_axis(self, afm_data, segment, column, om):
        if segment == 'approach':
            seg = afm_data.appr
        elif segment == 'retract':
            seg = afm_data.retr
        else:
            raise ValueError("'segment' must be 'approach' or 'retract'.")
        data = seg[column]

        height = seg[self.abscisse]
        size = len(height)
        scale = (height[1:] - height[:1]).mean()
        units = 'm'

        if segment == 'approach':
            offset = height[-1]
            scale = -scale
            data = data[::-1]
        else:
            offset = height[0]

        axes = [{'index_in_array': -1,
                 'size': size,
                 'name': self.abscisse,
                 'offset': offset,
                 'scale': scale,
                 'units': units,
                 'navigate': False}]

        meta_gen = {}
        meta_gen['original_filename'] = os.path.split(om['path'])[1]
        meta_gen['title'] = f"{segment}, {column}"

        meta_sig = {'signal_type': '', 'quantity': ''}

        return axes, {'General': meta_gen, 'Signal': meta_sig}


def file_reader(filename, lazy=False, segment=None, columns=None,
                abscisse='height (measured)', conversion=True):

    load_segment = None
    if columns is not None and not isinstance(columns, list):
        columns = [columns]
        load_segment = columns.copy()

    if load_segment is not None and abscisse not in load_segment:
        load_segment.append(abscisse)

    jpk_loader = JPKReader(filename, load_segment=load_segment,
                           abscisse=abscisse, conversion=conversion)

    if len(jpk_loader.afm_data) == 1:
        return jpk_loader.read_single_pixel(segment, columns)
    else:
        return jpk_loader.read_map(segment, columns)
