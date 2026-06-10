import { UUIDTypes } from "uuid"

interface AuthenticationBase {
    id: UUIDTypes
    type: string
    meta?: Record<string, unknown>
}


export interface BasicAuthentication extends AuthenticationBase {
    type: "basic"
    username: string
    password: string
}

export interface BearerAuthentication extends AuthenticationBase {
    type: "bearer"
    token: string
}

export interface JwtAuthentication extends AuthenticationBase {
    type: "jwt"
    token: string
}

export interface ApiKeyAuthentication extends AuthenticationBase {
    type: "apiKey"
    key: string
    name: string
    location: "header" | "query" | "cookie"
}

export interface OAuth2Authentication extends AuthenticationBase {
    type: "oauth2"
    accessToken: string
    refreshToken?: string
    expiresAt?: Date | number
    scope?: string[]
}

export interface DigestAuthentication extends AuthenticationBase {
    type: "digest"
    username: string
    password: string
}

export interface CookieAuthentication extends AuthenticationBase {
    type: "cookie"
    cookie: string
}

export interface MTlsAuthentication extends AuthenticationBase {
    type: "mtls"
    certificate: string
    privateKey: string
}

export interface CustomAuthentication extends AuthenticationBase {
    type: "custom"
    [key: string]: unknown
}

export type Authentication =
    | BasicAuthentication
    | BearerAuthentication
    | JwtAuthentication
    | ApiKeyAuthentication
    | OAuth2Authentication
    | DigestAuthentication
    | CookieAuthentication
    | MTlsAuthentication
    | CustomAuthentication

export const applyAuthentication = (
    url: URL,
    init: RequestInit,
    auth?: Authentication
): RequestInit => {
    if (!auth) {
        return init
    }

    const headers = new Headers(init.headers)

    switch (auth.type) {
        case "basic": {
            headers.set(
                "Authorization",
                `Basic ${btoa(`${auth.username}:${auth.password}`)}`
            )
            break
        }

        case "bearer": {
            headers.set("Authorization", `Bearer ${auth.token}`)
            break
        }

        case "apiKey": {
            if (auth.location === "header") {
                headers.set(auth.name, auth.key)
            } else {
                url.searchParams.set(auth.name, auth.key)
            }
            break
        }

        case "cookie": {
            headers.set("Cookie", auth.cookie)
            break
        }
    }

    return {
        ...init,
        headers,
    }
}