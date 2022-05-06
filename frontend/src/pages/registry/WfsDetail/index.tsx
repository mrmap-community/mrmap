import { PageContainer } from "@ant-design/pro-layout";
import type { ReactElement } from "react";
import { useIntl } from 'umi';

const WfsDetails = (): ReactElement => {
    /**
     * page hooks
     */
    const intl = useIntl();

    
    return (
        <PageContainer
            header={
                {
                    title: intl.formatMessage(
                        { id: 'pages.wmsDetail.pageTitle' },
                        { label: wms?.attributes?.stringRepresentation },
                      ),
                    extra: [
                            <Select
                                allowClear={true}
                                showSearch={true}
                                style={{ width: '100%'}}
                                dropdownMatchSelectWidth={false}
                                placeholder={
                                    intl.formatMessage(
                                        { id: 'pages.wmsDetail.searchLayer' }
                                    )
                                }
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
    );

};


export default WfsDetails;
