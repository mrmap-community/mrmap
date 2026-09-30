import { useCallback } from "react";
import { type RaRecord, ShowButton, SimpleList } from "react-admin";

const UpdateJobsList = () => {
  const changes = useCallback((record: RaRecord) => {
    const changes = [];
    const layersChanged = record?.mappings.filter(
      (mapping: RaRecord) => mapping.delta?.length > 0,
    );
    const newLayers = record?.mappings?.filter(
      (mapping: RaRecord) =>
        mapping.newLayer !== undefined && mapping.oldLayer === undefined,
    );
    const deletedLayers = record?.mappings?.filter(
      (mapping: RaRecord) =>
        mapping.newLayer === undefined && mapping.oldLayer !== undefined,
    );

    layersChanged.length > 0 &&
      changes.push(`${layersChanged.length || 0} layer(s) changed`);
    deletedLayers.length > 0 &&
      changes.push(`${deletedLayers} layer(s) are marked for deletion`);
    newLayers.length > 0 &&
      changes.push(`${newLayers.length || 0} new layer(s)`);

    return changes.join("·");
  }, []);

  return (
    <SimpleList
      rightIcon={(record) => (
        <ShowButton
          label={record.status === "Review required" ? "Review" : "View"}
          variant="contained"
          color={record.status === "Review required" ? "warning" : "primary"}
          icon={false}
        />
      )}
      primaryText={(record) =>
        `Update #${record.id} ${new Date(record.doneAt).toLocaleDateString(
          undefined,
          {
            day: "numeric",
            month: "short",
            year: "numeric",
          },
        )}`
      }
      secondaryText={(record) => `${record.status} | ${changes(record)}`}
      rowClick={false}
    />
  );
};

export default UpdateJobsList;
