import type { ReactElement, ReactNode } from "react";
import {
  BasenameContextProvider,
  Show,
  TabbedShowLayout,
  useCanAccessResources,
  useLocation,
  useRecordContext,
  useResourceContext,
  useResourceDefinitions,
  useTranslate,
} from "react-admin";

import { Badge, Stack } from "@mui/material";

import { useHttpClientContext } from "../../../../context/HttpClientContext";
import useResourceSchema from "../../../../jsonapi/hooks/useResourceSchema";
import { PUBLIC_READ_RESOURCES } from "../../../../providers/permissions";
import { createElementIfDefined } from "../../../../utils";
import { ATTENTION_REFETCH_INTERVAL } from "./ServiceAttentionTab";
import ServiceShowTabs from "./ServiceShowTabs";

export interface ServiceTab {
  path: string;
  label: string;
  resource?: string;
  /**
   * The `canAccess` action the tab is opened with - `list` (the default) for
   * a tab reading a collection, `edit` for a tab that changes the service.
   * #833: an anonymous visitor is only shown the tabs its check grants.
   */
  action?: "list" | "edit";
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

export default function ServiceShow({ tabs }: Readonly<{ tabs: ServiceTab[] }>) {
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
  const operationTabs = tabs.filter(
    (tab) => !tab.operation || api?.getOperation(tab.operation),
  );
  // #833: every tab reads a collection of its own, so the tab is only open
  // to a visitor whose `canAccess` answers for it - for an anonymous one that
  // leaves the tabs of the published service itself and hides the management
  // tabs of alerts, settings, monitoring and the editor. A tab naming no
  // resource names a collection of its own nowhere and stays as it was.
  const tabResources = (action: "list" | "edit") =>
    [
      ...new Set(
        operationTabs
          .filter((tab) => tab.resource && (tab.action ?? "list") === action)
          .map((tab) => tab.resource!),
      ),
    ];
  const listAccess = useCanAccessResources({
    action: "list",
    resources: tabResources("list"),
  });
  const editAccess = useCanAccessResources({
    action: "edit",
    resources: tabResources("edit"),
  });
  const visibleTabs = operationTabs.filter(
    (tab) =>
      !tab.resource ||
      (tab.action === "edit" ? editAccess : listAccess).canAccess?.[
        tab.resource
      ] === true,
  );

  return (
    <Show
      actions={false}
      disableAuthentication={
        resource !== undefined && PUBLIC_READ_RESOURCES.has(resource)
      }
      // the attention states of a service are attributes of its own record and
      // nothing is pushed about them - the record is re-read from time to
      // time, while the tab is visible (TanStack pauses in hidden tabs)
      queryOptions={{
        meta: { jsonApiParams: include ? { include } : {} },
        refetchInterval: ATTENTION_REFETCH_INTERVAL,
        refetchIntervalInBackground: false,
      }}
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
