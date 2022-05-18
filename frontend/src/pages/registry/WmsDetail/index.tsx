import type { TreeNode } from "@/components/RessourceDetails/OgcServiceDetails";
import OgcServiceDetails from "@/components/RessourceDetails/OgcServiceDetails";
import type { JsonApiDocument, JsonApiPrimaryData } from "@/utils/jsonapi";
import { getIncludesByType } from "@/utils/jsonapi";
import type { ParamsArray } from "openapi-client-axios";
import type { ReactElement } from "react";

const getDescendants = (nodes: JsonApiPrimaryData[], currentNode: JsonApiPrimaryData) => {
    return nodes?.filter(
        (node: JsonApiPrimaryData) => node?.attributes?.lft > currentNode?.attributes?.lft && node?.attributes?.rght < currentNode?.attributes?.rght
    );
};

const getChildren = (nodes: JsonApiPrimaryData[], currentNode: JsonApiPrimaryData) => {
    return getDescendants(nodes, currentNode).filter(
        (node: JsonApiPrimaryData) => node?.attributes?.level === currentNode?.attributes.level + 1
    );
};

const mapTreeData = (nodes: JsonApiPrimaryData[], currentNode: JsonApiPrimaryData): TreeNode => {
    const children = getChildren(nodes, currentNode);
    if (children.length === 0){
        return {
            key: currentNode.id, 
            title: currentNode.attributes.stringRepresentation, 
            raw: currentNode,
            isLeaf: true,
        }
    } else {
        const childNodes: TreeNode[] = [];
        children.forEach((child: JsonApiPrimaryData) => {
            childNodes.push(
                mapTreeData(nodes, child)
            );
        });
        return {
            key: currentNode.id, 
            title: currentNode.attributes.stringRepresentation, 
            raw: currentNode,
            isLeaf: false,
            children: childNodes,
            rawDescendants: getDescendants(nodes, currentNode)
        }
    }
};

const transformTreeData = (wms: JsonApiDocument): TreeNode[] => {
    const treeOrderedLayers = 
        getIncludesByType(wms, 'Layer')
        .sort((a: JsonApiPrimaryData, b: JsonApiPrimaryData) => a.attributes.lft - b.attributes.lft);
    const rootNode = treeOrderedLayers[0];
    const children = getDescendants(treeOrderedLayers, rootNode);
    return [mapTreeData(children, rootNode)];
};

const transformFlatNodeList = (wms: JsonApiDocument): JsonApiPrimaryData[] => {
    return getIncludesByType(wms, 'Layer').sort((a: JsonApiPrimaryData, b: JsonApiPrimaryData) => a.attributes.lft - b.attributes.lft);
};

const WmsDetails = (): ReactElement => {


    /**
     * derived constants
     */
     const getWebMapServiceParams: ParamsArray = [
        {
            in: 'query',
            name: 'include',
            value: 'layers',
        },
        {
            in: 'query',
            name: 'fields[Layer]',
            value: 'string_representation,lft,rght,level,is_active,dataset_metadata'
        }
    ];


    return (
        <OgcServiceDetails
            resourceType='WebMapService'
            additionalGetRessourceParams={getWebMapServiceParams}
            nodeRessourceType={"Layer"}
            transformTreeData={transformTreeData}
            transformFlatNodeList={transformFlatNodeList}
        />
    );

};


export default WmsDetails;
