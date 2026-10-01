import {
  Card,
  CardActions,
  CardContent,
  CardHeader,
  Divider,
  type CardActionsProps,
  type CardContentProps,
  type CardHeaderProps,
  type CardProps,
} from "@mui/material";
import type { PropsWithChildren, ReactNode } from "react";

export interface SimpleCardProps extends PropsWithChildren {
  title?: ReactNode;
  subheader?: ReactNode;
  cardProps?: CardProps;
  headerProps?: CardHeaderProps;
  /** Use false when the child provides its own content layout and spacing. */
  contentProps?: CardContentProps | false;
  footer?: ReactNode;
  footerProps?: CardActionsProps;
  divider?: boolean;
}

const SimpleCard = ({
  title,
  subheader,
  cardProps,
  headerProps,
  contentProps,
  footer,
  footerProps,
  divider = true,
  children,
}: SimpleCardProps) => {
  const hasHeader = title != null || subheader != null || headerProps != null;
  return (
    <Card sx={{ boxShadow: 4, height: "100%" }} {...cardProps}>
      {hasHeader && (
        <CardHeader title={title} subheader={subheader} {...headerProps} />
      )}
      {hasHeader && divider && <Divider />}
      {contentProps === false ? (
        children
      ) : (
        <CardContent {...contentProps}>{children}</CardContent>
      )}
      {footer != null && footer !== false && (
        <CardActions {...footerProps}>{footer}</CardActions>
      )}
    </Card>
  );
};

export default SimpleCard;
