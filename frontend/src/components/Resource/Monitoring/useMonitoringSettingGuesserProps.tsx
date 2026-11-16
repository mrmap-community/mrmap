import { useMemo } from 'react';
import { useRecordContext } from 'react-admin';

import { ReferenceManyInput } from '../../../jsonapi/components/ReferenceManyInput';
import useFieldsForResource from '../../../jsonapi/hooks/useFieldsForResource';
import CronInput from '../../Input/CronInput';
import SchedulePreviewPanel from '../Generic/Schedule/SchedulePreviewPanel';

/** A kind of probe which is configurable for a monitoring setting. */
export interface MonitoringProbeConfig {
  /** resource of the probe which is configured with the setting */
  reference: string
  /** field of the setting which holds the probes */
  source: string
}


/** Builds the guesser props of a monitoring setting of a registered service.
 *
 * The probes of a setting are always bound to the setting, so they are
 * configured with the `setting` target.
 */
const useMonitoringSettingGuesserProps = (
  resource: string,
  probes: MonitoringProbeConfig[]
) => {
  const record = useRecordContext()

  const fieldDefinitions = useFieldsForResource({
    resource,
    overwrites: [{ props: { source: 'scheduleInterval' }, component: CronInput }]
  })
  // the service kind comes from the schema reference of the settings'
  // service field, not from a hardcoded name table (#1327)
  const serviceKind = fieldDefinitions.find(
    fieldDefinition =>
      fieldDefinition.props.source === 'service' &&
      fieldDefinition.props.reference !== undefined
  )?.props.reference
  const guesserProps = useMemo(() => ({
    resource,
    updateFieldDefinitions: fieldDefinitions,
    defaultValues: {
      service: record
    },
    referenceInputs: [
      ...probes.map(({ reference, source }) => (
        <ReferenceManyInput
          key={source}
          reference={reference}
          source={source}
          target='setting'
        />
      )),
      <SchedulePreviewPanel
        key='schedule-preview'
        operation='monitoring'
        serviceKind={serviceKind}
        serviceId={record?.id}
      />
    ]
  }), [
    fieldDefinitions, probes, record, resource, serviceKind
  ])
  return guesserProps
}

export default useMonitoringSettingGuesserProps;
