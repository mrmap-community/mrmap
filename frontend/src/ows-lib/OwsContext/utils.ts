import { v4 as uuidv4 } from 'uuid';

import { WmsCapabilitites, WmsLayer } from "../XMLParser/types";
import { OWSResource } from './core';
import { OWSResource as IOWSResource, OWSContext, StyleSet, Operation, Offering } from "./types";
import { ensureCoreProfile, isWmsOfferingCode, WMS_OFFERING_CODE } from "./validation";

export const OWSContextDocument = (
    id: string = `urn:uuid:${uuidv4()}`,
    language: string = 'en',
    title: string = 'mrmap ows context',
    features: IOWSResource[] = []
): OWSContext => {

    return {
        id: id,
        type: "FeatureCollection",
        properties: ensureCoreProfile({
            lang: language,
            title: title,
            updated: new Date().toISOString()
        }),
        features: features,
    }
}

export const updateOrAppendSearchParam = (params: URLSearchParams, key: string, value: string) => {
    if (params.has(key)) {
        params.set(key, value)
    }
    else if (params.has(key.toUpperCase())) {
        params.set(key.toUpperCase(), value)
    } else if (params.has(key.toLowerCase())) {
        params.set(key.toLowerCase(), value)
    } else {
        params.append(key, value)
    }
}

export const prepareGetCapabilititesUrl = (href: string, serviceType: string, version?: string): URL => {
    const url = new URL(href)
    const params = url.searchParams
    updateOrAppendSearchParam(params, 'SERVICE', serviceType)
    updateOrAppendSearchParam(params, 'REQUEST', 'GetCapabilities')
    version && updateOrAppendSearchParam(params, 'VERSION', version)
    return url
}

export const prepareGetMapUrl = (
    capabilities: WmsCapabilitites,
    layerName: string
): URL => {
    const url = new URL(capabilities.operationUrls.getMap.get)
    const params = url.searchParams
    updateOrAppendSearchParam(params, 'SERVICE', 'WMS')
    updateOrAppendSearchParam(params, 'VERSION', capabilities.version)
    updateOrAppendSearchParam(params, 'REQUEST', 'GetMap') // TODO: version dependend
    updateOrAppendSearchParam(params, 'FORMAT', 'image/png') // TODO: should be configureable
    updateOrAppendSearchParam(params, 'LAYERS', layerName)
    updateOrAppendSearchParam(params, 'TRANSPARENT', 'true')

    return url
}

export const prepareGetFeatureInfoUrl = (
    capabilities: WmsCapabilitites,
    layerName: string
): URL | undefined => {
    const operation = capabilities.operationUrls.getFeatureInfo
    if (operation === undefined) return undefined

    const url = new URL(operation.get)
    const params = url.searchParams
    updateOrAppendSearchParam(params, 'SERVICE', 'WMS')
    updateOrAppendSearchParam(params, 'VERSION', capabilities.version)
    updateOrAppendSearchParam(params, 'REQUEST', 'GetFeatureInfo')
    // include the layer identifiers so callers only need to add pixel coords and INFO_FORMAT
    updateOrAppendSearchParam(params, 'LAYERS', layerName)
    updateOrAppendSearchParam(params, 'QUERY_LAYERS', layerName)
    // default info format can be overridden by the caller
    updateOrAppendSearchParam(params, 'INFO_FORMAT', 'text/html')

    return url
}

export const layerToFeature = (getCapabilitiesHref: string, capabilities: WmsCapabilitites, node: WmsLayer, folder: string): OWSResource => {
    // a layer without a name is a grouping layer of the capabilities tree and cannot be addressed by
    // GetMap, only its named children can
    const layerName = node.metadata.name?.trim() ?? ''
    const isRenderable = layerName.length > 0
    const getMapUrl = isRenderable ? prepareGetMapUrl(capabilities, layerName) : undefined
    const getFeatureInfoUrl = isRenderable ? prepareGetFeatureInfoUrl(capabilities, layerName) : undefined

    return OWSResource.fromPlainObject({
        type: "Feature",
        bbox: node.bbox,
        properties: {
            title: node.metadata.title,
            updated: new Date().toISOString(),
            offerings: [{
                code: WMS_OFFERING_CODE,
                operations: [
                    {
                        code: "GetCapabilities",
                        href: getCapabilitiesHref,
                        method: "GET",
                        type: "application/xml"
                    },
                    ...(getMapUrl ? [{
                        code: "GetMap",
                        href: getMapUrl.toString(),
                        method: "GET",
                        type: "image/png"
                    }] : []),
                    ...(getFeatureInfoUrl && node.isQueryable ? [{
                        code: "GetFeatureInfo",
                        href: getFeatureInfoUrl.toString(),
                        method: "GET",
                        type: "text/html"
                    }] : []),
                ],
                ...(node.styles && node.styles.length > 0 && {
                    styles: node.styles.map((style): StyleSet => {
                        return {
                            name: style.metadata.name,
                            title: style.metadata.title,
                            abstract: style.metadata.abstract,
                            legendURL: style.legendUrl?.href.toString()
                        }
                    })
                }),
            }],
            ...(node.minScaleDenominator !== undefined && { minscaledenominator: node.minScaleDenominator }),
            ...(node.maxScaleDenominator !== undefined && { maxscaledenominator: node.maxScaleDenominator }),
            folder: folder
        }
    })
}


export const deflatLayerTree = (
    getCapabilitiesHref: string,
    features: OWSResource[],
    capabilities: WmsCapabilitites,
    parentFolder: string,
    currentIndex: number,
    node?: WmsLayer,
): OWSResource[] => {

    const _node: WmsLayer = node ?? capabilities.rootLayer

    const folder = `${parentFolder}/${currentIndex}`
    features.push(layerToFeature(getCapabilitiesHref, capabilities, _node, folder))

    // iterate children if they exists
    _node.children?.forEach((subnode, index) => {
        subnode !== undefined && deflatLayerTree(getCapabilitiesHref, features, capabilities, folder, index, subnode)
    })

    return features
}

export const wmsToOWSResources = (href: string, capabilities: WmsCapabilitites, treeId: number = 0): OWSResource[] => {
    return deflatLayerTree(
        href,
        [],
        capabilities,
        '',
        treeId
    )
}

export const treeToList = (node: OWSResource) => {
    const flatNodes = [node]
    node.children?.forEach(child => flatNodes.push(...treeToList(child)))
    return flatNodes
}

export const isOperationUrlEqual = (url1: URL, url2: URL): boolean => {
    if (url1 === undefined || url2 === undefined) return false
    return (url1.origin === url2.origin) &&
        (url1.pathname === url2.pathname) &&
        ((url1.searchParams.get('SERVICE') ?? url1.searchParams.get('service')) === (url2.searchParams.get('SERVICE') ?? url2.searchParams.get('service'))) &&
        ((url1.searchParams.get('VERSION') ?? url1.searchParams.get('version')) === (url2.searchParams.get('VERSION') ?? url2.searchParams.get('version')))
}

// WMS names are case-insensitive; preserve vendor key casing for routing and tokens.
const WMS_PARAMETER_NAMES = new Set([
    'SERVICE', 'VERSION', 'REQUEST', 'LAYERS', 'QUERY_LAYERS', 'STYLES', 'CRS', 'SRS',
    'BBOX', 'WIDTH', 'HEIGHT', 'FORMAT', 'TRANSPARENT', 'BGCOLOR', 'EXCEPTIONS',
    'TIME', 'ELEVATION', 'SLD', 'SLD_BODY', 'INFO_FORMAT', 'FEATURE_COUNT', 'I', 'J', 'X', 'Y',
]);
// Only these positional parameters are combined. All other request values must match.
const WMS_BATCH_PARAMETERS = new Set(['LAYERS', 'QUERY_LAYERS', 'STYLES']);

const getWmsParameters = (url: URL) => {
    const parameters = new Map<string, { key: string, value: string }>();
    for (const [key, value] of url.searchParams) {
        const name = WMS_PARAMETER_NAMES.has(key.toUpperCase()) ? key.toUpperCase() : key;
        // Duplicate keys have server-dependent semantics, so do not batch them.
        if (parameters.has(name)) return undefined;
        parameters.set(name, { key, value });
    }
    return parameters;
};

const getWmsLayerStyles = (parameters: NonNullable<ReturnType<typeof getWmsParameters>>) => {
    const layers = parameters.get('LAYERS')?.value.split(',');
    if (!layers?.length || layers.some(layer => layer === '')) return undefined;
    const styles = parameters.get('STYLES')?.value;
    if (!styles) return layers.map(() => '');
    const values = styles.split(',');
    return values.length === layers.length ? values : undefined;
};

/** Read positional styles without rewriting imported operation URLs. */
export const getWmsOperationStyles = (operation?: Operation) => {
    if (!operation) return [];
    const parameters = getWmsParameters(new URL(operation.href));
    if (!parameters) return [];
    // Older contexts only describe the queried layers; the viewer uses these as map layers too.
    if (operation.code === 'GetFeatureInfo' && !parameters.has('LAYERS') && parameters.has('QUERY_LAYERS')) {
        parameters.set('LAYERS', { key: 'LAYERS', value: parameters.get('QUERY_LAYERS')!.value });
    }
    const styles = getWmsLayerStyles(parameters);
    return styles?.map((style, index) => ({
        layer: parameters.get('LAYERS')!.value.split(',')[index], style,
    })) ?? [];
};

/** Change only this layer's style, preserving independent operation activation and query subsets. */
export const setWmsLayerStyle = (offering: Offering, layer: string, style: string) => {
    if (style !== '' && !offering.styles?.some(item => item.name === style)) return;
    offering.operations?.filter(operation => ['GetMap', 'GetFeatureInfo'].includes(operation.code)).forEach(operation => {
        const values = getWmsOperationStyles(operation);
        if (!values.some(value => value.layer === layer)) return;
        const url = new URL(operation.href);
        const parameters = getWmsParameters(url)!;
        url.searchParams.set(parameters.get('STYLES')?.key ?? 'STYLES',
            values.map(value => value.layer === layer ? style : value.style).join(','));
        operation.href = url.href;
    });
};

export const areWmsOperationsCompatible = (first: Operation, second: Operation): boolean => {
    if (!['GetMap', 'GetFeatureInfo'].includes(first.code) || first.code !== second.code ||
        first.method.toUpperCase() !== second.method.toUpperCase() || first.type !== second.type ||
        first['x-authentication-id'] !== second['x-authentication-id']) return false;

    const firstUrl = new URL(first.href);
    const secondUrl = new URL(second.href);
    if (firstUrl.origin !== secondUrl.origin || firstUrl.pathname !== secondUrl.pathname ||
        firstUrl.username !== secondUrl.username || firstUrl.password !== secondUrl.password ||
        firstUrl.hash !== secondUrl.hash) return false;

    const firstParams = getWmsParameters(firstUrl);
    const secondParams = getWmsParameters(secondUrl);
    if (!firstParams || !secondParams || !getWmsLayerStyles(firstParams) || !getWmsLayerStyles(secondParams)) return false;
    if (first.code === 'GetFeatureInfo' &&
        (!firstParams.get('QUERY_LAYERS')?.value || !secondParams.get('QUERY_LAYERS')?.value)) return false;
    // These can bind filters or styling to individual layers. Equal text is insufficient to
    // establish that it still means the same thing after adding layers to the request.
    if ([...firstParams.keys(), ...secondParams.keys()].some(key =>
        ['CQL_FILTER', 'FILTER', 'SLD', 'SLD_BODY'].includes(key.toUpperCase()))) return false;

    const combined = first.code === 'GetFeatureInfo' ? WMS_BATCH_PARAMETERS : new Set(['LAYERS', 'STYLES']);
    const names = new Set([...firstParams.keys(), ...secondParams.keys()]);
    return [...names].every(name => combined.has(name) ||
        (firstParams.has(name) && secondParams.has(name) && firstParams.get(name)?.value === secondParams.get(name)?.value));
};

export const appendWmsOperationParameters = (target: URL, source: URL, code: string) => {
    const targetParams = getWmsParameters(target);
    const sourceParams = getWmsParameters(source);
    if (!targetParams || !sourceParams) return;
    const targetStyles = getWmsLayerStyles(targetParams);
    const sourceStyles = getWmsLayerStyles(sourceParams);
    if (!targetStyles || !sourceStyles) return;

    const names = code === 'GetFeatureInfo' ? ['LAYERS', 'QUERY_LAYERS'] : ['LAYERS'];
    for (const name of names) {
        const first = targetParams.get(name);
        const second = sourceParams.get(name);
        if (first && second) target.searchParams.set(first.key, `${first.value},${second.value}`);
    }
    if (targetParams.has('STYLES') || sourceParams.has('STYLES')) {
        target.searchParams.set(targetParams.get('STYLES')?.key ?? 'STYLES', [...targetStyles, ...sourceStyles].join(','));
    }
};

export const appendQueryParam = (param: string = "LAYERS", url1: URL, url2: URL) => {
    const paramLower = param.toLowerCase()
    const paramUpper = param.toUpperCase() 
    
    const layerIdentifiers1 = (url1.searchParams.get(paramUpper) ?? url1.searchParams.get(paramLower))?.split(',') ?? []
    const layerIdentifiers2 = (url2.searchParams.get(paramUpper) ?? url2.searchParams.get(paramLower))?.split(',') ?? []

    const newLayersParam = layerIdentifiers1?.concat(layerIdentifiers2)

    url1.searchParams.has(paramUpper) && url1.searchParams.set(paramUpper, newLayersParam?.join(','))
    url1.searchParams.has(paramLower) && url1.searchParams.set(paramLower, newLayersParam?.join(','))
}


export const getFeaturesByGetMapUrl = (url: URL, features: IOWSResource[]): IOWSResource[] => {   
    const layers = url.searchParams.get('LAYERS')?.split(',') ?? []
    return features.filter(feature => feature.properties.offerings?.find(offering =>
        isWmsOfferingCode(offering.code))?.operations?.find(operation => {
            const operationUrl = new URL(operation.href)
            const operationLayers = operationUrl.searchParams.get('LAYERS')?.split(',') ?? []
            return operation.code === 'GetMap' && 
                operation.method.toLowerCase() === 'get' && 
                isOperationUrlEqual(operationUrl, url) &&
                layers.some(layer => operationLayers.includes(layer))
        })
    )
}

export const isDescendant = (ancestor: IOWSResource, descendant: IOWSResource) => {
    const ancestorFolders = ancestor.properties.folder?.split('/') ?? []
    const descendantFolders = descendant.properties.folder?.split('/') ?? []
    return ancestorFolders.length < descendantFolders.length && ancestorFolders?.every((folder, index) => descendantFolders?.[index] === folder)
}

export const updateFolders = (
    tree: IOWSResource[],
    newRootPath: string = '',
    startIndex: number = 0) => {
    if (tree[0]?.properties.folder === undefined) return

    const newRootFolders = newRootPath.split('/')
    const oldRootFolders = tree[0].properties.folder.split('/')

    const subtreeDepthIndexes: Record<string, number> = { '0': startIndex }

    let lastDepth = 0

    tree.forEach((node) => {
        if (node.properties.folder === undefined) return

        const nodeFolders = node.properties.folder.split('/')
        const currentDepth = nodeFolders.length - oldRootFolders.length

        if (lastDepth > currentDepth) {
            // we climb up the tree. In that case the lastDepth index need to be reseted
            subtreeDepthIndexes[lastDepth.toString()] = 0
        }

        if (lastDepth < currentDepth) {
            // we climb down the tree. In that case the currentDepth index need to be reseted
            subtreeDepthIndexes[currentDepth.toString()] = 0
        }

        // initial with one empty string to get a leading / after joining
        const newNodeFolders = [...newRootFolders]

        // iterate over all depths and set correct index
        for (let depth = 0; depth <= currentDepth; depth++) {

            let index
            if (currentDepth === depth) {
                index = subtreeDepthIndexes[depth.toString()];
            } else {
                index = subtreeDepthIndexes[depth.toString()] - 1; // reduce by 1 cause the cache stores incremented values
            }
            newNodeFolders.push(index.toString())

        }
        subtreeDepthIndexes[currentDepth.toString()]++
        lastDepth = currentDepth
        node.properties.folder = newNodeFolders.join('/')
    })

}

export const getFeatureFolderIndex = (feature: IOWSResource) => {
    return Number(feature.properties.folder?.split('/').slice(-1)[0])
}

export const getParentFolder = (folder: string) => {
    if (folder?.split('/').length === 2) return // root node
    return folder?.split('/').slice(0, -1).join('/')
}
