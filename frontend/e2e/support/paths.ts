// The screens a scenario is allowed to name (#1689). "the dataset list" is
// business-readable; the route behind it is not a fact a feature file should
// carry (contract "Selector policy": no URL fragment in Gherkin). Every screen
// literal lives here, the step resolves the name and the UiAdapter navigates.

export const SCREENS = {
  portal: "/",
  search: "/search",
  login: "/login",
  dataset_list: "/DatasetMetadataRecord",
  wms_list: "/WebMapService",
  csw_list: "/CatalogueService",
  keyword_list: "/Keyword",
  language_list: "/Language",
  harvesting_list: "/HarvestingJob",
  background_processes: "/BackgroundProcess",
  csw_client: "/csw-client",
} as const;

export type Screen = keyof typeof SCREENS;

export const SCREEN_NAMES = Object.keys(SCREENS);

/** `datagrid` — a react-admin table; `explorer` — the dataset result list. */
export type ListShape = "datagrid" | "explorer";

// The app has two list shapes and the route decides which one it uses: the
// react-admin datagrid of a service or term list, and the result list of the
// metadata explorer (an ARIA list beside a coverage map, no table at all). The
// adapter reads the shape from the route rather than guessing from what is
// rendered — guessing is how an assertion silently matches page chrome, which
// is what made the first `Then the list answers with rows` vacuous (#1689
// review, finding 1). Keyed by route, so all three "I open …" steps of the
// grammar and a reload get the same answer.
const EXPLORER_ROUTES = new Set<string>([SCREENS.dataset_list]);

const screenKey = (screen: string): Screen =>
  screen.toLowerCase().replace(/[\s-]+/g, "_") as Screen;

/** The route of a screen a feature file may name; an unknown screen is a bug. */
export const screenPath = (screen: string): string => {
  const path = SCREENS[screenKey(screen)];
  if (!path) throw new Error(`unknown screen "${screen}" — known: ${SCREEN_NAMES.join(", ")}`);
  return path;
};

/** How the results of a route are rendered; anything without a list is `datagrid`. */
export const routeShape = (path: string): ListShape =>
  EXPLORER_ROUTES.has(path.replace(/\/+$/, "") || "/") ? "explorer" : "datagrid";
