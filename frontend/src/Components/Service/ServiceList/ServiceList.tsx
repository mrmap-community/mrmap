import { createRef, useContext, useEffect, useState } from "react";
import { Table, Card, Input, Space, Button } from "antd";
import { OpenAPIContext } from "../../../Hooks/OpenAPIProvider";
import { SearchOutlined } from '@ant-design/icons';
import Highlighter from 'react-highlight-words';
import { Link } from "react-router-dom";

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

export const ServiceList = () => {

    const [loading, setLoading] = useState(false);
    const [data, setData] = useState({
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
    const [columnTypes, setColumnTypes] = useState<any>({});

    const { api } = useContext(OpenAPIContext);

    useEffect(() => {
        async function buildColumns() {
            const client = await api.getClient();
            const props = client.api.getOperation("List/api/v1/registry/wms/").responses[200].content["application/vnd.api+json"].schema.properties.data.items.properties.attributes.properties;
            const columns = [];
            for (const propName in props) {
                const prop = props[propName];
                const column: any = {
                    title: prop.title || propName,
                    dataIndex: propName,
                    key: propName
                };
                prop.isFlat = prop.type === 'string';
                if (prop.isFlat) {
                    column.sorter = true;
                    const columnSearchProps = { ...getColumnSearchProps(propName) };
                    Object.assign(column, columnSearchProps);
                }
                columns.push(column);
            }
            columns.push({
                title: 'Actions',
                key: 'actions',
                render: (text: any, record: any) => (
                    <Space size="middle">
                        <a>Delete</a>
                        <a>Edit</a>
                    </Space>
                )
            });
            setColumns(columns);
            setColumnTypes(props);
        }
        buildColumns();
    }, [api]);

    useEffect(() => {
        async function fetchTableData() {
            setLoading(true);
            const client = await api.getClient();
            const queryParams = {
                'page[number]': tableState.page,
                'page[size]': tableState.pageSize,
                ...tableState.filters
            };
            if (tableState.ordering && tableState.ordering !== 'undefined') {
                queryParams.sort = tableState.ordering;
            }
            const res = await client["List/api/v1/registry/wms/"](queryParams);
            const dataSource: any = [];
            res.data.data.forEach((result: any) => {
                result.attributes.id = result.id;
                dataSource.push(result.attributes);
            });
            // for (const columnName in columnTypes) {
            //     const columnType = columnTypes[columnName];
            //     if (!columnType.isFlat) {
            //         res.data.data.forEach((result: any) => {
            //             result[columnName] = '[complex value]';
            //         });
            //     }
            // }
            setData({
                dataSource: dataSource,
                total: res.data.meta.pagination.count
            });
            setLoading(false);
        }
        // TODO can this skip be avoided somehow -> necessary when columnTypes is not initialized yet
        if (columnTypes && Object.keys(columnTypes).length === 0 && Object.getPrototypeOf(columnTypes) === Object.prototype) {
            return;
        }
        fetchTableData();
    }, [tableState, api, columnTypes]);

    const handleTableChange = (pagination: any, filters: any, sorter: any) => {
        const filterParams: any = {};
        for (const prop in filters) {
            if (filters[prop] && filters[prop].length > 0) {
                filterParams[`filter[${prop}.icontains]`] = filters[prop][0];
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
        <Card title="Services" extra={<Link to="/registry/services/add">Add</Link>} style={{ width: '100%' }}>
            <Table
                dataSource={data.dataSource}
                rowKey={(record: any) => record.id}
                columns={columns}
                loading={loading}
                pagination={{
                    current: tableState.page,
                    pageSize: tableState.pageSize,
                    total: data.total,
                }}
                onChange={handleTableChange}
            />
        </Card>
    );
}
