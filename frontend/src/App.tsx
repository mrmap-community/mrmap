import { Dashboard } from "./Components/Dashboard/Dashboard";
import { ServiceList } from "./Components/Service/ServiceList/ServiceList";
import { NavBar } from "./Components/NavBar/NavBar";
import { BrowserRouter as Router, Routes, Route  } from "react-router-dom";
import './App.css';
import { OpenAPIProvider } from "./Hooks/OpenAPIProvider";


export default function App() {
  return (
    <Router>
      <OpenAPIProvider definition="http://localhost:8001/api/schema/" axiosConfigDefaults={{ baseURL: "http://localhost:8001" }}>
        <NavBar />
        <Routes>
          <Route path="/" element={<Dashboard/>}/>
          <Route path="/registry/services/wms" element={<ServiceList/>}/>
        </Routes>
      </OpenAPIProvider>
    </Router>
  );
}