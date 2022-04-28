import { Form, Input } from 'antd';
import type { TooltipProps } from 'antd/lib/tooltip';
import type { ReactElement, ReactNode } from 'react';

interface ValidationPropsType {
  rules: any[];
  hasFeedback: boolean;
}

type TooltipPropsType = TooltipProps & { icon: ReactNode };

interface InputFieldProps {
  allowClear?: boolean;
  disabled?: boolean;
  placeholder?: string;
  label: string;
  name: string;
  onChange?: (e: any) => void;
  value?: number | string;
  validation?: ValidationPropsType;
  tooltip?: ReactNode | TooltipPropsType;
  type?: 'email' | 'number' | 'password' | 'text' | 'textarea';
}

const InputField = ({
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
    hasFeedback: false,
  },
  type = 'text',
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

export default InputField;
