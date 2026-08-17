export const getDocument = (xml: string): Document => {
    const parser = new DOMParser()
    const document = parser.parseFromString(xml, 'application/xml')

    const parsererror = document.querySelector('parsererror')
    if (parsererror !== null) {
        throw new Error('Invalid XML document')
    }

    return document
}
