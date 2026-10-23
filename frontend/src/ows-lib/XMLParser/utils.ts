export const getDocument = (xml: string): Document => {
    const parser = new DOMParser()
    const document = parser.parseFromString(xml, 'application/xml')

    const parsererror = document.querySelector('parsererror')
    if (parsererror !== null) {
        throw new Error('Invalid XML document')
    }

    return document
}

/**
 * XML lookup helpers shared by all capabilities parsers. They match by localName,
 * so the parsers are independent of the namespace prefix spellings of a document.
 */
export const getChild = (parent: Element | Document | undefined, localName: string): Element | undefined => {
  if (!parent) return undefined
  return Array.from(parent.childNodes).find((node): node is Element => {
    return node.nodeType === Node.ELEMENT_NODE && (node as Element).localName === localName
  })
}

export const getChildren = (parent: Element | Document | undefined, localName: string): Element[] => {
  if (!parent) return []
  return Array.from(parent.childNodes).filter((node): node is Element => {
    return node.nodeType === Node.ELEMENT_NODE && (node as Element).localName === localName
  })
}

export const getDescendantByPath = (parent: Element | Document | undefined, path: string[]): Element | undefined => {
  let node: Element | Document | undefined = parent
  for (const name of path) {
    if (!node) return undefined
    node = getChild(node, name)
  }
  return node instanceof Element ? node : undefined
}

export const getText = (parent: Element | Document | undefined, ...path: string[]): string | undefined => {
  const node = getDescendantByPath(parent, path)
  return node?.textContent?.trim() || undefined
}

export const getAttribute = (element: Element | undefined, ...names: string[]): string | undefined => {
  if (!element) return undefined
  for (const name of names) {
    const value = element.getAttribute(name)
    if (value !== null) return value
  }
  return undefined
}
