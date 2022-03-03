import { TooltipProps } from 'antd/lib/tooltip';
import { ReactNode } from 'react';

export interface ValidationPropsType {
  rules: any[]
  hasFeedback: boolean;
}

export type TooltipPropsType = TooltipProps & { icon: ReactNode }

