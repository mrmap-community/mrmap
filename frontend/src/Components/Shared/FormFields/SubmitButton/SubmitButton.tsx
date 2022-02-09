import React, { ReactElement } from 'react';

import { Button, Form } from 'antd';


interface SubmitButtonProps {
  buttonText: string;
  disabled?: boolean;
}

export const SubmitFormButton= ({
  buttonText = '',
  disabled = false
}: SubmitButtonProps): ReactElement => {
  return (
    <Form.Item>
      <Button
        type='primary'
        htmlType='submit'
        disabled={disabled}
      >
        {buttonText}
      </Button>
    </Form.Item>
  );
};
