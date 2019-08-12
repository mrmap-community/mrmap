"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 31.07.19

"""
from pysxm import ComplexType, SimpleType


class ContactAddress(ComplexType):
    def __init__(self,
                 address_type,
                 address,
                 city,
                 state_or_province,
                 post_code,
                 country,
                 ):
        self.AddressType = address_type
        self.Address = address
        self.City = city
        self.StateOrProvince = state_or_province
        self.PostCode = post_code
        self.Country = country


class ContactPersonPrimary(ComplexType):
    def __init__(self,
                 contact_person,
                 contact_organization,
                 ):
        self.ContactPerson = contact_person
        self.ContactOrganization = contact_organization


class ContactInformation(ComplexType):
    def __init__(self,
                 contact_person,
                 contact_organization,
                 contact_position,
                 address_type,
                 address,
                 city,
                 state_or_province,
                 post_code,
                 country,
                 contact_voice_telephone,
                 contact_electronic_mail_address,
                 ):
        self.ContactPersonPrimary = ContactPersonPrimary(contact_person, contact_organization)
        self.ContactPosition = contact_position
        self.ContactAddress = ContactAddress(address_type, address, city, state_or_province, post_code, country,)
        self.ContactVoiceTelephone = contact_voice_telephone
        self.ContactElectronicMailAddress = contact_electronic_mail_address


class Keyword(SimpleType):
    pass


class Service(ComplexType):
    def __init__(self,
                 name,
                 title,
                 abstract,
                 keywords_list,
                 online_resource,
                 contact_information: dict,
                 fees,
                 access_constraints,
                 layer_limit,
                 max_width,
                 max_height,
                 ):
        self.Name = name
        self.Title = title
        self.Abstract = abstract
        self.KeywordList = []
        for keyword in keywords_list:
            self.KeywordList.append(Keyword(keyword))
        self.OnlineResource = online_resource
        self.ContactInformation = ContactInformation(
                 contact_information.get("contact_person", None),
                 contact_information.get("contact_organization", None),
                 contact_information.get("contact_position", None),
                 contact_information.get("address_type", None),
                 contact_information.get("address", None),
                 contact_information.get("city", None),
                 contact_information.get("state_or_province", None),
                 contact_information.get("post_code", None),
                 contact_information.get("country", None),
                 contact_information.get("contact_voice_telephone", None),
                 contact_information.get("contact_electronic_mail_address", None),
        )
        self.Fees = fees
        self.AccessConstraints = access_constraints
        self.LayerLimit = layer_limit
        self.MaxWidth = max_width
        self.MaxHeight = max_height
