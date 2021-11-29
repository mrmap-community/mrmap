import { Form, Select } from 'antd';
import { LabeledValue } from 'antd/lib/select';
import React, { FC, ReactNode } from 'react';

import { TooltipPropsType, ValidationPropsType } from '../types';

export interface SearchFieldData {
  value: string | number;
  text: string;
  attributes?: any;
}

interface SelectAutocompleteFormFieldProps {
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
}

export const SelectAutocompleteFormField: FC<SelectAutocompleteFormFieldProps> = ({
  loading = false,
  allowClear = true,
  placeholder,
  label,
  name,
  onChange = () => undefined,
  onFocus = () => undefined,
  onBlur = () => undefined,
  onSearch = () => undefined,
  onSelect = () => undefined,
  onClear = () => undefined,
  // by default the filter is setting everything you write to lower case and comparing against lower case results
  filterOption = (input:any, option:any) => option.children.toLowerCase().indexOf(input.toLowerCase()) >= 0,
  searchData,
  validation = {
    rules: [],
    hasFeedback: false
  },
  tooltip = undefined
}) => {
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
          filterOption={filterOption}
        >
          {searchData.map((data: SearchFieldData, index: number) => (
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
