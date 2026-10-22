import { useTranslate } from 'react-admin';

import VpnKeyIcon from '@mui/icons-material/VpnKey';

import { useContextMenuBase } from './ContextMenuBase';
import ContextMenuItem from './ContextMenuItem';

const ManageAuthenticationItem = ({ onManage }: { onManage: (folder?: string) => void }) => {
  const { node } = useContextMenuBase();
  const translate = useTranslate();
  return <ContextMenuItem
    onClick={() => onManage(node?.properties.folder)}
    icon={<VpnKeyIcon fontSize="small" />}
    label={translate('viewerAuth.title')}
  />;
};

export default ManageAuthenticationItem;
