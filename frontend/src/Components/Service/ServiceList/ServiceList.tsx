import { useContext, useEffect, useState } from "react";
import { Table, Card } from "antd";
import { OpenAPIContext } from "../../../Util/OpenAPIProvider";

export const ServiceList = () => {

    console.log("*** ServiceList");

    const [loading, setLoading] = useState(false);
    const [dataSource, setDataSource] = useState([]);
    const [page, setPage] = useState(1);
    const [pageSize, setPageSize] = useState(1);
    const [total, setTotal] = useState(0);
    const [columns] = useState([{
        title: 'ID',
        dataIndex: 'id',
        key: 'id',
    },
    {
        title: 'Title',
        dataIndex: 'title',
        key: 'title',
    },
    {
        title: 'Abstract',
        dataIndex: 'abstract',
        key: 'abstract',
    },]);

    const { api } = useContext(OpenAPIContext);

    useEffect(() => {
        async function fetchTableData() {
            setLoading(true);
            const client = await api.getClient();
            const res = await client.v1_registry_service_services_list({
                page: page,
                page_size: pageSize
            });
            if (total !== res.data.count) {
                setTotal(res.data.count);
            }
            setDataSource(res.data.results);
            setLoading(false);
        }
        fetchTableData();
    }, [page, pageSize, api, total]);

    function handleTableChange(pagination: any, filters: any, sorter: any) {
        setPage(pagination.current);
        setPageSize(pagination.pageSize);
    };

    return (
        <div className="mrmap-mapcontext-list">
            <Card title="Services" style={{ width: '100%' }}>
                <Table
                    dataSource={dataSource}
                    rowKey={(record: any) => record.id}
                    columns={columns}
                    loading={loading}
                    pagination={{
                        current: page,
                        pageSize: pageSize,
                        total: total
                    }}
                    onChange={handleTableChange}
                />
            </Card>
        </div>
    );
}
