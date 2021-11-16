import { createRef, useContext, useEffect, useState } from "react";
import { Table, Card, Input, Space, Button } from "antd";
import { OpenAPIContext } from "../../../Hooks/OpenAPIProvider";
import { SearchOutlined } from '@ant-design/icons';
import Highlighter from 'react-highlight-words';

export const ServiceList = () => {

    const getColumnSearchProps = (dataIndex: any): any => {
        const searchInput: any = createRef();
        let searchText = "";
        let searchedColumn: any = null;
        return {
            filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => {
                const handleSearch = (selectedKeys: any, confirm: any, dataIndex: any) => {
                    confirm();
                    searchText = selectedKeys[0];
                    searchedColumn = dataIndex;
                };
                const handleReset = (clearFilters: any) => {
                    clearFilters();
                    searchText = '';
                };
                return (<div style={{ padding: 8 }}>
                    <Input
                        ref={searchInput}
                        placeholder={`Search ${dataIndex}`}
                        value={selectedKeys[0]}
                        onChange={e => setSelectedKeys(e.target.value ? [e.target.value] : [])}
                        onPressEnter={() => handleSearch(selectedKeys, confirm, dataIndex)}
                        style={{ marginBottom: 8, display: 'block' }}
                    />
                    <Space>
                        <Button
                            type="primary"
                            onClick={() => handleSearch(selectedKeys, confirm, dataIndex)}
                            icon={<SearchOutlined />}
                            size="small"
                            style={{ width: 90 }}
                        >
                            Search
                        </Button>
                        <Button onClick={() => handleReset(clearFilters)} size="small" style={{ width: 90 }}>
                            Reset
                        </Button>
                        <Button
                            type="link"
                            size="small"
                            onClick={() => {
                                confirm({ closeDropdown: false });
                                searchText = selectedKeys[0];
                                searchedColumn = dataIndex;
                            }}
                        >
                            Filter
                        </Button>
                    </Space>
                </div>);
            },
            onFilterDropdownVisibleChange: (visible: any) => {
                if (visible) {
                    setTimeout(() => searchInput.current.select(), 100);
                }
            },
            filterIcon: (filtered: any) => <SearchOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
            render: (text: any) => {
                return searchedColumn === dataIndex ? (
                    <Highlighter
                        highlightStyle={{ backgroundColor: '#ffc069', padding: 0 }}
                        searchWords={[searchText]}
                        autoEscape
                        textToHighlight={text ? text.toString() : ''}
                    />
                ) : (
                    text
                )
            }
        }
    };

    const [fetchState, setFetchState] = useState({
        loading: false,
        dataSource: [],
        total: 0
    });
    const [tableState, setTableState] = useState<any>({
        page: 1,
        pageSize: 1,
        ordering: undefined,
        filters: undefined
    });
    const [columns, setColumns] = useState<any>([]);

    const { api } = useContext(OpenAPIContext);

    useEffect(() => {
        async function buildColumns() {
            const client = await api.getClient();
            const props = client.api.getOperation("v1_registry_service_services_list").responses[200].content["application/json"].schema.properties.results.items.properties;
            const columns = [];
            for (let propName in props) {
                const prop = props[propName];
                if (propName === 'keywords') {
                    // TODO why does keywords as dataIndex not work??
                    break;
                }
                columns.push({
                    title: prop.title || propName,
                    dataIndex: propName,
                    key: propName,
                    sorter: true,
                    ...getColumnSearchProps(propName)
                });

            }
            setColumns(columns);
        }
        buildColumns();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
        async function fetchTableData() {
            setFetchState({
                ...fetchState,
                loading: true
            });
            const client = await api.getClient();
            const res = await client.v1_registry_service_services_list({
                page: tableState.page,
                page_size: tableState.pageSize,
                ordering: tableState.ordering,
                ...tableState.filters
            });
            setFetchState({
                loading: false,
                dataSource: res.data.results,
                total: res.data.count
            });
        }
        fetchTableData();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [tableState, api]);

    function handleTableChange(pagination: any, filters: any, sorter: any) {
        const filterParams: any = {};
        for (const prop in filters) {
            if (filters[prop] && filters[prop].length > 0) {
                filterParams[prop + "__icontains"] = filters[prop][0];
            }
        }
        setTableState({
            page: pagination.current,
            pageSize: pagination.pageSize,
            ordering: sorter ? ((sorter.order === 'descend' ? '-' : '') + sorter.field) : undefined,
            filters: filterParams
        });
    };

    return (
        <div className="mrmap-mapcontext-list">
            <Card title="Services" style={{ width: '100%' }}>
                <Table
                    dataSource={fetchState.dataSource}
                    rowKey={(record: any) => record.id}
                    columns={columns}
                    loading={fetchState.loading}
                    pagination={{
                        current: tableState.page,
                        pageSize: tableState.pageSize,
                        total: fetchState.total,
                    }}
                    onChange={handleTableChange}
                />
            </Card>
        </div>
    );
}
