import { useContext, useEffect, useState } from "react";
import { Table, Card } from "antd";
import { OpenAPIContext } from "../../../Hooks/OpenAPIProvider";
import { ColumnFilterDropdown } from "./ColumnFilterDropdown";
import { SearchOutlined } from '@ant-design/icons';
import Highlighter from 'react-highlight-words';

export const ServiceList = () => {

    console.log("*** ServiceList");

    const [searchInputFocused, setSearchInputFocused] = useState(false);
    const [searchText, setSearchText] = useState("");
    const [searchedColumn, setSearchedColumn] = useState("");

    const getColumnSearchProps = (dataIndex: any): any => {
        return {
            filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
                <ColumnFilterDropdown
                    setSelectedKeys={setSelectedKeys}
                    selectedKeys={selectedKeys}
                    confirm={confirm}
                    clearFilters={clearFilters}
                    dataIndex={dataIndex}
                    searchText={searchText}
                    setSearchText={setSearchText}
                    searchedColumn={searchedColumn}
                    setSearchedColumn={setSearchedColumn}
                    searchInputFocused={searchInputFocused} />),
            onFilterDropdownVisibleChange: (visible: any) => {
                console.log("*** setSearchInputFocused: " + visible);
                setSearchInputFocused(visible);
            },
            filterIcon: (filtered: any) => <SearchOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
            render: (text: any) => {
                console.log("**** render " + searchedColumn);
                // searchedColumn null ????
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
    const [columns] = useState([{
        title: 'ID',
        dataIndex: 'id',
        key: 'id',
        sorter: true,
        ...getColumnSearchProps('id')
    },
    {
        title: 'Title',
        dataIndex: 'title',
        key: 'title',
        sorter: true,
        ...getColumnSearchProps('title')
    },
    {
        title: 'Abstract',
        dataIndex: 'abstract',
        key: 'abstract',
        sorter: true,
        ...getColumnSearchProps('abstract')
    },]);

    const { api } = useContext(OpenAPIContext);

    useEffect(() => {
        console.log("*** fetching");
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
            <h1>SearchedColumn: {searchedColumn}</h1>
        </div>
    );
}
