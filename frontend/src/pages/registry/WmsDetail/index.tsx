import SchemaForm from '@/components/SchemaForm';
import SchemaTable from '@/components/SchemaTable';
import type { JsonApiDocument, JsonApiPrimaryData } from '@/utils/jsonapi';
import { buildJsonApiPayload, getIncludesByType } from '@/utils/jsonapi';
import { CheckOutlined, CloseOutlined, EditFilled, LinkOutlined } from '@ant-design/icons';
import { PageContainer } from '@ant-design/pro-layout';
import { Badge, Button, Card, Collapse, Drawer, Select, Space, Switch, Tooltip } from 'antd';
import type { DefaultOptionType } from 'antd/lib/select';
import type { ReactElement, ReactNode } from 'react';
import { useCallback, useEffect, useState } from 'react';
import { useOperationMethod } from 'react-openapi-client/useOperationMethod';
import { useParams } from 'react-router';

const { Panel } = Collapse;

interface Node {
    key: any;
    raw: JsonApiPrimaryData;
    title: string;
    children?: Node[] | undefined;
    rawDescendants?: JsonApiPrimaryData[] | undefined;
    isLeaf: boolean
};


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

const isDescendantOf = (descendants: JsonApiPrimaryData[], key: any): boolean => {
    return descendants.some((descendant: JsonApiPrimaryData) => {
        return descendant.id === key;
    })
};

const mapTreeData = (nodes: JsonApiPrimaryData[], currentNode: JsonApiPrimaryData): Node => {
    const children = getChildren(nodes, currentNode);
    if (children.length === 0){
        return {
            key: currentNode.id, 
            title: currentNode.attributes.stringRepresentation, 
            raw: currentNode,
            isLeaf: true,
        }
    } else {
        const childNodes: Node[] = [];
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


const transformTreeData = (wms: JsonApiDocument): Node[] => {
    const treeOrderedLayers = 
        getIncludesByType(wms, 'Layer')
        .sort((a: JsonApiPrimaryData, b: JsonApiPrimaryData) => a.attributes.lft - b.attributes.lft);
    const rootNode = treeOrderedLayers[0];
    const children = getDescendants(treeOrderedLayers, rootNode);
    return [mapTreeData(children, rootNode)];
};

const WmsDetails = (): ReactElement => {
    const { id } = useParams<{ id: string }>();
    const [
        getWebMapService, 
        { loading: getWMSLoading, response: getWMSResponse, error: getWMSError }
    ] = useOperationMethod('getWebMapService');
    const wms: JsonApiPrimaryData = getWMSResponse?.data?.data;
    const [
        updateLayer,
        { loading: updateLayerLoading, response: updateLayerResponse}
    ] = useOperationMethod('updateLayer');
    const [
        updateWms,
        { loading: updateWmsLoading, response: updateWmsResponse}
    ] = useOperationMethod('updateWebMapService');

    const [ treeData, setTreeData ] = useState<Node[]>();

    const [ searchOptions, setSearchOptions ] = useState<DefaultOptionType[]>([]);
    const [ selectedSearchKey, setSelectedSearchKey ] = useState<string>();

    const [ selectedForEdit, setSelectedForEdit ] = useState<JsonApiPrimaryData>();
    const [ rightDrawerVisible, setRightDrawerVisible ] = useState<boolean>(false);

    const [ selectedForDataset, setSelectedForDataset ] = useState<JsonApiPrimaryData>();
    const [ bottomDrawerVisible, setBottomDrawerVisible ] = useState<boolean>(false);

    const isLoading = getWMSLoading || updateLayerLoading || updateWmsLoading;

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
            value: 'string_representation,lft,rght,level,is_active,dataset_metadata'
        }
    ];
    
    /**
     * @description Initial hook to receive the service
     */
    useEffect(() => {
        if (!getWMSLoading){
            getWebMapService(getWebMapServiceParams);
        }
    }, [updateLayerResponse, updateWmsResponse]);

    /**
     * @description Transform jsonapi response to needed tree data
     */
    useEffect(() => {
        if (getWMSResponse?.data) {
            const newTreeData = transformTreeData(getWMSResponse.data)
            setTreeData(newTreeData);
            
            const newSearchOptions = getIncludesByType(getWMSResponse.data, 'Layer').map((node: JsonApiPrimaryData) => {
                return {
                    value: node.id,
                    label: node.attributes.stringRepresentation
                }
            })
            setSearchOptions(newSearchOptions);
        }
    }, [getWMSResponse]);


    const genExtra = useCallback((resource: JsonApiPrimaryData): ReactNode => {
        const isActive = resource?.attributes?.isActive;
        const datasetMetadataCount = resource?.relationships?.datasetMetadata?.meta?.count;
        const datasetMetadataButton = (
            <Badge 
                count={datasetMetadataCount}
                size={'small'}>
                <Button
                    size='small'
                    icon={<LinkOutlined />}
                    loading={isLoading}
                    onClick={(event) => {
                        event.stopPropagation();
                        setSelectedForDataset(resource);
                        setBottomDrawerVisible(true);
                    }}
                />
            </Badge>
        );
        return (
            <Space size="small">
                {datasetMetadataCount > 0 ? datasetMetadataButton: <></>}
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
                                let func = updateLayer;
                                if (resource.type === 'WebMapService'){
                                    func = updateWms;
                                }
                                func(
                                    [{
                                        in: 'path',
                                        name: 'id',
                                        value: String(resource.id),
                                    }], 
                                    buildJsonApiPayload(resource.type, resource.id, {isActive: checked })
                                )
                            }
                        }
                        loading={isLoading}
                    />
                </Tooltip>
                <Tooltip
                title='edit metadata'
                >
                    <Button
                        size='small'
                        icon={<EditFilled />}
                        style={{ borderColor: 'gold', color: 'gold' }}
                        onClick={
                            (event) => {
                                event.stopPropagation();
                                setRightDrawerVisible(true);
                                setSelectedForEdit(resource);
                            }
                        }
                        loading={isLoading}
                    />
                </Tooltip>
            </Space>
        );
    }, [isLoading, updateLayer]);
    
    const getCollapseableTree = useCallback((node: Node) => {
        if (node.children){

            const showDescendants = selectedSearchKey && node.rawDescendants ? isDescendantOf([node.raw].concat(node.rawDescendants), selectedSearchKey): false;
            
            return (
                <Collapse
                    defaultActiveKey={showDescendants ? node.key: undefined}
                    key={node.key}
                >
                    <Panel header={node.title} key={node.key} extra={genExtra(node.raw)}>
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
                <Collapse key={node.key}>
                    <Panel header={<Badge status='processing' count='0'>{node.title}</Badge>} key={node.key} extra={genExtra(node.raw)} showArrow={!node.isLeaf} />
                </Collapse>
            )
        }
    }, [genExtra, selectedSearchKey]);

    return (
        <PageContainer>
            <Card 
                title={wms?.attributes?.stringRepresentation}
                extra={
                    <>
                    <Select
                        showSearch
                        placeholder="Search Layer"
                        optionFilterProp="label"
                        filterOption={
                            (input, option) => {
                                // TODO: label is a ReactNode...
                                return option?.label?.toLocaleLowerCase().includes(input.toLocaleLowerCase()) ? true: false;
                            }
                        }
                        onSelect={
                            (key: string)=>{
                                setSelectedSearchKey(key);
                            }
                        } 
                        options={searchOptions}
                    />
                    {wms ? genExtra(wms): undefined}
                    </>
                }
                loading={!getWMSResponse}

            >
                {treeData ? getCollapseableTree(treeData[0]): undefined}
            </Card>
            
            <Drawer
                title={`edit ${selectedForEdit?.attributes.stringRepresentation}`}
                placement="right"
                visible={rightDrawerVisible}
                onClose={() => { setRightDrawerVisible(false);}}
                destroyOnClose={true}
            >
                <SchemaForm
                    resourceType={selectedForEdit?.type || 'Layer'}
                    resourceId={selectedForEdit?.id}
                    onSuccess={() => {
                        setRightDrawerVisible(false);
                        getWebMapService(getWebMapServiceParams);
                    }}
                />
            </Drawer>
            <Drawer
                title={`linked dataset metadata records for ${selectedForDataset?.type}: ${selectedForDataset?.attributes.stringRepresentation}`}
                placement="bottom"
                visible={bottomDrawerVisible}
                onClose={() => {setBottomDrawerVisible(false);}}
                destroyOnClose={true}
                
            >
                <SchemaTable
                    resourceTypes={{baseResourceType: "DatasetMetadata", nestedResource: selectedForDataset ? {type: selectedForDataset?.type, id: selectedForDataset?.id}: undefined }}
                />

            </Drawer>
        </PageContainer>
    );
};

export default WmsDetails;

