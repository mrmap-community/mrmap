import { TooltipProps } from 'antd';
import { ReactNode } from 'react';

export interface ValidationPropsType {
  rules: any[]
  errorHelp: string;
  hasFeedback: boolean;
  feedbackStatus: '' | 'success' | 'warning' | 'error' | 'validating' | undefined;
}

export type TooltipPropsType = TooltipProps & { icon: ReactNode }

export interface NodeAttributesFormType {
  name: string;
  form: ReactNode;
}
