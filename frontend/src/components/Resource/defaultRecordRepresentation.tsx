import { RaRecord } from "react-admin";

const defaultRecordRepresentation = (record: RaRecord) => {
  if (record?.stringRepresentation != null && record?.stringRepresentation !== '') {
    return record.stringRepresentation;
  }
  if (record?.name != null && record?.name !== '') {
    return record.name;
  }
  if (record?.title != null && record?.title !== '') {
      return record.title;
  }
  if (record?.label != null && record?.label !== '') {
      return record.label;
  }
  if (record?.reference != null && record?.reference !== '') {
      return record.reference;
  }
  return `#${record.id}`;
}

export default defaultRecordRepresentation