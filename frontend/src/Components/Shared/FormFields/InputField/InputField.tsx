import { Form, Input } from 'antd';
import React, { ReactElement, ReactNode } from 'react';
import { TooltipPropsType, ValidationPropsType } from '../FormFieldsTypes';

interface InputFieldProps {
  allowClear?: boolean;
  disabled?: boolean;
  placeholder?: string,
  label: string,
  name: string,
  onChange?: (e:any) => void;
  value?: number | string;
  validation?: ValidationPropsType;
  tooltip?: ReactNode | TooltipPropsType;
  type?: 'email' | 'number' | 'password' | 'text' | 'textarea';
}

export const InputField = ({
  allowClear = false,
  disabled = false,
  placeholder = '',
  label,
  name,
  tooltip,
  onChange = () => undefined,
  value = '',
  validation = {
    rules: [],
    hasFeedback: false
  },
  type = 'text'
}: InputFieldProps): ReactElement => {
  return (
    <Form.Item
      label={label}
      name={name}
      rules={validation.rules}
      hasFeedback={validation.hasFeedback}
      tooltip={tooltip}
    >
      <Input
        allowClear={allowClear}
        disabled={disabled}
        onChange={onChange}
        placeholder={placeholder}
        type={type}
        value={value}
      />
    </Form.Item>
  );
};
