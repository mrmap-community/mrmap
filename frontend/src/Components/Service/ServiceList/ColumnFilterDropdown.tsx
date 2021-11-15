import { Button, Input, Space } from "antd";
import { SearchOutlined } from '@ant-design/icons';
import { createRef, useEffect, useState } from "react";
import React from "react";

export const ColumnFilterDropdown = ({ setSelectedKeys, selectedKeys, confirm, clearFilters, dataIndex, searchText, setSearchText, searchedColumn, setSearchedColumn, searchInputFocused }: any) => {
    console.log("*** ColumnFilterDropdown");
    const handleSearch = () => {
        confirm();
        setSearchText(selectedKeys[0]);
        setSearchedColumn(dataIndex);
    };
    const handleReset = (clearFilters: any) => {
        clearFilters();
        setSearchText('');
    };
    const inputRef: any = createRef();
    useEffect(() => {
        console.log("useEffect: searchInputFocused: " + searchInputFocused);
        if (searchInputFocused) {
            inputRef.current.select();
        }
    }, [searchInputFocused]);
    return (
        <div style={{ padding: 8 }} >
            <Input
                ref={inputRef}
                placeholder={`Search ${dataIndex}`}
                value={selectedKeys[0]}
                onChange={e => setSelectedKeys(e.target.value ? [e.target.value] : [])}
                onPressEnter={() => handleSearch()}
                style={{ marginBottom: 8, display: 'block' }}
            />
            <Space>
                <Button
                    type="primary"
                    onClick={() => handleSearch()}
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
                        setSearchText(selectedKeys[0]);
                        setSearchedColumn(dataIndex);
                    }}
                >
                    Filter
                </Button>
            </Space>
        </div>
    );
}
