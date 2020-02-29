import os
import numpy as np

import hyperspy.api as hs


FILE_PATH = os.path.join(os.path.dirname(__file__), 'jpk_files')


def test_single_jpk_force():
    FNAME = os.path.join(FILE_PATH, 'single_pixel.jpk-force')
    s = hs.load(FNAME)
    len(s) == 12
    s = hs.load(FNAME, columns='force')
    len(s) == 2
    s = hs.load(FNAME, segment='approach')
    len(s) == 6
    am = s[0].axes_manager
    np.testing.assert_allclose(am[0].size, 1024)
    np.testing.assert_allclose(am[0].scale, 3.579151e-07)
    np.testing.assert_allclose(am[0].offset, 5.524879e-06)
    assert am[0].units == 'm'


def test_map_jpk_forge():
    FNAME = os.path.join(FILE_PATH, 'map.jpk-force-map')
    s = hs.load(FNAME, segment='retract')
    len(s) == 6
    s = hs.load(FNAME, segment='retract', columns='force')
    len(s) == 1
    am = s.axes_manager
    np.testing.assert_allclose(am[0].size, 8)
    np.testing.assert_allclose(am[0].scale, 6.310397e-07)
    np.testing.assert_allclose(am[0].offset, 0.)
    np.testing.assert_allclose(am[1].size, 8)
    np.testing.assert_allclose(am[1].scale, 6.310397e-07)
    np.testing.assert_allclose(am[1].offset, 0.)  
    np.testing.assert_allclose(am[2].size, 1024)
    np.testing.assert_allclose(am[2].scale, 3.580294e-07)
    np.testing.assert_allclose(am[2].offset, 5.499739e-06)    

import afmformats

FNAME = os.path.join(FILE_PATH, 'map.jpk-force-map')
afm_data = afmformats.load_data(FNAME) 
