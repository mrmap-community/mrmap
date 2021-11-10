import { useContext, useEffect, useState } from "react";
import { Table, Card } from "antd";
import { OpenAPIContext } from "../../../Hooks/OpenAPIProvider";
import { ColumnFilterDropdown } from "./ColumnFilterDropdown";

export const ServiceList = () => {

    console.log("*** ServiceList");
    const [fetchState, setFetchState] = useState({
        loading: false,
        dataSource: [],
        total: 0
    });
    const [tableState, setTableState] = useState<any>({
        page: 1,
        pageSize: 1,
        ordering: undefined
    });
    const [columns] = useState([{
        title: 'ID',
        dataIndex: 'id',
        key: 'id',
        sorter: true,
        filterDropdown: <ColumnFilterDropdown />
    },
    {
        title: 'Title',
        dataIndex: 'title',
        key: 'title',
        sorter: true,
        filterDropdown: <ColumnFilterDropdown />
    },
    {
        title: 'Abstract',
        dataIndex: 'abstract',
        key: 'abstract',
        sorter: true,
        filterDropdown: <ColumnFilterDropdown />
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
                ordering: tableState.ordering
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
        setTableState({
            page: pagination.current,
            pageSize: pagination.pageSize,
            ordering: sorter ? ((sorter.order === 'descend' ? '-' : '') + sorter.field) : undefined
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
