import SchemaForm from '@/components/SchemaForm';
import SchemaTable from '@/components/SchemaTable';
import type { JsonApiDocument, JsonApiPrimaryData } from '@/utils/jsonapi';
import { buildJsonApiPayload, getIncludesByType } from '@/utils/jsonapi';
import { CheckOutlined, CloseOutlined, EditFilled, LinkOutlined } from '@ant-design/icons';
import { PageContainer } from '@ant-design/pro-layout';
import { Badge, Button, Collapse, Drawer, Select, Space, Switch, Tooltip } from 'antd';
import type { DefaultOptionType } from 'antd/lib/select';
import type { ReactElement, ReactNode } from 'react';
import { useEffect, useState } from 'react';
import { useOperationMethod } from 'react-openapi-client/useOperationMethod';
import { useParams } from 'react-router';

const { Panel } = Collapse;

interface Node {
    key: any;
    raw: JsonApiPrimaryData;
    title: string;
    children?: Node[] | undefined;
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
        { loading: getWMSLoading, response: getWMSResponse }
    ] = useOperationMethod('getWebMapService');
    const [
        updateLayer,
        { loading: updateLayerLoading, response: updateLayerResponse}
    ] = useOperationMethod('updateLayer');
    const [ treeData, setTreeData ] = useState<Node[]>();

    const [ searchOptions, setSearchOptions ] = useState<DefaultOptionType[]>([]);
    const [ selectedSearchKey, setSelectedSearchKey ] = useState();

    const [ selectedForEdit, setSelectedForEdit ] = useState<JsonApiPrimaryData>();
    const [ rightDrawerVisible, setRightDrawerVisible ] = useState<boolean>(false);

    const [ selectedForDataset, setSelectedForDataset ] = useState<JsonApiPrimaryData>();
    const [ bottomDrawerVisible, setBottomDrawerVisible ] = useState<boolean>(false);

    const isLoading = getWMSLoading || updateLayerLoading;

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
    }, [updateLayerResponse]);

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


    const genExtra = (node: Node): ReactNode => {
        const isActive = node?.raw?.attributes?.isActive;
        const datasetMetadataCount = node?.raw?.relationships?.datasetMetadata?.meta?.count;
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
                        setSelectedForDataset(node.raw);
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
                                setSelectedForEdit(node.raw);
                            }
                        }
                        loading={isLoading}
                    />
                </Tooltip>
            </Space>
        );
    };
    
    const getCollapseableTree = (node: Node) => {
        if (node.children){
            return (
                <Collapse >
                    <Panel header={node.title} key={node.key} extra={genExtra(node)} >
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
                    <Panel header={node.title} key={node.key} extra={genExtra(node)} showArrow={!node.isLeaf} />
                </Collapse>
            )
        }
    };

    useEffect(() => {
        console.log('selectedForDataset', selectedForDataset);
    }, [selectedForDataset]);

    return (
        <PageContainer>
            
            <Select
                showSearch
                placeholder="Select a person"
                optionFilterProp="label"
                filterOption={
                    (input, option) => {
                        // TODO: label is a ReactNode...
                        return option?.label?.toLocaleLowerCase().includes(input.toLocaleLowerCase()) ? true: false;
                    }
                }
                onSelect={
                    (key)=>{
                        console.log(key);
                        setSelectedSearchKey(key);
                    }
                } 
                options={searchOptions}
            />

            {treeData ? getCollapseableTree(treeData[0]): undefined}

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

