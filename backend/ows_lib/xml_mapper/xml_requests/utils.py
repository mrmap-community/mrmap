from eulxml.xmlmap import StringField, XmlObject


class PostRequest(XmlObject):

    operation = StringField(xpath="local-name()")
    version = StringField(xpath="./@version")
    service_type = StringField(xpath="./@service")
