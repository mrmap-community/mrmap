from django.db.models.enums import TextChoices
from django.utils.translation import gettext_lazy as _
from extras.enums import SmartIntegerChoices


# TODO: use IntegerChoices instead
class CategoryOriginEnum(TextChoices):
    """ Defines sources for categories
    """
    ISO = "iso"
    INSPIRE = "inspire"

    @classmethod
    def all_values_as_list(cls):
        return [enum.value for enum in cls]

    @classmethod
    def all_names_as_list(cls):
        return [enum.name for enum in cls]


class MetadataOriginEnum(SmartIntegerChoices):
    """ Defines origins from where a resource could be coming from

    """
    CAPABILITIES = 1, _("Capabilities")
    UPLOAD = 2, _("Upload")
    FILE_SYSTEM_IMPORT = 3, _("File System Import")
    EDITOR = 4, _("Editor")
    CATALOGUE = 5, _("Catalogue")


class DatasetFormatEnum(SmartIntegerChoices):
    DATABASE = 1, _("Database")
    ESRI_SHAPE = 2, _("Esri shape")
    CSV = 3, _("CSV")
    GML = 4, _("GML")
    GEOTIFF = 5, _("GeoTIFF")


class LanguageChoices(SmartIntegerChoices):
    ger = 1, _("ger")
    en = 2, _("en")


class MetadataCharsetChoices(SmartIntegerChoices):
    """Represents all valueable choices for MD_CharacterSetCode<<CodeList>> ISO19139"""
    # 16-bit fixed size Universal Character Set, based on ISO/IEC 10646
    UCS2 = 2, _("ucs2")
    # 32-bit fixed size Universal Character Set, based on ISO/IEC 10646
    UCS4 = 3, _("ucs4")
    # 7-bit variable size UCS Transfer Format, based on ISO/IEC 10646
    utf7 = 4, _("utf7")
    # 8-bit variable size UCS Transfer Format, based on ISO/IEC 10646
    UTF8 = 5, _("utf8")
    # 16-bit variable size UCS Transfer Format, based on ISO/IEC 10646
    utf16 = 6, _("utf16")
    # ISO/IEC 8859-1, Information technology - 8-bit single-byte coded graphic character sets - Part 1: Latin alphabet No. 1
    PART1 = 7, _("8859part1")
    # ISO/IEC 8859-2, Information technology - 8-bit single-byte coded graphic character sets - Part 2: Latin alphabet No. 2
    PART2 = 8, _("8859part2")
    # ISO/IEC 8859-3, Information technology - 8-bit single-byte coded graphic character sets - Part 3: Latin alphabet No. 3
    PART3 = 9, _("8859part3")
    # ISO/IEC 8859-4, Information technology - 8-bit single-byte coded graphic character sets - Part 4: Latin alphabet No. 4
    PART4 = 10, _("8859part4")
    # ISO/IEC 8859-51, Information technology - 8-bit single-byte coded graphic character sets - Part 5: Latin/Cyrillic alphabet
    PART5 = 11, _("8859part5")
    # ISO/IEC 8859-6, Information technology - 8-bit single-byte coded graphic character sets - Part 6: Latin/Arabic alphabet
    PART6 = 12, _("8859part6")
    # ISO/IEC 8859-7, Information technology - 8-bit single-byte coded graphic character sets - Part 7: Latin/Greek alphabet
    PART7 = 13, _("8859part7")
    # ISO/IEC 8859-8, Information technology - 8-bit single-byte coded graphic character sets - Part 8: Latin/Hebrew alphabet
    PART8 = 14, _("8859part8")
    # ISO/IEC8859-9, Information technology - 8-bit single-byte coded graphic character sets - Part 9: Latin alphabet No. 5
    PART9 = 15, _("8859part9")
    # ISO/IEC 8859-10, Information technology - 8-bit single-byte coded graphic character sets - Part 10: Latin alphabet No. 6
    PART10 = 16, _("8859part10")
    # ISO/IEC 8859-11, Information technology - 8-bit single-byte coded graphic character sets - Part 11: Latin/Thai alphabet
    PART11 = 17, _("8859part11")
    # 18 (reserved for future use) a future ISO/IEC 8-bit single-byte coded graphic character set (e.g. possibly ISO/IEC 8859-12
    # ISO/IEC 8859-13, Information technology - 8-bit single-byte coded graphic character sets - Part 13: Latin alphabet No. 7
    PART13 = 19, _("8859part13")
    # ISO/IEC 8859-14, Information technology - 8-bit single-byte coded graphic character sets - Part 14: Latin alphabet No. 8 (Celtic)
    PART14 = 20, _("8859part14")
    # ISO/IEC 8859-15, Information technology - 8-bit single-byte coded graphic character sets - Part 15: Latin alphabet No. 9
    PART15 = 21, _("8859part15")
    # ISO/IEC 8859-16, Information technology - 8-bit single-byte coded graphic character sets - Part 16: Latin alphabet No. 10
    PART16 = 22, _("8859part16")
    JIS = 23, _("jis")  # japanese code set used for electronic transmission
    # japanese code set used on MS-DOS based machines
    SHIFT_JIS = 24, _("shiftJIS")
    EUC_JP = 25, _("eucJP")  # japanese code set used on UNIX based machines
    US_ASCII = 26, _("usAscii")  # united states ASCII code set (ISO 646 US)
    EBCDIC = 27, _("ebcdic")  # ibm mainframe code set
    EUC_KR = 28, _("eucKR")  # korean code set
    # traditional Chinese code set used in Taiwan, HongKong of China and other areas
    BID_5 = 29, _("big5")
    GB2312 = 30, _("GB2312")  # simplified Chinese code set


class ReferenceSystemPrefixChoices(TextChoices):
    EPSG = "EPSG"


class UpdateFrequencyChoices(SmartIntegerChoices):
    """Represents all valueable choices for MD_MaintenanceFrequencyCode<<CodeList>> ISO19139"""

    CONTINUAL = 2, _("continual")  # data is repeatedly and frequently updated
    DAILY = 3, _("daily")  # data is updated each day
    WEEKLY = 4, _("weekly")  # data is updated on a weekly basis
    FORTNIGHTLY = 5, _("fortnightly")  # data is updated every two weeks
    MONTHLY = 6, _("monthly")  # data is updated each month
    QUARTERLY = 7, _("querterly")  # data is updated every three months
    biannually = 8, _("biannually")  # data is updated twice each year
    annually = 9, _("annually")  # data is updated every year
    ASNEEDED = 10, _("as needed")  # data is updated as deemed necessary
    # data is updated in intervals that are uneven in duration
    IRREGULAR = 11, _("irregular")
    NOTPLANNED = 12, _("not planned")  # there are no plans to update the data
    # frequency of maintenance for the data is not known
    UNKNOWN = 13, _("unknown")


class CategoryChoices(SmartIntegerChoices):
    """Represents all valueable choices for  MD_TopicCategoryCode<<CodeList>> ISO19115-2"""
    """
        farming, biota, boundaries, climatologyMeteorologyAtmosphere, economy, elevation,
        environement, geoscientificInformation, health, imageryBaseMapsEarchCover,
        intelligenceMilitary, inlandWaters, location, oceans, planningCadastre, society, structure,
        transportation, utilitiesCommunication
    """
    FARMING = 1, _("farming")  # rearing of animals and/or cultivation of plants Examples: agriculture, irrigation, aquaculture, plantations, herding, pests and diseases affecting crops and livestock
    BIOTA = 2, _("biota")  # flora and fauna Examples: vegetation, wildlife, ecosystems, habitats, species distribution
    BOUNDARIES = 3, _("boundaries")  # political and administrative boundaries
    CLIMATOLOGYMETEOROLOGYATMOSPHERE = 4, _("climatologyMeteorologyAtmosphere") # processes and phenomena of the atmosphere Examples: cloud cover, weather, climate, atmospheric conditions, climate change, precipitation
    ECONOMY = 5, _("economy")  # economic activities and conditions Examples: employment, industries, income, production, consumption, trade, tourism
    ELEVATION = 6, _("elevation")  # height or depth of the Earth's surface Examples: topography, bathymetry, slope, terrain models, contours, digital elevation
    ENVIRONEMENT = 7, _("environement")  # environmental resources, protection and conservation Examples: natural resources, pollution, environmental monitoring, environmental impact assessments
    GEOSCIENTIFICINFORMATION = 8, _("geoscientificInformation")  # solid Earth and its processes Examples: geology, geophysics, soils, minerals, seismic activity, volcanology
    HEALTH = 9, _("health")  # human health and disease Examples: disease distribution, health facilities, sanitation, epidemiology
    IMAGERYBASEMAPSEARTHCOVER = 10, _("imageryBaseMapsEarchCover")  # remotely sensed imagery and base maps Examples: satellite imagery, aerial photography, land cover, land use
    INTELLIGENCEMILITARY = 11, _("intelligenceMilitary")  # military bases, facilities, operations and activities
    INLANDWATERS = 12, _("inlandWaters")  # water courses and bodies on the Earth's surface Examples: rivers, lakes, wetlands, reservoirs, watersheds
    LOCATION = 13, _("location")  # named locations and their associated information Examples: place names, postal codes, address locations
    OCEANS = 14, _("oceans")  # marine and coastal areas Examples: sea floor, coastal zones, marine ecosystems, oceanographic features
    PLANNINGCADASTRE = 15, _("planningCadastre")  # land use planning and cadastral information Examples: zoning, land parcels, property boundaries, land ownership
    SOCIETY = 16, _("society")  # social systems and activities Examples: demographics, education, culture, religion, social services
    STRUCTURE = 17, _("structure")  # man-made features and structures Examples: buildings, infrastructure, utilities, transportation networks
    TRANSPORTATION = 18, _("transportation")  # transport networks and services Examples: roads, railways, airports, public transit
    UTILITIESCOMMUNICATION = 19, _("utilitiesCommunication")  # utility and communication networks Examples: power lines, water supply, telecommunications, broadcasting
    