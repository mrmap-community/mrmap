import { Form, Input } from 'antd';
import React, { FC, ReactNode } from 'react';

import { TooltipPropsType, ValidationPropsType } from '../types';

interface InputFormFieldProps {
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

export const InputFormField: FC<InputFormFieldProps> = ({
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
    errorHelp: '',
    hasFeedback: false,
    feedbackStatus: ''
  },
  type = 'text'
}) => {
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
