import { ReactNode } from 'react';

import { TooltipProps } from 'antd/lib/tooltip';


export interface ValidationPropsType {
  rules: any[]
  hasFeedback: boolean;
}

export type TooltipPropsType = TooltipProps & { icon: ReactNode }

export interface NodeAttributesFormType {
  name: string;
  form: ReactNode;
}
