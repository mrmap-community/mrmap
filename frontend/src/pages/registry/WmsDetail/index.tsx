import SchemaForm from '@/components/SchemaForm';
import SchemaTable from '@/components/SchemaTable';
import type { JsonApiDocument, JsonApiPrimaryData } from '@/utils/jsonapi';
import { buildJsonApiPayload, getIncludesByType } from '@/utils/jsonapi';
import { CheckOutlined, CloseOutlined, EditFilled, LinkOutlined, SearchOutlined } from '@ant-design/icons';
import { PageContainer } from '@ant-design/pro-layout';
import { Badge, Button, Collapse, Drawer, Select, Space, Switch, Tooltip, Typography } from 'antd';
import type { DefaultOptionType } from 'antd/lib/select';
import type { AxiosError, ParamsArray } from 'openapi-client-axios';
import type { ReactElement, ReactNode } from 'react';
import { useCallback, useEffect, useState } from 'react';
import { useOperationMethod } from 'react-openapi-client/useOperationMethod';
import { useParams } from 'react-router';
import { history } from 'umi';

const { Text } = Typography;
const { Panel } = Collapse;

interface Node {
    key: any;
    raw: JsonApiPrimaryData;
    title: string;
    children?: Node[] | undefined;
    rawDescendants?: JsonApiPrimaryData[] | undefined;
    isLeaf: boolean
}

interface NodeOptionType extends DefaultOptionType {
    label: string;
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
    /**
     * page hooks
     */
    const { id } = useParams<{ id: string }>();
    const [ treeData, setTreeData ] = useState<Node[]>();
    const [ collapseableTree, setCollapseableTree ] = useState<ReactElement>();
    const [ searchOptions, setSearchOptions ] = useState<NodeOptionType[]>([]);
    const [ selectedSearchKey, setSelectedSearchKey ] = useState<string>();
    const [ selectedForEdit, setSelectedForEdit ] = useState<JsonApiPrimaryData>();
    const [ rightDrawerVisible, setRightDrawerVisible ] = useState<boolean>(false);
    const [ selectedForDataset, setSelectedForDataset ] = useState<JsonApiPrimaryData>();
    const [ bottomDrawerVisible, setBottomDrawerVisible ] = useState<boolean>(false);

    /**
     * Api hooks
     */
    const [
        getWebMapService, 
        { loading: getWMSLoading, response: getWMSResponse, error: getWMSError }
    ] = useOperationMethod('getWebMapService');    
    const [
        updateLayer,
        { loading: updateLayerLoading, response: updateLayerResponse}
    ] = useOperationMethod('updateLayer');
    const [
        updateWms,
        { loading: updateWmsLoading, response: updateWmsResponse}
    ] = useOperationMethod('updateWebMapService');

    /**
     * derived constants
     */
    const getWMSAxiosError = getWMSError as AxiosError;
    const wms: JsonApiPrimaryData = getWMSResponse?.data?.data;
    const isLoading: boolean = getWMSLoading || updateLayerLoading || updateWmsLoading;
    const getWebMapServiceParams: ParamsArray = [
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
     * @description Generate extra ui components like edit button for given json:api resource
     */
         const genExtra = useCallback((resource: JsonApiPrimaryData): ReactNode => {
            if (!resource){
                return <></>
            }
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
                <Space size="small" key={`space-${resource.id}`}>
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
                            key={`activate-switch-${resource.id}`}
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
                            key={`edit-btn-${resource.id}`}
                        />
                    </Tooltip>
                </Space>
            );
        }, [isLoading, updateLayer, updateWms]);
        
        /**
         * @description Generate nested Collapse components from given node
         */
        const getCollapseableTree = useCallback((node: Node) => {
            const title = selectedSearchKey === node.key ? <Text strong={true}><SearchOutlined /> {node.title}</Text> : node.title;
    
            if (node.children){
    
                const showDescendants = selectedSearchKey && node.rawDescendants ? isDescendantOf([node.raw].concat(node.rawDescendants), selectedSearchKey): false;
                return (
                    <Collapse
                        defaultActiveKey={showDescendants ? node.key: undefined}
                        key={node.key}
                        
                    >
                        <Panel header={title} key={node.key} extra={genExtra(node.raw)}>
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
                        <Panel header={title} key={node.key} extra={genExtra(node.raw)} showArrow={!node.isLeaf} />
                    </Collapse>
                )
            }
        }, [genExtra, selectedSearchKey]);
    
    /**
     * @description hook to receive the service on initial or any update layer or wms object
     */
    useEffect(() => {
        if (!getWMSLoading){
            getWebMapService(getWebMapServiceParams);
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [updateLayerResponse, updateWmsResponse]);

    /**
     * @description Transform jsonapi response to needed tree data and provide search options
     */
    useEffect(() => {
        if (getWMSAxiosError?.response?.status === 404){
            history.push('/404');
        }
        if (getWMSResponse?.data) {
            setTreeData(transformTreeData(getWMSResponse.data));
            
            const newSearchOptions: NodeOptionType[] = getIncludesByType(getWMSResponse.data, 'Layer').map((node: JsonApiPrimaryData) => {
                return {
                    value: node.id,
                    label: node.attributes.stringRepresentation
                }
            })
            setSearchOptions(newSearchOptions);
        }
    }, [getWMSResponse, getWMSAxiosError]);

    /**
     * @description Call getCollapseableTree on treeData or selectedSearchKey changed to rerender Collapse tree
     */
    useEffect(() => {
        if (treeData){
            setCollapseableTree(getCollapseableTree(treeData[0]));
        }
    }, [getCollapseableTree, treeData, selectedSearchKey]);

    return (
        <PageContainer
            header={
                {
                    title: `Details of ${wms?.attributes?.stringRepresentation}`,
                    extra: [
                            <Select
                                allowClear={true}
                                showSearch={true}
                                style={{ width: '100%'}}
                                dropdownMatchSelectWidth={false}
                                placeholder="Search Layer"
                                optionFilterProp="label"
                                filterOption={
                                    (input, option) => {
                                        return option?.label?.toLocaleLowerCase().includes(input.toLocaleLowerCase()) ? true: false;
                                    }
                                }
                                onSelect={
                                    (key: string)=>{
                                        setCollapseableTree(undefined);
                                        setSelectedSearchKey(key);
                                    }
                                } 
                                onDeselect={()=>{
                                    setCollapseableTree(undefined);
                                    setSelectedSearchKey('');
                                }}
                                options={searchOptions}
                                key={'layer-search-select'}
                            />,
                            <Space key={'service-extras'}>{genExtra(wms)}</Space>
                    ]
                }

            }
            loading={!getWMSResponse || !collapseableTree}
            
        > 
            {collapseableTree}   
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
                size={'large'}
            >
                <SchemaTable
                    resourceTypes={{baseResourceType: "DatasetMetadata", nestedResource: selectedForDataset ? {type: selectedForDataset?.type, id: selectedForDataset?.id}: undefined }}
                />

            </Drawer>
        </PageContainer>
    );
};

export default WmsDetails;

