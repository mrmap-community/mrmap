import OpenApiRepo from "./OpenApiRepo";

export interface MapContextCreate {
    title: string;
    abstract?: string;
    ownerOrganizationId: string;
}

export class MapContextRepo extends OpenApiRepo<any> {

    constructor() {
        super("/api/v1/registry/mapcontexts/");
    }

    async create(create: MapContextCreate): Promise<any> {
        const client = await OpenApiRepo.getClientInstance();
        const attributes:any = {
            "title": create.title
        }
        if (create.abstract) {
            attributes.abstract = create.abstract;
        }
        const relationships = {
            "owned_by_org": {
                "data": {
                    "type": "Organization",
                    "id": create.ownerOrganizationId
                }
            }
        }
        return this.add("MapContext", attributes, relationships);
    }

}

export default MapContextRepo;
