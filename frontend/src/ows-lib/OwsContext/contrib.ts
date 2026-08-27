import { UUIDTypes } from "uuid"

interface AuthenticationBase {
    id: UUIDTypes
    type: string
    meta?: Record<string, unknown>
}

export interface HeaderAuthentication extends AuthenticationBase {
    type: "header"
    name: string
    value: string
}


export type Authentication =
    | HeaderAuthentication
