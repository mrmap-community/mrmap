import { Dashboard } from "./Components/Dashboard/Dashboard";
import { ServiceList } from "./Components/Service/ServiceList/ServiceList";
import { NavBar } from "./Components/NavBar/NavBar";
import { BrowserRouter as Router, Routes, Route  } from "react-router-dom";
import './App.css';
import { OpenAPIProvider } from "./Hooks/OpenAPIProvider";
import { LoginForm } from "./Components/Users/Auth/Login";
import { AuthProvider } from "./Hooks/AuthUserProvider";


export default function App() {
  return (
    <Router>
      <OpenAPIProvider definition="https://localhost/backend/api/schema/" axiosConfigDefaults={{ baseURL: "https://localhost/backend" }}>
        <AuthProvider>
          <NavBar />
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