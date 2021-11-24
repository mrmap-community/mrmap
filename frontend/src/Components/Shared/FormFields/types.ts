import { TooltipProps } from 'antd';
import { ReactNode } from 'react';

export interface ValidationPropsType {
  rules: any[]
  hasFeedback: boolean;
}

export type TooltipPropsType = TooltipProps & { icon: ReactNode }

export interface NodeAttributesFormType {
  name: string;
  form: ReactNode;
}
