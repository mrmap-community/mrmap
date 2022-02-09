import React, { ReactElement, ReactNode, useEffect, useState } from 'react';

import { SettingFilled } from '@ant-design/icons';
import { Form, Select } from 'antd';
import { LabeledValue } from 'antd/lib/select';

import { TooltipPropsType, ValidationPropsType } from '../FormFieldsTypes';


export interface SearchFieldData {
  value: string | number;
  text: string;
  attributes?: any;
  pagination?: {next: string}
}

interface SelectAutocompleteFieldProps {
  loading?: boolean;
  allowClear?: boolean
  placeholder: string,
  label: string,
  name: string,
  onChange?: (value: any, option:any) => void;
  onFocus?: React.FocusEventHandler<HTMLElement>;
  onBlur?: React.FocusEventHandler<HTMLElement>;
  onSearch?: (value: any) => void;
  onSelect?: (value: string | number | LabeledValue, option:any) => void;
  onClear?:() => void;
  filterOption?: any // TODO,
  searchData: SearchFieldData[],
  validation?: ValidationPropsType
  tooltip?: ReactNode | TooltipPropsType;
  pagination?: boolean;
}

export const SelectAutocompleteField = ({
  loading = false,
  allowClear = true,
  placeholder = '',
  label = '',
  name = '',
  onChange = () => undefined,
  onFocus = () => undefined,
  onBlur = () => undefined,
  onSearch = () => undefined,
  onSelect = () => undefined,
  onClear = () => undefined,
  // by default the filter is setting everything you write to lower case and comparing against lower case results
  filterOption = (input:any, option:any) => option.children.toLowerCase().indexOf(input.toLowerCase()) >= 0,
  searchData = [],
  validation = {
    rules: [],
    hasFeedback: false
  },
  tooltip = undefined,
  pagination = false

}: SelectAutocompleteFieldProps): ReactElement => {
  const [searchOptions, setSearchOptions] = useState<SearchFieldData[]>([]);
  const [nextPageData, setNextPageData] = useState<any>(undefined);
  const [isLoadingPaginatedResults, setIsLoadingPaginatedResults] = useState<boolean>(false);

  /**
   * @description: Method to fetch paginaation data and set it to ther state.
   * Assumes that the pagination data is  set as a parameter in every searchData element.
   * @param list
   */
  const getPaginationData = (list: any[]) => {
    const paginationInfo = list.map(listData => listData.pagination);
    setNextPageData(paginationInfo[paginationInfo.length - 1]);
  };

  /**
   * @description Hook to run when searchData changes
   */
  useEffect(() => {
    setSearchOptions(searchData);
  }, [searchData]);

  /**
   * @description Hook to run when searchData is available and has pagination. Fetches the initial pagination data
   */
  useEffect(() => {
    if (pagination && searchOptions) {
      getPaginationData(searchOptions);
    }
  }, [pagination, searchOptions]);

  /**
   * @description: Assyncronous method called when the popup menu is being scrolled.
   * Currently it is designed to handle openAPI responses, where every response provides a link to the next page.
   * It will stop requesting new vaalues when the link to next paage has the value "null"
   */
  const onPopupScroll = async (e:any) => {
    // to detect when the scroll has been done all the way down
    const hasReachedBottom: boolean = e.target.scrollHeight - e.target.scrollTop === e.target.clientHeight;

    if (pagination) {
      if (nextPageData && nextPageData.next && hasReachedBottom) {
        try {
          setIsLoadingPaginatedResults(true);
          const promise:any = await fetch(nextPageData.next);
          if (promise.ok) {
            const response = await promise.json();
            // update the search options by providing more results coming from the response
            setSearchOptions([...searchOptions, ...response.data.map((o: any) => ({
              value: o.id,
              text: o.attributes.title,
              attributes: o.attributes,
              pagination: {
                next: response.links.next
              }
            }))]);
          } else {
            setIsLoadingPaginatedResults(false);
            throw new Error(promise.status);
          }
        } catch (error) {
          setIsLoadingPaginatedResults(false);
          // @ts-ignore
          throw new Error(error);
        } finally {
          setIsLoadingPaginatedResults(false);
          // update the pagination data
          getPaginationData(searchOptions);
        }
      }
    }
  };

  return (
    <Form.Item
      label={label}
      name={name}
      rules={validation.rules}
      hasFeedback={validation.hasFeedback}
      tooltip={tooltip}
    >
      <Select
        loading={loading}
        showSearch
        allowClear={allowClear}
        placeholder={placeholder}
        optionFilterProp='children'
        onChange={onChange}
        onFocus={onFocus}
        onBlur={onBlur}
        onSearch={onSearch}
        onSelect={onSelect}
        onClear={onClear}
        onPopupScroll={onPopupScroll}
        filterOption={filterOption}
        dropdownRender={(menu) => (
          <>
            {menu}
            {isLoadingPaginatedResults && (<p>Loading more results <SettingFilled spin/></p>)}
          </>
        )}
      >
        {searchOptions.map((data: SearchFieldData, index: number) => (
          <Select.Option
            key={index}
            value={data.value}
            attributes={data.attributes}
          >
            {data.text}
          </Select.Option>
        ))}
      </Select>
    </Form.Item>
  );
};
