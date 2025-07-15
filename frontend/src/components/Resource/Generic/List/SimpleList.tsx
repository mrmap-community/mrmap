import { useResourceContext, useResourceDefinition } from 'react-admin';
import ListGuesser, { ListGuesserProps } from '../../../../jsonapi/components/ListGuesser';
import { createElementIfDefined } from '../../../../utils';
import SimpleCard, { SimpleCardProps } from '../../../MUI/SimpleCard';

export interface SettingsProps extends ListGuesserProps{
  cardProps?: SimpleCardProps
}

const SimpleList = ({
  cardProps,
  ...rest
}: SettingsProps) => {

  const resource = useResourceContext(rest)
  const { name, icon } = useResourceDefinition({resource: resource})

  return (
    <SimpleCard
      title={<span>{createElementIfDefined(icon)} {name}</span>}
      {...cardProps}
    >
      <ListGuesser
        perPage={5}
        {...rest}
      />
    </SimpleCard>
  )
};


export default SimpleList;