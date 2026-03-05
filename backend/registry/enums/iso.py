from extras.enums import SmartIntegerChoices


class MetadataCharsetChoices(SmartIntegerChoices):
    """Represents all valueable choices for MD_CharacterSetCode<<CodeList>> ISO19139"""
    # 16-bit fixed size Universal Character Set, based on ISO/IEC 10646
    UCS2 = 2, "ucs2"
    # 32-bit fixed size Universal Character Set, based on ISO/IEC 10646
    UCS4 = 3, "ucs4"
    # 7-bit variable size UCS Transfer Format, based on ISO/IEC 10646
    UTF7 = 4, "utf7"
    # 8-bit variable size UCS Transfer Format, based on ISO/IEC 10646
    UTF8 = 5, "utf8"
    # 16-bit variable size UCS Transfer Format, based on ISO/IEC 10646
    UTF16 = 6, "utf16"
    # ISO/IEC 8859-1, Information technology - 8-bit single-byte coded graphic character sets - Part 1: Latin alphabet No. 1
    PART1 = 7, "8859part1"
    # ISO/IEC 8859-2, Information technology - 8-bit single-byte coded graphic character sets - Part 2: Latin alphabet No. 2
    PART2 = 8, "8859part2"
    # ISO/IEC 8859-3, Information technology - 8-bit single-byte coded graphic character sets - Part 3: Latin alphabet No. 3
    PART3 = 9, "8859part3"
    # ISO/IEC 8859-4, Information technology - 8-bit single-byte coded graphic character sets - Part 4: Latin alphabet No. 4
    PART4 = 10, "8859part4"
    # ISO/IEC 8859-51, Information technology - 8-bit single-byte coded graphic character sets - Part 5: Latin/Cyrillic alphabet
    PART5 = 11, "8859part5"
    # ISO/IEC 8859-6, Information technology - 8-bit single-byte coded graphic character sets - Part 6: Latin/Arabic alphabet
    PART6 = 12, "8859part6"
    # ISO/IEC 8859-7, Information technology - 8-bit single-byte coded graphic character sets - Part 7: Latin/Greek alphabet
    PART7 = 13, "8859part7"
    # ISO/IEC 8859-8, Information technology - 8-bit single-byte coded graphic character sets - Part 8: Latin/Hebrew alphabet
    PART8 = 14, "8859part8"
    # ISO/IEC8859-9, Information technology - 8-bit single-byte coded graphic character sets - Part 9: Latin alphabet No. 5
    PART9 = 15, "8859part9"
    # ISO/IEC 8859-10, Information technology - 8-bit single-byte coded graphic character sets - Part 10: Latin alphabet No. 6
    PART10 = 16, "8859part10"
    # ISO/IEC 8859-11, Information technology - 8-bit single-byte coded graphic character sets - Part 11: Latin/Thai alphabet
    PART11 = 17, "8859part11"
    # 18 (reserved for future use a future ISO/IEC 8-bit single-byte coded graphic character set (e.g. possibly ISO/IEC 8859-12
    # ISO/IEC 8859-13, Information technology - 8-bit single-byte coded graphic character sets - Part 13: Latin alphabet No. 7
    PART13 = 19, "8859part13"
    # ISO/IEC 8859-14, Information technology - 8-bit single-byte coded graphic character sets - Part 14: Latin alphabet No. 8 (Celtic
    PART14 = 20, "8859part14"
    # ISO/IEC 8859-15, Information technology - 8-bit single-byte coded graphic character sets - Part 15: Latin alphabet No. 9
    PART15 = 21, "8859part15"
    # ISO/IEC 8859-16, Information technology - 8-bit single-byte coded graphic character sets - Part 16: Latin alphabet No. 10
    PART16 = 22, "8859part16"
    JIS = 23, "jis"  # japanese code set used for electronic transmission
    # japanese code set used on MS-DOS based machines
    SHIFT_JIS = 24, "shiftJIS"
    EUC_JP = 25, "eucJP"  # japanese code set used on UNIX based machines
    US_ASCII = 26, "usAscii"  # united states ASCII code set (ISO 646 US
    EBCDIC = 27, "ebcdic"  # ibm mainframe code set
    EUC_KR = 28, "eucKR"  # korean code set
    # traditional Chinese code set used in Taiwan, HongKong of China and other areas
    BID_5 = 29, "big5"
    GB2312 = 30, "GB2312"  # simplified Chinese code set


class UpdateFrequencyChoices(SmartIntegerChoices):
    """Represents all valueable choices for MD_MaintenanceFrequencyCode<<CodeList>> ISO19139"""

    CONTINUAL = 2, "continual"  # data is repeatedly and frequently updated
    DAILY = 3, "daily"  # data is updated each day
    WEEKLY = 4, "weekly"  # data is updated on a weekly basis
    FORTNIGHTLY = 5, "fortnightly"  # data is updated every two weeks
    MONTHLY = 6, "monthly"  # data is updated each month
    QUARTERLY = 7, "quarterly"  # data is updated every three months
    BIANNUALLY = 8, "biannually"  # data is updated twice each year
    ANNUALLY = 9, "annually"  # data is updated every year
    ASNEEDED = 10, "as needed"  # data is updated as deemed necessary
    IRREGULAR = 11, "irregular"  # data is updated in intervals that are uneven in duration
    NOTPLANNED = 12, "not planned"  # there are no plans to update the data
    UNKNOWN = 13, "unknown"  # frequency of maintenance for the data is not known


class CategoryChoices(SmartIntegerChoices):
    """Represents all valueable choices for  MD_TopicCategoryCode<<CodeList>> ISO19115-2

    farming, biota, boundaries, climatologyMeteorologyAtmosphere, economy, elevation,
    environment, geoscientificInformation, health, imageryBaseMapsEarthCover,
    intelligenceMilitary, inlandWaters, location, oceans, planningCadastre, society, structure,
    transportation, utilitiesCommunication
    """
    FARMING = 1, "farming"  # rearing of animals and/or cultivation of plants Examples: agriculture, irrigation, aquaculture, plantations, herding, pests and diseases affecting crops and livestock
    # flora and fauna Examples: vegetation, wildlife, ecosystems, habitats, species distribution
    BIOTA = 2, "biota"
    BOUNDARIES = 3, "boundaries"  # political and administrative boundaries
    # processes and phenomena of the atmosphere Examples: cloud cover, weather, climate, atmospheric conditions, climate change, precipitation
    CLIMATOLOGYMETEOROLOGYATMOSPHERE = 4, "climatologyMeteorologyAtmosphere"
    # economic activities and conditions Examples: employment, industries, income, production, consumption, trade, tourism
    ECONOMY = 5, "economy"
    # height or depth of the Earth's surface Examples: topography, bathymetry, slope, terrain models, contours, digital elevation
    ELEVATION = 6, "elevation"
    # environmental resources, protection and conservation Examples: natural resources, pollution, environmental monitoring, environmental impact assessments
    EVNVIRONMENT = 7, "environment"
    # solid Earth and its processes Examples: geology, geophysics, soils, minerals, seismic activity, volcanology
    GEOSCIENTIFICINFORMATION = 8, "geoscientificInformation"
    # human health and disease Examples: disease distribution, health facilities, sanitation, epidemiology
    HEALTH = 9, "health"
    # remotely sensed imagery and base maps Examples: satellite imagery, aerial photography, land cover, land use
    IMAGERYBASEMAPSEARTHCOVER = 10, "imageryBaseMapsEarthCover"
    # military bases, facilities, operations and activities
    INTELLIGENCEMILITARY = 11, "intelligenceMilitary"
    # water courses and bodies on the Earth's surface Examples: rivers, lakes, wetlands, reservoirs, watersheds
    INLANDWATERS = 12, "inlandWaters"
    # named locations and their associated information Examples: place names, postal codes, address locations
    LOCATION = 13, "location"
    # marine and coastal areas Examples: sea floor, coastal zones, marine ecosystems, oceanographic features
    OCEANS = 14, "oceans"
    # land use planning and cadastral information Examples: zoning, land parcels, property boundaries, land ownership
    PLANNINGCADASTRE = 15, "planningCadastre"
    # social systems and activities Examples: demographics, education, culture, religion, social services
    SOCIETY = 16, "society"
    # man-made features and structures Examples: buildings, infrastructure, utilities, transportation networks
    STRUCTURE = 17, "structure"
    # transport networks and services Examples: roads, railways, airports, public transit
    TRANSPORTATION = 18, "transportation"
    # utility and communication networks Examples: power lines, water supply, telecommunications, broadcasting
    UTILITIESCOMMUNICATION = 19, "utilitiesCommunication"


class LanguageChoices(SmartIntegerChoices):
    # ISO 639-2 language codes
    AAR = 1, "aar"  # Afar
    ABK = 2, "abk"  # Abkhazian
    ACE = 3, "ace"  # Achinese
    ACH = 4, "ach"  # Acoli
    ADA = 5, "ada"  # Adangme
    ADY = 6, "ady"  # Adyghe ; Adygei
    AFA = 7, "afa"  # Afro-Asiatic languages
    AFH = 8, "afh"  # Afrihili
    AFR = 9, "afr"  # Afrikaans
    AIN = 10, "ain"  # Ainu
    AKA = 11, "aka"  # Akan
    AKK = 12, "akk"  # Akkadian
    ALE = 13, "ale"  # Aleut
    ALG = 14, "alg"  # Algonquian languages
    ALT = 15, "alt"  # Southern Altai
    AMH = 16, "amh"  # Amharic
    ANG = 17, "ang"  # English, Old (ca.450–1100)
    ANP = 18, "anp"  # Angika
    APA = 19, "apa"  # Apache languages
    ARA = 20, "ara"  # Arabic
    ARC = 21, "arc"  # Official Aramaic (700–300 BCE); Imperial Aramaic (700–300 BCE)
    ARG = 22, "arg"  # Aragonese
    ARN = 23, "arn"  # Mapudungun; Mapuche
    ARP = 24, "arp"  # Arapaho
    ART = 25, "art"  # Artificial languages
    ARW = 26, "arw"  # Arawak
    ASM = 27, "asm"  # Assamese
    AST = 28, "ast"  # Asturian ; Bable ; Leonese ; Asturleonese
    ATH = 29, "ath"  # Athapascan languages
    AUS = 30, "aus"  # Australian languages
    AVA = 31, "ava"  # Avaric
    AVE = 32, "ave"  # Avestan
    AWA = 33, "awa"  # Awadhi
    AYM = 34, "aym"  # Aymara
    AZE = 35, "aze"  # Azerbaijani
    BAD = 36, "bad"  # Banda languages
    BAI = 37, "bai"  # Bamileke languages
    BAK = 38, "bak"  # Bashkir
    BAL = 39, "bal"  # Baluchi
    BAM = 40, "bam"  # Bambara
    BAN = 41, "ban"  # Balinese
    BAS = 42, "bas"  # Basa
    BAT = 43, "bat"  # Baltic languages
    BEJ = 44, "bej"  # Beja ; Bedawiyet
    BEL = 45, "bel"  # Belarusian
    BEM = 46, "bem"  # Bemba
    BEN = 47, "ben"  # Bengali
    BER = 48, "ber"  # Berber languages
    BHO = 49, "bho"  # Bhojpuri
    BIH = 50, "bih"  # Bihari languages
    BIK = 51, "bik"  # Bikol
    BIN = 52, "bin"  # Bini ; Edo
    BIS = 53, "bis"  # Bislama
    BLA = 54, "bla"  # Siksika
    BNT = 55, "bnt"  # Bantu languages
    BOD = 56, "bod"  # Tibetan
    TIB = 57, "tib"  # Tibetan
    BOS = 58, "bos"  # Bosnian
    BRA = 59, "bra"  # Braj
    BRE = 60, "bre"  # Breton
    BTK = 61, "btk"  # Batak languages
    BUA = 62, "bua"  # Buriat
    BUG = 63, "bug"  # Buginese
    BUL = 64, "bul"  # Bulgarian
    BYN = 65, "byn"  # Blin; Bilin
    CAD = 66, "cad"  # Caddo
    CAI = 67, "cai"  # Central American Indian languages
    CAR = 68, "car"  # Galibi Carib
    CAT = 69, "cat"  # Catalan ; Valencian
    CAU = 70, "cau"  # Caucasian languages
    CEB = 71, "ceb"  # Cebuano
    CEL = 72, "cel"  # Celtic languages
    CES = 73, "ces"  # Czech
    CZE = 74, "cze"  # Czech
    CHA = 75, "cha"  # Chamorro
    CHB = 76, "chb"  # Chibcha
    CHE = 77, "che"  # Chechen
    CHG = 78, "chg"  # Chagatai
    CHK = 79, "chk"  # Chuukese
    CHM = 80, "chm"  # Mari
    CHN = 81, "chn"  # Chinook Jargon
    CHO = 82, "cho"  # Choctaw
    CHP = 83, "chp"  # Chipewyan ; Dene Suline
    CHR = 84, "chr"  # Cherokee
    CHU = 85, "chu"  # Church Slavic ; Old Slavonic ; Church Slavonic ; Old Bulgarian ; Old Church Slavonic
    CHV = 86, "chv"  # Chuvash
    CHY = 87, "chy"  # Cheyenne
    CMC = 88, "cmc"  # Chamic languages
    CNR = 89, "cnr"  # Montenegrin
    COP = 90, "cop"  # Coptic
    COR = 91, "cor"  # Cornish
    COS = 92, "cos"  # Corsican
    CPE = 93, "cpe"  # Creoles and pidgins , English based
    CPF = 94, "cpf"  # Creoles and pidgins, French-based
    CPP = 95, "cpp"  # Creoles and pidgins, Portuguese-based
    CRE = 96, "cre"  # Cree
    CRH = 97, "crh"  # Crimean Tatar ; Crimean Turkish
    CRP = 98, "crp"  # Creoles and pidgins
    CSB = 99, "csb"  # Kashubian
    CUS = 100, "cus"  # Cushitic languages
    CYM = 101, "cym"  # Welsh
    WEL = 102, "wel"  # Welsh
    DAK = 103, "dak"  # Dakota
    DAN = 104, "dan"  # Danish
    DAR = 105, "dar"  # Dargwa
    DAY = 106, "day"  # Land Dayak languages
    DEL = 107, "del"  # Delaware
    DEN = 108, "den"  # Slave (Athapascan)
    DEU = 109, "deu"  # German
    GER = 110, "ger"  # German
    DGR = 111, "dgr"  # Tlicho; Dogrib
    DIN = 112, "din"  # Dinka
    DIV = 113, "div"  # Divehi; Dhivehi; Maldivian
    DOI = 114, "doi"  # Dogri
    DRA = 115, "dra"  # Dravidian languages
    DSB = 116, "dsb"  # Lower Sorbian
    DUA = 117, "dua"  # Duala
    DUM = 118, "dum"  # Dutch, Middle (ca.1050–1350)
    DYU = 119, "dyu"  # Dyula
    DZO = 120, "dzo"  # Dzongkha
    EFI = 121, "efi"  # Efik
    EGY = 122, "egy"  # Egyptian (Ancient)
    EKA = 123, "eka"  # Ekajuk
    ELL = 124, "ell"  # Greek, Modern (1453–)
    GRE = 125, "gre"  # Greek, Modern (1453–)
    ELX = 126, "elx"  # Elamite
    ENG = 127, "eng"  # English
    ENM = 128, "enm"  # English, Middle (1100–1500)
    EPO = 129, "epo"  # Esperanto
    EST = 130, "est"  # Estonian
    EUS = 131, "eus"  # Basque
    BAQ = 132, "baq"  # Basque
    EWE = 133, "ewe"  # Ewe
    EWO = 134, "ewo"  # Ewondo
    FAN = 135, "fan"  # Fang
    FAO = 136, "fao"  # Faroese
    FAS = 137, "fas"  # Persian
    PER = 138, "per"  # Persian
    FAT = 139, "fat"  # Fanti
    FIJ = 140, "fij"  # Fijian
    FIL = 141, "fil"  # Filipino ; Pilipino
    FIN = 142, "fin"  # Finnish
    FIU = 143, "fiu"  # Finno-Ugrian languages
    FON = 144, "fon"  # Fon
    FRA = 145, "fra"  # French
    FRE = 146, "fre"  # French
    FRM = 147, "frm"  # French, Middle (ca.1400–1600)
    FRO = 148, "fro"  # French, Old (842–ca.1400)
    FRR = 149, "frr"  # Northern Frisian
    FRS = 150, "frs"  # Eastern Frisian
    FRY = 151, "fry"  # Western Frisian
    FUL = 152, "ful"  # Fulah
    FUR = 153, "fur"  # Friulian
    GAA = 154, "gaa"  # Ga
    GAY = 155, "gay"  # Gayo
    GBA = 156, "gba"  # Gbaya
    GEM = 157, "gem"  # Germanic languages
    GEZ = 158, "gez"  # Geez
    GIL = 159, "gil"  # Gilbertese
    GLA = 160, "gla"  # Gaelic ; Scottish Gaelic
    GLE = 161, "gle"  # Irish
    GLG = 162, "glg"  # Galician
    GLV = 163, "glv"  # Manx
    GMH = 164, "gmh"  # German, Middle High (ca.1050–1500)
    GOH = 165, "goh"  # German, Old High (ca.750–1050)
    GON = 166, "gon"  # Gondi
    GOR = 167, "gor"  # Gorontalo
    GOT = 168, "got"  # Gothic
    GRB = 169, "grb"  # Grebo
    GRC = 170, "grc"  # Greek, Ancient (to 1453)
    GRN = 171, "grn"  # Guarani
    GSW = 172, "gsw"  # Swiss German ; Alemannic ; Alsatian
    GUJ = 173, "guj"  # Gujarati
    GWI = 174, "gwi"  # Gwich'in
    HAI = 175, "hai"  # Haida
    HAT = 176, "hat"  # Haitian; Haitian Creole
    HAU = 177, "hau"  # Hausa
    HAW = 178, "haw"  # Hawaiian
    HEB = 179, "heb"  # Hebrew
    HER = 180, "her"  # Herero
    HIL = 181, "hil"  # Hiligaynon
    HIM = 182, "him"  # Himachali languages; Pahari languages
    HIN = 183, "hin"  # Hindi
    HIT = 184, "hit"  # Hittite
    HMN = 185, "hmn"  # Hmong ; Mong
    HMO = 186, "hmo"  # Hiri Motu
    HRV = 187, "hrv"  # Croatian
    HSB = 188, "hsb"  # Upper Sorbian
    HUN = 189, "hun"  # Hungarian
    HUP = 190, "hup"  # Hupa
    HYE = 191, "hye"  # Armenian
    ARM = 192, "arm"  # Armenian
    IBA = 193, "iba"  # Iban
    IBO = 194, "ibo"  # Igbo
    IDO = 195, "ido"  # Ido
    III = 196, "iii"  # Sichuan Yi ; Nuosu
    IJO = 197, "ijo"  # Ijo languages
    IKU = 198, "iku"  # Inuktitut
    ILE = 199, "ile"  # Interlingue; Occidental
    ILO = 200, "ilo"  # Iloko
    INA = 201, "ina"  # Interlingua ( International Auxiliary Language Association )
    INC = 202, "inc"  # Indic languages
    IND = 203, "ind"  # Indonesian
    INE = 204, "ine"  # Indo-European languages
    INH = 205, "inh"  # Ingush
    IPK = 206, "ipk"  # Inupiaq
    IRA = 207, "ira"  # Iranian languages
    IRO = 208, "iro"  # Iroquoian languages
    ISL = 209, "isl"  # Icelandic
    ICE = 210, "ice"  # Icelandic
    ITA = 211, "ita"  # Italian
    JAV = 212, "jav"  # Javanese
    JBO = 213, "jbo"  # Lojban
    JPN = 214, "jpn"  # Japanese
    JPR = 215, "jpr"  # Judeo-Persian
    JRB = 216, "jrb"  # Judeo-Arabic
    KAA = 217, "kaa"  # Kara-Kalpak
    KAB = 218, "kab"  # Kabyle
    KAC = 219, "kac"  # Kachin ; Jingpho
    KAL = 220, "kal"  # Kalaallisut ; Greenlandic
    KAM = 221, "kam"  # Kamba
    KAN = 222, "kan"  # Kannada
    KAR = 223, "kar"  # Karen languages
    KAS = 224, "kas"  # Kashmiri
    KAT = 225, "kat"  # Georgian
    GEO = 226, "geo"  # Georgian
    KAU = 227, "kau"  # Kanuri
    KAW = 228, "kaw"  # Kawi
    KAZ = 229, "kaz"  # Kazakh
    KBD = 230, "kbd"  # Kabardian
    KHA = 231, "kha"  # Khasi
    KHI = 232, "khi"  # Khoisan languages
    KHM = 233, "khm"  # Central Khmer
    KHO = 234, "kho"  # Khotanese ; Sakan
    KIK = 235, "kik"  # Kikuyu ; Gikuyu
    KIN = 236, "kin"  # Kinyarwanda
    KIR = 237, "kir"  # Kirghiz ; Kyrgyz
    KMB = 238, "kmb"  # Kimbundu
    KOK = 239, "kok"  # Konkani
    KOM = 240, "kom"  # Komi
    KON = 241, "kon"  # Kongo
    KOR = 242, "kor"  # Korean
    KOS = 243, "kos"  # Kosraean
    KPE = 244, "kpe"  # Kpelle
    KRC = 245, "krc"  # Karachay-Balkar
    KRL = 246, "krl"  # Karelian
    KRO = 247, "kro"  # Kru languages
    KRU = 248, "kru"  # Kurukh
    KUA = 249, "kua"  # Kuanyama ; Kwanyama
    KUM = 250, "kum"  # Kumyk
    KUR = 251, "kur"  # Kurdish
    KUT = 252, "kut"  # Kutenai
    LAD = 253, "lad"  # Ladino
    LAH = 254, "lah"  # Lahnda
    LAM = 255, "lam"  # Lamba
    LAO = 256, "lao"  # Lao
    LAT = 257, "lat"  # Latin
    LAV = 258, "lav"  # Latvian
    LEZ = 259, "lez"  # Lezghian
    LIM = 260, "lim"  # Limburgan ; Limburger ; Limburgish
    LIN = 261, "lin"  # Lingala
    LIT = 262, "lit"  # Lithuanian
    LOL = 263, "lol"  # Mongo
    LOZ = 264, "loz"  # Lozi
    LTZ = 265, "ltz"  # Luxembourgish ; Letzeburgesch
    LUA = 266, "lua"  # Luba-Lulua
    LUB = 267, "lub"  # Luba-Katanga
    LUG = 268, "lug"  # Ganda
    LUI = 269, "lui"  # Luiseno
    LUN = 270, "lun"  # Lunda
    LUO = 271, "luo"  # Luo (Kenya and Tanzania)
    LUS = 272, "lus"  # Lushai
    MAD = 273, "mad"  # Madurese
    MAG = 274, "mag"  # Magahi
    MAH = 275, "mah"  # Marshallese
    MAI = 276, "mai"  # Maithili
    MAK = 277, "mak"  # Makasar
    MAL = 278, "mal"  # Malayalam
    MAN = 279, "man"  # Mandingo
    MAP = 280, "map"  # Austronesian languages
    MAR = 281, "mar"  # Marathi
    MAS = 282, "mas"  # Masai
    MDF = 283, "mdf"  # Moksha
    MDR = 284, "mdr"  # Mandar
    MEN = 285, "men"  # Mende
    MGA = 286, "mga"  # Irish, Middle (900–1200)
    MIC = 287, "mic"  # Mi'kmaq ; Micmac
    MIN = 288, "min"  # Minangkabau
    MIS = 289, "mis"  # Uncoded languages
    MKD = 290, "mkd"  # Macedonian
    MAC = 291, "mac"  # Macedonian
    MKH = 292, "mkh"  # Mon-Khmer languages
    MLG = 293, "mlg"  # Malagasy
    MLT = 294, "mlt"  # Maltese
    MNC = 295, "mnc"  # Manchu
    MNI = 296, "mni"  # Manipuri
    MNO = 297, "mno"  # Manobo languages
    MOH = 298, "moh"  # Mohawk
    MON = 299, "mon"  # Mongolian
    MOS = 300, "mos"  # Mossi
    MRI = 301, "mri"  # Maori
    MAO = 302, "mao"  # Maori
    MSA = 303, "msa"  # Malay
    MAY = 304, "may"  # Malay
    MUL = 305, "mul"  # Multiple languages
    MUN = 306, "mun"  # Munda languages
    MUS = 307, "mus"  # Creek
    MWL = 308, "mwl"  # Mirandese
    MWR = 309, "mwr"  # Marwari
    MYA = 310, "mya"  # Burmese
    BUR = 311, "bur"  # Burmese
    MYN = 312, "myn"  # Mayan languages
    MYV = 313, "myv"  # Erzya
    NAH = 314, "nah"  # Nahuatl languages
    NAI = 315, "nai"  # North American Indian languages
    NAP = 316, "nap"  # Neapolitan
    NAU = 317, "nau"  # Nauru
    NAV = 318, "nav"  # Navajo ; Navaho
    NBL = 319, "nbl"  # Ndebele, South; South Ndebele
    NDE = 320, "nde"  # Ndebele, North; North Ndebele
    NDO = 321, "ndo"  # Ndonga
    NDS = 322, "nds"  # Low German ; Low Saxon; German, Low; Saxon, Low
    NEP = 323, "nep"  # Nepali
    NEW = 324, "new"  # Nepal Bhasa ; Newari
    NIA = 325, "nia"  # Nias
    NIC = 326, "nic"  # Niger-Kordofanian languages
    NIU = 327, "niu"  # Niuean
    NLD = 328, "nld"  # Dutch ; Flemish
    DUT = 329, "dut"  # Dutch ; Flemish
    NNO = 330, "nno"  # Norwegian Nynorsk ; Nynorsk, Norwegian
    NOB = 331, "nob"  # Bokmål , Norwegian; Norwegian Bokmål
    NOG = 332, "nog"  # Nogai
    NON = 333, "non"  # Norse, Old
    NOR = 334, "nor"  # Norwegian
    NQO = 335, "nqo"  # N'Ko
    NSO = 336, "nso"  # Pedi ; Sepedi ; Northern Sotho
    NUB = 337, "nub"  # Nubian languages
    NWC = 338, "nwc"  # Classical Newari ; Old Newari ; Classical Nepal Bhasa
    NYA = 339, "nya"  # Chichewa ; Chewa ; Nyanja
    NYM = 340, "nym"  # Nyamwezi
    NYN = 341, "nyn"  # Nyankole
    NYO = 342, "nyo"  # Nyoro
    NZI = 343, "nzi"  # Nzima
    OCI = 344, "oci"  # Occitan (post 1500)
    OJI = 345, "oji"  # Ojibwa
    ORI = 346, "ori"  # Oriya
    ORM = 347, "orm"  # Oromo
    OSA = 348, "osa"  # Osage
    OSS = 349, "oss"  # Ossetian ; Ossetic
    OTA = 350, "ota"  # Turkish, Ottoman (1500–1928)
    OTO = 351, "oto"  # Otomian languages
    PAA = 352, "paa"  # Papuan languages
    PAG = 353, "pag"  # Pangasinan
    PAL = 354, "pal"  # Pahlavi
    PAM = 355, "pam"  # Pampanga ; Kapampangan
    PAN = 356, "pan"  # Panjabi ; Punjabi
    PAP = 357, "pap"  # Papiamento
    PAU = 358, "pau"  # Palauan
    PEO = 359, "peo"  # Persian, Old (ca.600–400 B.C.)
    PHI = 360, "phi"  # Philippine languages
    PHN = 361, "phn"  # Phoenician
    PLI = 362, "pli"  # Pali
    POL = 363, "pol"  # Polish
    PON = 364, "pon"  # Pohnpeian
    POR = 365, "por"  # Portuguese
    PRA = 366, "pra"  # Prakrit languages
    PRO = 367, "pro"  # Provençal, Old (to 1500); Old Occitan (to 1500)
    PUS = 368, "pus"  # Pushto ; Pashto
    QAA = 369, "qaa"  # Reserved for local use
    QTZ = 370, "qtz"  # Reserved for local use
    QUE = 371, "que"  # Quechua
    RAJ = 372, "raj"  # Rajasthani
    RAP = 373, "rap"  # Rapanui
    RAR = 374, "rar"  # Rarotongan; Cook Islands Maori
    ROA = 375, "roa"  # Romance languages
    ROH = 376, "roh"  # Romansh
    ROM = 377, "rom"  # Romany
    RON = 378, "ron"  # Romanian ; Moldavian; Moldovan
    RUM = 379, "rum"  # Romanian ; Moldavian; Moldovan
    RUN = 380, "run"  # Rundi
    RUP = 381, "rup"  # Aromanian ; Arumanian; Macedo-Romanian [ b ]
    RUS = 382, "rus"  # Russian
    SAD = 383, "sad"  # Sandawe
    SAG = 384, "sag"  # Sango
    SAH = 385, "sah"  # Yakut
    SAI = 386, "sai"  # South American Indian languages
    SAL = 387, "sal"  # Salishan languages
    SAM = 388, "sam"  # Samaritan Aramaic
    SAN = 389, "san"  # Sanskrit
    SAS = 390, "sas"  # Sasak
    SAT = 391, "sat"  # Santali
    SCN = 392, "scn"  # Sicilian
    SCO = 393, "sco"  # Scots
    SEL = 394, "sel"  # Selkup
    SEM = 395, "sem"  # Semitic languages
    SGA = 396, "sga"  # Irish, Old (to 900)
    SGN = 397, "sgn"  # Sign languages
    SHN = 398, "shn"  # Shan
    SID = 399, "sid"  # Sidamo
    SIN = 400, "sin"  # Sinhala ; Sinhalese
    SIO = 401, "sio"  # Siouan languages
    SIT = 402, "sit"  # Sino-Tibetan languages
    SLA = 403, "sla"  # Slavic languages
    SLK = 404, "slk"  # Slovak
    SLO = 405, "slo"  # Slovak
    SLV = 406, "slv"  # Slovenian
    SMA = 407, "sma"  # Southern Sami
    SME = 408, "sme"  # Northern Sami
    SMI = 409, "smi"  # Sami languages
    SMJ = 410, "smj"  # Lule Sami
    SMN = 411, "smn"  # Inari Sami
    SMO = 412, "smo"  # Samoan
    SMS = 413, "sms"  # Skolt Sami
    SNA = 414, "sna"  # Shona
    SND = 415, "snd"  # Sindhi
    SNK = 416, "snk"  # Soninke
    SOG = 417, "sog"  # Sogdian
    SOM = 418, "som"  # Somali
    SON = 419, "son"  # Songhai languages
    SOT = 420, "sot"  # Sotho, Southern
    SPA = 421, "spa"  # Spanish ; Castilian
    SQI = 422, "sqi"  # Albanian
    ALB = 423, "alb"  # Albanian
    SRD = 424, "srd"  # Sardinian
    SRN = 425, "srn"  # Sranan Tongo
    SRP = 426, "srp"  # Serbian
    SRR = 427, "srr"  # Serer
    SSA = 428, "ssa"  # Nilo-Saharan languages
    SSW = 429, "ssw"  # Swati
    SUK = 430, "suk"  # Sukuma
    SUN = 431, "sun"  # Sundanese
    SUS = 432, "sus"  # Susu
    SUX = 433, "sux"  # Sumerian
    SWA = 434, "swa"  # Swahili
    SWE = 435, "swe"  # Swedish
    SYC = 436, "syc"  # Classical Syriac
    SYR = 437, "syr"  # Syriac
    TAH = 438, "tah"  # Tahitian
    TAI = 439, "tai"  # Tai languages
    TAM = 440, "tam"  # Tamil
    TAT = 441, "tat"  # Tatar
    TEL = 442, "tel"  # Telugu
    TEM = 443, "tem"  # Timne
    TER = 444, "ter"  # Tereno
    TET = 445, "tet"  # Tetum
    TGK = 446, "tgk"  # Tajik
    TGL = 447, "tgl"  # Tagalog
    THA = 448, "tha"  # Thai
    TIG = 449, "tig"  # Tigre
    TIR = 450, "tir"  # Tigrinya
    TIV = 451, "tiv"  # Tiv
    TKL = 452, "tkl"  # Tokelau
    TLH = 453, "tlh"  # Klingon ; tlhIngan-Hol
    TLI = 454, "tli"  # Tlingit
    TMH = 455, "tmh"  # Tamashek
    TOG = 456, "tog"  # Tonga (Nyasa)
    TON = 457, "ton"  # Tonga (Tonga Islands)
    TPI = 458, "tpi"  # Tok Pisin
    TSI = 459, "tsi"  # Tsimshian
    TSN = 460, "tsn"  # Tswana
    TSO = 461, "tso"  # Tsonga
    TUK = 462, "tuk"  # Turkmen
    TUM = 463, "tum"  # Tumbuka
    TUP = 464, "tup"  # Tupi languages
    TUR = 465, "tur"  # Turkish
    TUT = 466, "tut"  # Altaic languages
    TVL = 467, "tvl"  # Tuvalu
    TWI = 468, "twi"  # Twi
    TYV = 469, "tyv"  # Tuvinian
    UDM = 470, "udm"  # Udmurt
    UGA = 471, "uga"  # Ugaritic
    UIG = 472, "uig"  # Uighur ; Uyghur
    UKR = 473, "ukr"  # Ukrainian
    UMB = 474, "umb"  # Umbundu
    UND = 475, "und"  # Undetermined
    URD = 476, "urd"  # Urdu
    UZB = 477, "uzb"  # Uzbek
    VAI = 478, "vai"  # Vai
    VEN = 479, "ven"  # Venda
    VIE = 480, "vie"  # Vietnamese
    VOL = 481, "vol"  # Volapük
    VOT = 482, "vot"  # Votic
    WAK = 483, "wak"  # Wakashan languages
    WAL = 484, "wal"  # Wolaitta ; Wolaytta
    WAR = 485, "war"  # Waray
    WAS = 486, "was"  # Washo
    WEN = 487, "wen"  # Sorbian languages
    WLN = 488, "wln"  # Walloon
    WOL = 489, "wol"  # Wolof
    XAL = 490, "xal"  # Kalmyk ; Oirat
    XHO = 491, "xho"  # Xhosa
    YAO = 492, "yao"  # Yao
    YAP = 493, "yap"  # Yapese
    YID = 494, "yid"  # Yiddish
    YOR = 495, "yor"  # Yoruba
    YPK = 496, "ypk"  # Yupik languages
    ZAP = 497, "zap"  # Zapotec
    ZBL = 498, "zbl"  # Blissymbols ; Blissymbolics ; Bliss
    ZEN = 499, "zen"  # Zenaga
    ZGH = 500, "zgh"  # Standard Moroccan Tamazight
    ZHA = 501, "zha"  # Zhuang ; Chuang
    ZHO = 502, "zho"  # Chinese
    CHI = 503, "chi"  # Chinese
    ZND = 504, "znd"  # Zande languages
    ZUL = 505, "zul"  # Zulu
    ZUN = 506, "zun"  # Zuni
    ZXX = 507, "zxx"  # No linguistic content; Not applicable
    ZZA = 508, "zza"  # Zaza ; Dimili ; Dimli ; Kirdki ; Kirmanjki ; Zazaki
