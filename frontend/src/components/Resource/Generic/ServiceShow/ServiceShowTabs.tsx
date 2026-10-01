import { Tabs, type TabsProps } from "@mui/material";
import {
  Children,
  cloneElement,
  isValidElement,
  type ReactElement,
  type ReactNode,
} from "react";
import { useLocation } from "react-admin";

interface ServiceShowTabsProps extends Omit<TabsProps, "value"> {
  children?: ReactNode;
  syncWithLocation?: boolean;
  value?: number | string;
}

interface ServiceShowTabProps {
  context?: "header" | "content";
  path?: string;
  syncWithLocation?: boolean;
  to?: unknown;
  value?: number | string;
}

const ServiceShowTabs = ({
  children,
  syncWithLocation = true,
  value,
  ...rest
}: ServiceShowTabsProps) => {
  const location = useLocation();
  const showPathIndex = location.pathname.search(/\/show(?:\/|$)/);
  const showBase =
    showPathIndex === -1
      ? `${location.pathname}/show`
      : location.pathname.slice(0, showPathIndex + "/show".length);
  const activePath =
    location.pathname
      .slice(showBase.length)
      .replace(/^\/+/, "")
      .split("/")[0] ?? "";

  return (
    <Tabs
      value={syncWithLocation ? activePath : value}
      variant="scrollable"
      scrollButtons="auto"
      {...rest}
    >
      {Children.map(children, (tab, index) => {
        if (!isValidElement(tab)) {
          return null;
        }

        const tabProps = (tab as ReactElement<ServiceShowTabProps>).props;
        const path =
          typeof tabProps.path === "string"
            ? tabProps.path.replace(/\/\*$/, "")
            : index > 0
              ? index
              : "";

        return cloneElement(tab as ReactElement<ServiceShowTabProps>, {
          context: "header",
          value: syncWithLocation ? path : index,
          syncWithLocation,
          to: {
            ...location,
            pathname: `${showBase}/${path}`,
          },
        });
      })}
    </Tabs>
  );
};

export default ServiceShowTabs;
