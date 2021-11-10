import { useContext, useEffect, useState } from "react";
import { Table, Card } from "antd";
import { OpenAPIContext } from "../../../Util/OpenAPIProvider";

export const ServiceList = () => {

    console.log("*** ServiceList");

    const [loading, setLoading] = useState(false);
    const [dataSource, setDataSource] = useState([]);
    const [pagination, setPagination] = useState({
        current: 1,
        pageSize: 1,
        total: 0
    });
    const [columns, setColumns] = useState([{
        title: 'ID',
        dataIndex: 'id',
        key: 'id',
    }]);

    // the approach below has the problem that the whole data object is state... makes it difficult to observe only the results for changes
    // const [fetchServices, { loading, data, error }] = useOperationMethod('v1_registry_service_services_list');

    const { api } = useContext(OpenAPIContext);

    async function fetchTableData() {
        setLoading(true);
        const client = await api.getClient();
        const res = await client.v1_registry_service_services_list({
            page: pagination.current,
            page_size: pagination.pageSize
        });
        if (pagination.total !== res.data.count) {
            setPagination({ ...pagination, total: res.data.count });
        }
        setDataSource(res.data.results);
        setLoading(false);
    }

    useEffect(() => {
        fetchTableData();
    }, [pagination.current, pagination.pageSize]);

    function handleTableChange(newPagination: any, filters: any, sorter: any) {
        setPagination(newPagination);
    };

    return (
        <div className="mrmap-mapcontext-list">
            <Card title="MapContext List" extra={<a href="#">More</a>} style={{ width: '100%' }}>
                <Table
                    dataSource={dataSource}
                    rowKey={(record: any) => record.id}
                    columns={columns}
                    loading={loading}
                    pagination={pagination}
                    onChange={handleTableChange}
                />
            </Card>
        </div>
    );
}
