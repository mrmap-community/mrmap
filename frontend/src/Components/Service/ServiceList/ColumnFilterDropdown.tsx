import { Button, Input, Space } from "antd";
import { SearchOutlined } from '@ant-design/icons';

export const ColumnFilterDropdown = () => {
    console.log("*** ColumnFilterDropdown");
    return (
        <div style={{ padding: 8 }}>
            <Input
                placeholder={`Search`}
                style={{ marginBottom: 8, display: 'block' }}
            />
            <Space>
                <Button
                    type="primary"
                    icon={<SearchOutlined />}
                    size="small"
                    style={{ width: 90 }}
                >
                    Search
                </Button>
                <Button size="small" style={{ width: 90 }}>
                    Reset
                </Button>
                <Button
                    type="link"
                    size="small"
                >
                    Filter
                </Button>
            </Space>
        </div>
    );
}
