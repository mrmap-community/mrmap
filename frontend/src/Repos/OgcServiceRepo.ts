import OpenApiRepo from "./OpenApiRepo";

export interface OgcServiceCreate {
    get_capabilities_url: string;
    owned_by_org: string;
}

export class OgcServiceRepo extends OpenApiRepo<any> {

    constructor() {
        super("/api/v1/registry/ogcservices/");
    }

    async create(create: OgcServiceCreate): Promise<any> {
        const attributes = {
            "get_capabilities_url": create.get_capabilities_url
        }
        const relationships = {
            "owned_by_org": {
                "data": {
                    "type": "Organization",
                    "id": create.owned_by_org
                }
            }
        }
        return this.add("OgcService", attributes, relationships);
    }
}

export default OgcServiceRepo;
