import { Form, Select } from 'antd';
import React, { FC, ReactNode } from 'react';

import { TooltipPropsType, ValidationPropsType } from '../types';

interface SearchFieldData {
  value: string | number;
  text: string;
}

interface SearchAutocompleteFormFieldProps {
  showSearch?: boolean,
  placeholder: string,
  label: string,
  name: string,
  fieldKey?: any;
  onChange?: (value: any, option:any) => void;
  onFocus?: React.FocusEventHandler<HTMLElement>;
  onBlur?: React.FocusEventHandler<HTMLElement>;
  filterOption?: any // TODO,
  searchData: SearchFieldData[],
  validation?: ValidationPropsType
  tooltip?: ReactNode | TooltipPropsType;
}

export const SearchAutocompleteFormField: FC<SearchAutocompleteFormFieldProps> = ({
  showSearch = false,
  placeholder,
  label,
  name,
  fieldKey,
  onChange = () => undefined,
  onFocus = () => undefined,
  onBlur = () => undefined,
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
        fieldKey={fieldKey}
      >
        <Select
          showSearch= {showSearch}
          placeholder={placeholder}
          optionFilterProp='children'
          onChange={onChange}
          onFocus={onFocus}
          onBlur={onBlur}
          filterOption={filterOption}
        >
          {searchData.map((data: SearchFieldData, index: number) => (
            <Select.Option
              key={index}
              value={data.value}
            >
              {data.text}
            </Select.Option>
          ))}
        </Select>
      </Form.Item>
  );
};
