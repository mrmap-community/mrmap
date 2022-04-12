import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import React from 'react';
import { ProgressList } from '../BackgroundProcessList';
import HeaderDropdown from '../HeaderDropdown';

export type GlobalHeaderRightProps = {
  menu?: boolean;
};

const BackgroundProcessDropdown: React.FC<GlobalHeaderRightProps> = ({ menu }) => {

  return (
    <HeaderDropdown overlay={<ProgressList/>}>
        <FontAwesomeIcon icon={["fas", "bars-progress"]} />
    </HeaderDropdown>
  );
};

export default BackgroundProcessDropdown;
