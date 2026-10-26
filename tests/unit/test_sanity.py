"""Toolchain sanity check: proves tests run inside the tools container."""


def test_package_is_importable():
    import penpot_selfhost

    assert penpot_selfhost.__name__ == "penpot_selfhost"
