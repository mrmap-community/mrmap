/** How a map image is authorized: the header of a credential assignment or the browser credentials. */
export interface AuthOptions {
  headers?: Record<string, string>;
  credentials?: RequestCredentials;
}

/**
 * How long a fetched frame answers the identical request again without asking the service. The image of a
 * fixed timestamp is the same observation whenever it is asked for, so reuse is bounded by memory rather
 * than by age: a viewer keeps the frames near its selection and takes the rest back (#705).
 */
const FRAME_STALE_MS = 10 * 60 * 1000;
/** How long an image which no overlay draws anymore is kept before its memory is released. */
const FRAME_GC_MS = 10 * 60 * 1000;

/** The cache identity of one map image; authentication is part of it, so a frame never crosses contexts. */
export type RemoteImageKey = [string, string, string];

/**
 * The authentication a request is made with as one stable string, so that images fetched under one
 * credential are never taken for images of another and the order their headers were given in does not
 * matter to the key they are kept under.
 */
const authenticationId = (authOptions: AuthOptions, authenticationError?: string): string =>
  authenticationError !== undefined
    ? `error:${authenticationError}`
    : [
      Object.entries(authOptions.headers ?? {})
        .sort(([first], [second]) => first.localeCompare(second))
        .map(([name, value]) => `${name}=${value}`)
        .join("&"),
      authOptions.credentials ?? "",
    ].join("&");

/**
 * The key a map image is kept under. The overlay which draws a frame and the buffering which fetches the
 * upcoming ones ask for an image through this one key, which is what lets a buffered frame answer a
 * selection without a second request (#705).
 */
export const remoteImageKey = (
  url: string,
  authOptions: AuthOptions,
  authenticationError?: string,
): RemoteImageKey => ["remoteImage", url, authenticationId(authOptions, authenticationError)];

/**
 * What a buffered frame is remembered under, so that the frames a viewer takes back are exactly the ones
 * it asked for: the same request under another authentication is another frame (#705).
 */
export const remoteImageIdentity = (key: RemoteImageKey): string => JSON.stringify(key);

/** Converts Headers object to Record<string, string> */
const headersToObject = (headers?: Headers): Record<string, string> => {
  if (!headers) return {};
  const obj: Record<string, string> = {};
  headers.forEach((value, key) => {
    obj[key] = value;
  });
  return obj;
};

/**
 * Gets authentication options. Supports:
 * 1. Explicit auth object
 * 2. Auth function that returns auth options
 * 3. Headers object that gets converted to auth options
 */
export const getAuthOptions = (
  auth?: AuthOptions | (() => AuthOptions) | Headers,
): AuthOptions => {
  // If auth is a function, call it
  if (typeof auth === "function") {
    return auth();
  }

  // If auth is a Headers object, convert it
  if (auth instanceof Headers) {
    return {
      headers: headersToObject(auth),
    };
  }

  // If auth is an object, return it
  if (auth) {
    return auth;
  }
  return {};
};

const getServiceExceptionMessage = (xml: string): string | undefined => {
  if (!xml.trimStart().startsWith("<")) return undefined;

  try {
    const document = new DOMParser().parseFromString(xml, "application/xml");
    const exception = Array.from(document.getElementsByTagName("*")).find(
      (element) => element.localName === "ServiceException",
    );

    if (!exception) return undefined;

    const code = exception.getAttribute("code");
    const message = exception.textContent?.trim();

    if (code && message) return `${code}: ${message}`;
    return message || code || "OGC service exception";
  } catch {
    return undefined;
  }
};

/**
 * Requests one map image, answering its bytes or refusing with the reason the service gave. Requests of
 * the same image share one answer, which is how the image an overlay waits for and the same image held in
 * the buffer are one piece of work rather than two (#705).
 */
export const fetchRemoteImage = async ({
  url,
  authOptions,
  authenticationError,
  signal,
  translate,
}: {
  url: string;
  authOptions: AuthOptions;
  authenticationError?: string;
  signal: AbortSignal;
  translate: (key: string) => string;
}): Promise<Blob> => {
  if (authenticationError) throw new Error(translate(`viewerAuth.${authenticationError}`));
  const response = await fetch(url, {
    redirect: authOptions.headers ? "error" : "follow",
    ...(authOptions.headers && { credentials: "omit" }),
    signal,
    ...(authOptions.headers && { headers: authOptions.headers }),
    ...(authOptions.credentials && {
      credentials: authOptions.credentials,
    }),
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }

  const blob = await response.blob();
  // WMS servers can label XML errors as images. Sniff a bounded prefix even
  // for image content types, and decode the full body only when it may be XML.
  const prefix = (await blob.slice(0, 512).text()).trimStart();
  const mayBeXml =
    blob.type.includes("xml") || prefix.startsWith("<") || prefix === "";
  const serviceExceptionMessage = mayBeXml
    ? getServiceExceptionMessage(await blob.text())
    : undefined;
  if (serviceExceptionMessage) {
    throw new Error(serviceExceptionMessage);
  }

  return blob;
};

/**
 * Asking for one map image of one request, asked once and kept for as long as a viewer may reach for it
 * again. The overlay of a layer and the buffering of its neighbouring frames ask through this one
 * definition, so the frame an overlay draws is the very frame the buffer holds for it (#705).
 */
export const remoteImageQuery = (
  url: string,
  authOptions: AuthOptions,
  translate: (key: string) => string,
  authenticationError?: string,
) => ({
  queryKey: remoteImageKey(url, authOptions, authenticationError),
  queryFn: ({ signal }: { signal: AbortSignal }) =>
    fetchRemoteImage({ url, authOptions, authenticationError, signal, translate }),
  retry: false,
  staleTime: FRAME_STALE_MS,
  gcTime: FRAME_GC_MS,
});
