from registry.models.metadata import ReferenceSystem


def parse_reference_systems(mapper, elements):
    """
    Parst alle DefaultCRS und OtherCRS des aktuellen FeatureType.

    """
    instances = []
    for element in elements:
        code = ""
        prefix = ""
        crs_text = element.text
        if "http://www.opengis.net/def/crs/EPSG" in crs_text:
            code = crs_text.split("/")[-1]
            prefix = "EPSG"
        else:
            code = crs_text.split(":")[-1]
            prefix = "EPSG"

        if code and prefix:
            instances.append(
                ReferenceSystem(
                    code=code,
                    prefix=prefix
                )
            )

    return instances
