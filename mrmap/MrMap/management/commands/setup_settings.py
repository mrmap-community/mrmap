"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.07.20

"""
from registry.enums.metadata import CategoryOriginEnum

CATEGORIES = {
    CategoryOriginEnum.INSPIRE.value: "https://www.eionet.europa.eu/gemet/getTopmostConcepts?thesaurus_uri=http://inspire.ec.europa.eu/theme/&language={}",
    CategoryOriginEnum.ISO.value: "http://inspire.ec.europa.eu/metadata-codelist/TopicCategory/TopicCategory.{}.json",
}

CATEGORIES_LANG = {
    "locale_1": "de",
    "locale_2": "fr",
}

LICENCES = [
    {
        "name": "Creative Commons 3.0",
        "identifier": "cc-by-nc-nd-3.0",
        "symbol_url": "http://i.creativecommons.org/l/by-nc-nd/3.0/de/88x31.png",
        "description": "Creative Commons: Namensnennung - Keine kommerzielle Nutzung - Keine Bearbeitungen 3.0 Deutschland",
        "description_url": "http://creativecommons.org/licenses/by-nc-nd/3.0/de/",
        "is_open_data": False,
    },
    {
        "name": "Creative Commons 3.0",
        "identifier": "cc-nc-3.0",
        "symbol_url": "http://i.creativecommons.org/l/by-nc/3.0/de/88x31.png",
        "description": "Creative Commons: Namensnennung - Keine kommerzielle Nutzung 3.0 Deutschland",
        "description_url": "http://creativecommons.org/licenses/by-nc/3.0/de/",
        "is_open_data": False,
    },
    {
        "name": "Creative Commons 3.0",
        "identifier": "cc-by-3.0",
        "symbol_url": "http://i.creativecommons.org/l/by/3.0/de/88x31.png",
        "description": "Creative Commons: Namensnennung 3.0 Deutschland",
        "description_url": "http://creativecommons.org/licenses/by/3.0/de/",
        "is_open_data": True,
    },
    {
        "name": "Datenlizenz Deutschland 1.0",
        "identifier": "dl-de-by-nc-1.0",
        "symbol_url": None,
        "description": "Datenlizenz Deutschland – Namensnennung – nicht-kommerziell – Version 1.0",
        "description_url": "https://www.govdata.de/dl-de/by-nc-1-0",
        "is_open_data": False,
    },
    {
        "name": "Datenlizenz Deutschland 1.0",
        "identifier": "dl-de-by-1.0",
        "symbol_url": None,
        "description": "Datenlizenz Deutschland – Namensnennung – Version 1.0",
        "description_url": "https://www.govdata.de/dl-de/by-1-0",
        "is_open_data": True,
    },
    {
        "name": "Datenlizenz Deutschland 2.0",
        "identifier": "dl-de-zero-2.0",
        "symbol_url": None,
        "description": "Datenlizenz Deutschland – Zero – Version 2.0",
        "description_url": "https://www.govdata.de/dl-de/zero-2-0",
        "is_open_data": True,
    },
    {
        "name": "Datenlizenz Deutschland 2.0",
        "identifier": "dl-de-by-2.0",
        "symbol_url": None,
        "description": "Datenlizenz Deutschland Namensnennung 2.0",
        "description_url": "https://www.govdata.de/dl-de/by-2-0",
        "is_open_data": True,
    },
    {
        "name": "Open Data Commons Open Database License",
        "identifier": "odc-odbl-1.0",
        "symbol_url": None,
        "description": "Open Data Commons Open Database License (ODbL)",
        "description_url": "http://opendatacommons.org/licenses/odbl/1.0/",
        "is_open_data": True,
    },
]
