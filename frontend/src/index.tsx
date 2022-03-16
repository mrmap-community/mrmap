import { ConfigProvider } from 'antd';
import 'antd/dist/antd.css';
import deDE from 'antd/lib/locale/de_DE';
import { AxiosRequestConfig } from 'axios';
import 'moment/locale/de'; // needed for german date formats in antd date components
import 'ol/ol.css';
import React from 'react';
import ReactDOM from 'react-dom';
import { OpenAPIProvider } from 'react-openapi-client';
import { Provider } from 'react-redux';
import { BrowserRouter as Router } from 'react-router-dom';
import App from './App';
import './index.css';
import reportWebVitals from './reportWebVitals';
import { store } from './Services/ReduxStore/Store';


const defaultConfig: AxiosRequestConfig = {
  baseURL: '/',
  xsrfCookieName: 'csrftoken',
  xsrfHeaderName: 'X-CSRFToken',
  headers: {
    'Content-Type': 'application/vnd.api+json'
  }
};

ReactDOM.render(
  <Provider store={store}>
    <OpenAPIProvider 
      definition='/api/schema/' 
      axiosConfigDefaults={defaultConfig}>
      <ConfigProvider locale={deDE}>
        <Router>
          <App />
        </Router>
      </ConfigProvider>
      
    </OpenAPIProvider>
  </Provider>,

  document.getElementById('root'),
);

// If you want to start measuring performance in your app, pass a function
// to log results (for example: reportWebVitals(console.log))
// or send to an analytics endpoint. Learn more: https://bit.ly/CRA-vitals
reportWebVitals();
