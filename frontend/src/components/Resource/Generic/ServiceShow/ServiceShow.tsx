import { Badge, Stack } from "@mui/material";
import type { ReactElement, ReactNode } from "react";
import {
  BasenameContextProvider,
  Show,
  TabbedShowLayout,
  useLocation,
  useRecordContext,
  useResourceContext,
  useResourceDefinitions,
  useTranslate,
} from "react-admin";
import { useHttpClientContext } from "../../../../context/HttpClientContext";
import useResourceSchema from "../../../../jsonapi/hooks/useResourceSchema";
import { createElementIfDefined } from "../../../../utils";
import ServiceShowTabs from "./ServiceShowTabs";

export interface ServiceTab {
  path: string;
  label: string;
  resource?: string;
  countSource?: string;
  icon?: ReactElement;
  operation?: string;
  content: ReactNode;
}

const TabIcon = ({ tab }: { tab: ServiceTab }) => {
  const definitions = useResourceDefinitions();
  const record = useRecordContext();
  const items: unknown = tab.countSource
    ? record?.[tab.countSource]
    : undefined;
  return (
    <Stack direction="row" spacing={1}>
      {tab.icon ??
        (tab.resource
          ? createElementIfDefined(definitions[tab.resource]?.icon)
          : null)}
      {Array.isArray(items) && (
        <Badge showZero badgeContent={items.length} color="secondary" />
      )}
    </Stack>
  );
};

export default function ServiceShow({ tabs }: { tabs: ServiceTab[] }) {
  const resource = useResourceContext();
  const { api } = useHttpClientContext();
  const { includeAbleResources } = useResourceSchema(`retrieve_${resource}`);
  const { pathname } = useLocation();
  const translate = useTranslate();
  const showIndex = pathname.search(/\/show(?:\/|$)/);
  const basename =
    showIndex < 0 ? pathname : pathname.slice(0, showIndex + "/show".length);
  const include = includeAbleResources?.includes("operationUrls")
    ? "operationUrls"
    : undefined;
  const visibleTabs = tabs.filter(
    (tab) => !tab.operation || api?.getOperation(tab.operation),
  );

  return (
    <Show
      actions={false}
      queryOptions={{ meta: { jsonApiParams: include ? { include } : {} } }}
    >
      <TabbedShowLayout tabs={<ServiceShowTabs />}>
        {visibleTabs.map((tab) => (
          <TabbedShowLayout.Tab
            key={tab.path}
            path={tab.path}
            label={translate(tab.label)}
            icon={<TabIcon tab={tab} />}
          >
            <BasenameContextProvider basename={basename}>
              {tab.content}
            </BasenameContextProvider>
          </TabbedShowLayout.Tab>
        ))}
      </TabbedShowLayout>
    </Show>
  );
}
