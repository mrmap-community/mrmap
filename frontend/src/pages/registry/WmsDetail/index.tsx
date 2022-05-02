import type { JsonApiDocument, JsonApiPrimaryData } from '@/utils/jsonapi';
import { buildJsonApiPayload } from '@/utils/jsonapi';
import { CheckOutlined, CloseOutlined } from '@ant-design/icons';
import { PageContainer } from '@ant-design/pro-layout';
import { Collapse, Switch, Tooltip, Tree } from 'antd';
import type { ReactElement, ReactNode } from 'react';
import { useEffect, useState } from 'react';
import { useOperationMethod } from 'react-openapi-client/useOperationMethod';
import { useParams } from 'react-router';

const { Panel } = Collapse;

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
    const [
        updateLayer,
        { loading: updateLayerLoading, response: updateLayerResponse}
    ] = useOperationMethod('updateLayer');
    const [ treeData, setTreeData] = useState<Node[]>();

    const getWebMapServiceParams = [
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
        {
            in: 'query',
            name: 'fields[Layer]',
            value: 'string_representation,lft,rght,level,is_active'
        }
    ];
    
    /**
     * @description Initial hook to receive the service
     */
    useEffect(() => {
        if (!getWMSLoading){
            getWebMapService(getWebMapServiceParams);
        }
    }, [updateLayerResponse]);

    /**
     * @description Transform jsonapi response to needed tree data
     */
    useEffect(() => {
        if (getWMSResponse) {
            const newTreeData = transformTreeData(getWMSResponse.data)
            setTreeData(newTreeData);
        }
    }, [getWMSResponse]);


    const genExtra = (node: Node): ReactNode => {
        const isActive = node?.raw?.attributes?.isActive;
        return (
            <>
                <Tooltip
                title={
                    isActive
                    ? 'deactivate'
                    : 'activate'
                }
                >
                    <Switch
                        checkedChildren={<CheckOutlined />}
                        unCheckedChildren={<CloseOutlined />}
                        defaultChecked={isActive}
                        onClick={
                            (checked, event) => {
                                // If you don't want click extra trigger collapse, you can prevent this:
                                event.stopPropagation();
                                updateLayer(
                                    [{
                                        in: 'path',
                                        name: 'id',
                                        value: String(node.key),
                                    }], 
                                    buildJsonApiPayload(node.raw.type, node.key, {isActive: checked })
                                )
                            }
                        }
                        loading={getWMSLoading || updateLayerLoading}
                        
                        
                    />
                </Tooltip>
            </>
        );
    };
    
    const getCollapseableTree = (node: Node) => {
        if (node.children){
            return (
                <Collapse >
                    <Panel header={node.title} key={node.key} extra={genExtra(node)}>
                    {
                        node.children.map(
                            (child: Node) => {
                                return (getCollapseableTree(child))
                            }
                        )
                    }
                    </Panel>
                </Collapse>
            );
        } else {
            return (
                <Collapse >
                    <Panel header={node.title} key={node.key} extra={genExtra(node)}/>
                </Collapse>
            )
        }
    };

    return (
        <PageContainer>
            {/* <DirectoryTree
                multiple
                defaultExpandAll
                // onSelect={onSelect}
                // onExpand={onExpand}
                treeData={treeData}
                /> */}
            
            {treeData ? getCollapseableTree(treeData[0]): undefined}
            
        </PageContainer>
    );
};

export default WmsDetails;
