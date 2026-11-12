"""Drop-in addition for lerobot/sensors/__init__.py.

After the existing imports, add:

    from .configs import PaxiniSensorConfig
    from .paxini import PaxiniSensor

and extend __all__:

    "PaxiniSensor",
    "PaxiniSensorConfig",
"""
