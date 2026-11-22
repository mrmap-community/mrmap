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

/** The route of a screen a feature file may name; an unknown screen is a bug. */
export const screenPath = (screen: string): string => {
  const key = screen.toLowerCase().replace(/[\s-]+/g, "_") as Screen;
  const path = SCREENS[key];
  if (!path) throw new Error(`unknown screen "${screen}" — known: ${SCREEN_NAMES.join(", ")}`);
  return path;
};
