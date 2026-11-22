import { expect, request as pwRequest, type APIRequestContext, type Page } from "@playwright/test";

import { UiAdapter } from "./adapters/ui";

// The world of one scenario (#1688, "Scenario-state lifetimes" scope 3): the
// adapters a step may talk to, the response log the API assertions read, and the
// bookkeeping that lets a scenario assert what it created. Steps receive this
// fixture instead of the raw page — that is what keeps a step free of selectors
// and transport details.

export type RecordedResponse = { url: string; method: string; status: number; headers: Record<string, string> };

// Only headers that cannot identify a session are kept: the artifact of a failed
// run leaves the runner, and a recorded Authorization header is a live credential.
const HEADER_ALLOW_LIST = ["content-type", "content-length", "allow", "deprecation", "warning"];

const sanitizeHeaders = (headers: Record<string, string>) => {
  const kept: Record<string, string> = {};
  for (const [name, value] of Object.entries(headers)) {
    if (HEADER_ALLOW_LIST.includes(name.toLowerCase())) kept[name] = value;
  }
  return kept;
};

export class E2EWorld {
  readonly responses: RecordedResponse[] = [];
  readonly created: { resource: string; ids: string[] }[] = [];
  lastAsyncObservation?: unknown;
  lastExport?: string;
  private readonly tokens = new Map<string, string>();
  readonly ui: UiAdapter;

  constructor(
    readonly page: Page,
    readonly request: APIRequestContext
  ) {
    this.ui = new UiAdapter(page);
    page.on("response", (response) => {
      const url = response.url();
      if (!url.includes("/api/") && !url.includes("/csw")) return;
      this.responses.push({
        url,
        method: response.request().method(),
        status: response.status(),
        headers: sanitizeHeaders(response.headers()),
      });
    });
  }

  resetResponses() {
    this.responses.length = 0;
  }

  /** Bookkeep a record the scenario created, so a later Then can read it back. */
  remember(resource: string, id: string) {
    const entry = this.created.find((item) => item.resource === resource);
    if (entry) entry.ids.push(id);
    else this.created.push({ resource, ids: [id] });
  }

  createdIds(resource?: string) {
    return this.created
      .filter((entry) => !resource || entry.resource === resource)
      .flatMap((entry) => entry.ids);
  }

  rememberToken(role: string, token: string) {
    this.tokens.set(role, token);
  }

  /** A client authenticated with the remembered machine token of a role (#835). */
  async asRole(role: string) {
    const token = this.tokens.get(role);
    if (!token) throw new Error(`no token remembered for role "${role}" — run the "the <role> role has a token" Given first`);
    return pwRequest.newContext({ extraHTTPHeaders: { Authorization: `Token ${token}` } });
  }

  lastResponsesFor(pattern: RegExp) {
    return this.responses.filter((entry) => pattern.test(entry.url));
  }

  expectNoRejectedApiCalls() {
    const rejected = this.responses.filter((entry) => entry.status >= 400);
    expect(
      rejected.map((entry) => `${entry.method} ${entry.url} -> ${entry.status}`),
      "no API call of the scenario answered 4xx/5xx"
    ).toEqual([]);
  }
}
