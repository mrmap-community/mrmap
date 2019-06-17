"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 07.06.19


This file contains app specific configurations like constants and so on.
"""
from MapSkinner.settings import BASE_DIR

ALLOWED_SRS = [
    4326,
    4258,
    31466,
    31467,
    31468,
    25832,
    3857,
]

ALLOWED_SRS_EXTENTS = {

    4326: {
        "minx": -180,
        "miny": -90,
        "maxx": 180,
        "maxy": 90,
        },
    4258: {
        "minx": -10.6700,
        "miny": 34.5000,
        "maxx": 31.5500,
        "maxy": 71.0500,
        },
    31466: {
        "minx": 5.1855468,
        "miny": 46.8457031,
        "maxx": 15.46875,
        "maxy": 55.634765,
        },
    31467: {
        "minx": 5.1855468,
        "miny": 46.8457031,
        "maxx": 15.46875,
        "maxy": 55.634765,
        },
    31468: {
        "minx": 5.1855468,
        "miny": 46.8457031,
        "maxx": 15.46875,
        "maxy": 55.634765,
        },
    25832: {
        "minx": 5.1855468,
        "miny": 46.8457031,
        "maxx": 15.46875,
        "maxy": 55.634765,
        },
    3857: {
        "minx": -180,
        "miny": -90,
        "maxx": 180,
        "maxy": 90,
        },
}

INSPIRE_LEGISLATION_FILE = BASE_DIR + "/inspire_legislation.json"