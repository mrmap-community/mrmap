import { Dashboard } from "./Components/Dashboard/Dashboard";
import { ServiceList } from "./Components/Service/ServiceList/ServiceList";
import { NavBar } from "./Components/NavBar/NavBar";
import { BrowserRouter as Router, Routes, Route  } from "react-router-dom";
import './App.css';
import { OpenAPIProvider } from "./Hooks/OpenAPIProvider";
import { LoginForm } from "./Components/Users/Auth/Login";
import { AuthProvider } from "./Hooks/AuthUserProvider";
import { Header } from "antd/lib/layout/layout";



export default function App() {
  
  if (process.env.REACT_APP_REST_API_SCHEMA_URL === undefined) {
    throw new Error("Environment variable REACT_APP_REST_API_SCHEMA_URL is undefined.");
  }
  if (process.env.REACT_APP_REST_API_BASE_URL === undefined) {
    throw new Error("Environment variable REACT_APP_REST_API_BASE_URL is undefined.");
  }

  return (
    <Router>
      <OpenAPIProvider definition={process.env.REACT_APP_REST_API_SCHEMA_URL} axiosConfigDefaults={{ baseURL: process.env.REACT_APP_REST_API_BASE_URL }}>
        <AuthProvider>
        <Header>

            <NavBar />
           
        </Header>
          <Routes>
            <Route path="/" element={<Dashboard/>}/>
            <Route path="/registry/services/wms" element={<ServiceList/>}/>
            <Route path="/users/auth/login" element={<LoginForm/>}/>
          </Routes>
        </AuthProvider>
      </OpenAPIProvider>
    </Router>
  );
}