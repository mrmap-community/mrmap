import React, { ReactElement } from 'react';
import './ToolsContainer.css';


interface ToolsContainerProps {
  visible: boolean;
  title?: string;
  tools?: ReactElement;
  onClick?: () => void;
}

export const ToolsContainer: React.FC<ToolsContainerProps> = ({
  visible,
  title = '',
  tools,
  onClick = () => {}
}) => {

  return (
    <>
      {
        visible &&
        <div className='tools-container'>
          {tools}
        </div>
      }
    </>
  );
};

export default ToolsContainer;
