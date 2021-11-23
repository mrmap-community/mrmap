import { Form, Input } from 'antd';
import React, { FC, ReactNode } from 'react';

import { TooltipPropsType, ValidationPropsType } from '../types';

interface InputFormFieldProps {
  allowClear?: boolean;
  disabled?: boolean;
  placeholder?: string,
  label: string,
  name: string,
  fieldKey?: any;
  onChange?: (e:any) => void;
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
  fieldKey,
  tooltip,
  onChange = () => undefined,
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
        fieldKey={fieldKey}
        rules={validation.rules}
        validateStatus={validation.feedbackStatus}
        help={validation.errorHelp}
        hasFeedback={validation.hasFeedback}
        tooltip={tooltip}
      >
        <Input
          allowClear={allowClear}
          disabled={disabled}
          onChange={onChange}
          placeholder={placeholder}
          type={type}
        />
      </Form.Item>
  );
};
