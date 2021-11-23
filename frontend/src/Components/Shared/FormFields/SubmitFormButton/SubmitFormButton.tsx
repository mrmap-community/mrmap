import { Button, Form } from 'antd';
import React, { FC } from 'react';

interface SubmitFormButtonProps {
  buttonText: string;
  disabled?: boolean;
}

export const SubmitFormButton: FC<SubmitFormButtonProps> = ({
  buttonText = '',
  disabled = false
}) => {
  return (
    <Form.Item>
        <Button
          type="primary"
          htmlType="submit"
          disabled={disabled}
        >
          {buttonText}
        </Button>
      </Form.Item>
  );
};
