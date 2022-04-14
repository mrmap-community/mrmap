import { configureStore } from '@reduxjs/toolkit';
import { useContext } from 'react';
import { OpenAPIContext } from 'react-openapi-client/OpenAPIProvider';
import { Provider as ReduxProvider } from 'react-redux';
import backgroundProcessReducer from '../Reducers/BackgroundProcesses';

const StoreProvider: React.FC = (props: any) => {
  const { api } = useContext(OpenAPIContext);
  const store = configureStore({
    reducer: {
      backgroundProcesses: backgroundProcessReducer,
    },
    middleware: getDefaultMiddleware =>
      getDefaultMiddleware({
        thunk: {
          extraArgument: {
            api: api
          }
        }
      })
  });
  return (
  <ReduxProvider store={store}>
    {props.children}
  </ReduxProvider>)
};

export default StoreProvider;