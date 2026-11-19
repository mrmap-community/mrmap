// The deterministic records of the acceptance stack seeded by
// acceptance_seed.py from the repository's own behave fixtures. The PKs are
// the ones the behave suite pins (`test_wms.json`, `test_datasetmetadata.json`),
// so backend and browser acceptance speak about the same rows.

export const DATASET_VALID_GEOMETRY_PK = 'd8b50d33-2ad7-4a41-bd0d-2d518ea10fd4';
export const DATASET_EMPTY_GEOMETRY_PK = '9e57ada9-d3bf-403f-bd6c-eb4d38f0ef8e';
export const DATASET_ABSENT_GEOMETRY_PK = 'ebdf480c-2c43-483b-bdba-258fd1b333f2';

export const DATASET_TITLE_VALID = 'Niederschlag an RBSN Stationen';
export const DATASET_TITLE_EMPTY = 'Relative Feuchte an RBSN Stationen (empty geometry)';
export const DATASET_TITLE_ABSENT = 'E2E Dataset Without Geometry';

export const WMS_PK = 'cd16cc1f-3abb-4625-bb96-fbe80dbe23e3';
export const WMS_TITLE = 'WMS1';

export const CSW_PK = '9cc4889d-0cd4-4c3b-8975-58de6d30db41';

// The search term of the acceptance run on /search: it matches the valid
// dataset record (title and copied abstract) and not the others.
export const SEARCH_TERM = 'Niederschlag';
