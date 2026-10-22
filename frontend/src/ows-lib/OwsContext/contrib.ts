interface AuthenticationBase {
    id: string
    type: string
    meta?: Record<string, unknown>
}

export interface HeaderAuthentication extends AuthenticationBase {
    type: "header"
    name: string
    value: string
    origin?: string
}


export type Authentication =
    | HeaderAuthentication
