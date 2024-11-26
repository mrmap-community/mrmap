import { X2jOptions, XMLParser } from "fast-xml-parser"

export const getDocument = (xml: string): any => {
    const options: X2jOptions = {
        ignoreAttributes: false,
        attributeNamePrefix : "@_",
        removeNSPrefix: true,
    }
    const parser = new XMLParser(options)
    return parser.parse(xml)
}
