def test_package_imports():
    import nesting
    assert nesting is not None


def test_dependencies_available():
    import numpy
    import scipy.signal
    import shapely.geometry
    import ezdxf
    import PIL.ImageDraw
    import yaml

    assert numpy.__version__
    assert scipy.signal.fftconvolve is not None
    assert shapely.geometry.Polygon is not None
    assert ezdxf.new is not None
    assert PIL.ImageDraw.Draw is not None
    assert yaml.safe_load("a: 1") == {"a": 1}
