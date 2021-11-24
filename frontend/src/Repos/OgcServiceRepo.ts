import OpenApiRepo, { JsonApiMimeType } from "./OpenApiRepo";
import OpenAPIService from "./OpenApiRepo";

export interface OgcService {
    type: string;
    id: string;
    links: any;
    attributes: any;
    relationships: any;
}

export interface OgcServiceCreate {
    get_capabilities_url: string;
    owned_by_org: string;
}

export class OgcServiceRepo extends OpenApiRepo<OgcService> {

    constructor() {
        super("/api/v1/registry/wms/");
    }

    async create(create: OgcServiceCreate): Promise<any> {
        const client = await OpenAPIService.getClientInstance();
        return await client["create" + this.resourcePath ](undefined, {
            "data": {
                "type": "OgcService",
                "attributes": {
                    "get_capabilities_url": create.get_capabilities_url
                },
                "relationships": {
                    "owned_by_org": {
                        "data": {
                            "type": "Organization",
                            "id": create.owned_by_org
                        }
                    }
                }
            }
        }, { headers: { 'Content-Type': JsonApiMimeType } });
    }
}

export default OgcServiceRepo;
