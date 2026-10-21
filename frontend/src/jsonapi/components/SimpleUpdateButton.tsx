import { IconButtonWithTooltip, IconButtonWithTooltipProps, RaRecord, useUpdate, UseUpdateOptions } from 'react-admin';


export interface SimpleUpdateButtonProps extends IconButtonWithTooltipProps{
  resource: string
  data: Partial<RaRecord>
  record: RaRecord
  options?: UseUpdateOptions<RaRecord, Error>
}

const SimpleUpdateButton = ({
  resource,
  record,
  data,
  options,
  ...props
}: SimpleUpdateButtonProps) => {
  const [update, { isPending }] = useUpdate();

  return (
    <IconButtonWithTooltip 
      loading={isPending} 
      onClick={() => update(
        resource, 
        {
          id: record?.id,
          data: data,
          previousData: record,
        },
        options
      )}
      {...props}
    />
  )
}

export default SimpleUpdateButton;
