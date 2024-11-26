import fs from 'fs'
import path from 'path'
import { expect, test } from 'vitest'

import { parseWms } from '../parseCapabilities'
import { getDocument } from '../utils'

const xmlString = fs.readFileSync(path.resolve(__dirname,'./capabilitites_130.xml'), 'utf-8')

test('getDocument', () => {
    const doc = getDocument(xmlString)
    expect(doc).toBeDefined()
})


test('parseWms', () => {
    const wms = parseWms(xmlString)
    // expect(wms).toStrictEqual({
    //     version: '1.3.0'
    // })
})

