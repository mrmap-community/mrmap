import { useContext, useEffect, useState } from "react";
import { Table, Card} from "antd";
import { OpenAPIContext } from "../../../Hooks/OpenAPIProvider";

export const ServiceList = () => {

    console.log("*** ServiceList");

    // modified by data fetching
    const [backendState, setBackendState] = useState({
        loading: false,
        dataSource: [],
        total: 0
    });

    // modified by table interaction (page change, page size, sort order change, filter change)
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
    },
    {
        title: 'Title',
        dataIndex: 'title',
        key: 'title',
        sorter: true,
    },
    {
        title: 'Abstract',
        dataIndex: 'abstract',
        key: 'abstract',
        sorter: true
    },]);

    const { api } = useContext(OpenAPIContext);

    useEffect(() => {
        console.log("*** fetching");
        async function fetchTableData() {
            setBackendState({
                ...backendState,
                loading: true
            });
            const client = await api.getClient();
            const res = await client.v1_registry_service_services_list({
                page: tableState.page,
                page_size: tableState.pageSize,
                ordering: tableState.ordering
            });
            setBackendState({
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
                    dataSource={backendState.dataSource}
                    rowKey={(record:any) => record.id}
                    columns={columns}
                    loading={backendState.loading}
                    pagination={{
                        current: tableState.page,
                        pageSize: tableState.pageSize,
                        total: backendState.total,
                    }}
                    onChange={handleTableChange}
                />
            </Card>
        </div>
    );
}
