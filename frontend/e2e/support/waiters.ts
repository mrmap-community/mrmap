import { expect } from "@playwright/test";

import type { E2EWorld } from "./world";

// The Then-async category of the step grammar (#1688): the interval and the
// deadline live here in code, the feature file only names the terminal state.
// A step that carried a timeout would make the Gherkin layer unmergeable
// across machines of different speed.

export const WAIT_TIMEOUT_MS = Number(process.env.E2E_WAIT_TIMEOUT ?? 180_000);
export const WAIT_INTERVAL_MS = Number(process.env.E2E_WAIT_INTERVAL ?? 1_000);

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export type PollOptions = { timeout?: number; interval?: number };

export const pollUntil = async (world: E2EWorld, label: string, probe: () => Promise<boolean>, options: PollOptions = {}) => {
  const timeout = options.timeout ?? WAIT_TIMEOUT_MS;
  const interval = options.interval ?? WAIT_INTERVAL_MS;
  const deadline = Date.now() + timeout;
  let last: unknown = "no attempt yet";
  do {
    try {
      if (await probe()) return;
      last = "the probe answered false";
    } catch (error) {
      last = error instanceof Error ? error.message : String(error);
    }
    await sleep(interval);
  } while (Date.now() < deadline);
  world.lastAsyncObservation = last;
  throw new Error(`${label} did not happen within ${timeout} ms. Last observation: ${last}`);
};

// The harness's own failure signal: a background process is reported over
// /api/notify/background-processes, and a finished run is the only proof that
// out-of-process work completed.
export const backgroundProcessReachedState = async (world: E2EWorld, processType: string, state: string) => {
  const response = await world.request.get(
    `/api/notify/background-processes?sort=-dateCreated&page[size]=25&processType=${encodeURIComponent(processType)}`
  );
  if (!response.ok()) throw new Error(`background process list answered ${response.status()}`);
  const body = (await response.json()) as { data?: { attributes?: { processType?: string; status?: string } }[] };
  const match = (body.data ?? []).find((entry) => entry.attributes?.processType === processType);
  if (!match) throw new Error(`no ${processType} background process in the latest 25`);
  return match.attributes?.status === state;
};

export const expectBackgroundProcessState = async (world: E2EWorld, processType: string, state: string) => {
  await pollUntil(world, `background process ${processType} reaches ${state}`, () =>
    backgroundProcessReachedState(world, processType, state)
  );
  expect(world.lastAsyncObservation, "a finished async wait leaves no failure reason").toBeUndefined();
};
