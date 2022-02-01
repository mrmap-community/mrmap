import { ConfigProvider } from 'antd';
import deDE from 'antd/lib/locale/de_DE';
import React from 'react';
import ReactDOM from 'react-dom';
import { Provider } from 'react-redux';
import App from './App';
import './index.css';
import { AuthProvider } from './Providers/AuthProvider';
import reportWebVitals from './reportWebVitals';
import { store } from './Services/ReduxStore/Store';
import WebSockets from './Services/WebSockets';

ReactDOM.render(
  <Provider store={store}>
    <WebSockets />
    <AuthProvider>
      <ConfigProvider locale={deDE}>    
        <App />
      </ConfigProvider>
    </AuthProvider>
  </Provider>,

  document.getElementById('root'),
);

// If you want to start measuring performance in your app, pass a function
// to log results (for example: reportWebVitals(console.log))
// or send to an analytics endpoint. Learn more: https://bit.ly/CRA-vitals
reportWebVitals();
