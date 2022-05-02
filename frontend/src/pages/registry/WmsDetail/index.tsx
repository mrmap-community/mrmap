import type { JsonApiDocument, JsonApiPrimaryData } from '@/utils/jsonapi';
import { PageContainer } from '@ant-design/pro-layout';
import { Tree } from 'antd';
import type { ReactElement } from 'react';
import { useEffect, useState } from 'react';
import { useOperationMethod } from 'react-openapi-client/useOperationMethod';
import { useParams } from 'react-router';
const { DirectoryTree } = Tree;
interface Node {
    key: any;
    raw: JsonApiPrimaryData;
    title: string;
    children?: Node[] | undefined;
    isLeaf: boolean
}

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

const mapTreeData = (nodes: JsonApiPrimaryData[], currentNode: JsonApiPrimaryData): Node => {
    const childNodes = getChildren(nodes, currentNode);
    if (childNodes.length === 0){
        return {
            key: currentNode.id, 
            title: currentNode.attributes.stringRepresentation, 
            raw: currentNode,
            isLeaf: true
        }
    } else {
        const children: Node[] = [];
        childNodes.forEach((child: JsonApiPrimaryData) => {
            children.push(
                mapTreeData(nodes, child)
            );
        });
        return {
            key: currentNode.id, 
            title: currentNode.attributes.stringRepresentation, 
            raw: currentNode,
            isLeaf: false,
            children: children
        }
    }
};


const transformTreeData = (wms: JsonApiDocument): Node[] => {
    const treeOrderedLayers = wms.included
        .filter((item: JsonApiPrimaryData) => item.type === 'Layer')
        .sort((a: JsonApiPrimaryData, b: JsonApiPrimaryData) => a.attributes.lft - b.attributes.lft);
    const rootNode = treeOrderedLayers[0];
    const children = getDescendants(treeOrderedLayers, rootNode);
    return [mapTreeData(children, rootNode)];
};




const WmsDetails = (): ReactElement => {
    const { id } = useParams<{ id: string }>();
    const [
        getWebMapService, 
        { loading: getWMSLoading, response: getWMSResponse }
    ] = useOperationMethod('getWebMapService');
    const [ treeData, setTreeData] = useState<Node[]>();

    /**
     * @description Initial hook to receive the service
     */
    useEffect(() => {
        getWebMapService(
        [
            {
              in: 'path',
              name: 'id',
              value: String(id),
            },
            {
              in: 'query',
              name: 'include',
              value: 'layers',
            },
          ]);
    }, [getWebMapService, id]);

    /**
     * @description Transform jsonapi response to needed tree data
     */
    useEffect(() => {
        if (getWMSResponse) {
            const newTreeData = transformTreeData(getWMSResponse.data)
            setTreeData(newTreeData);
        }
    }, [getWMSResponse])

    return (
        <PageContainer>
            <DirectoryTree
                multiple
                defaultExpandAll
                // onSelect={onSelect}
                // onExpand={onExpand}
                treeData={treeData}
                />
        </PageContainer>
    );
};

export default WmsDetails;
