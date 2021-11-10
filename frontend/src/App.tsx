import { Dashboard } from "./Components/Dashboard/Dashboard";
import { ServiceList } from "./Components/Service/ServiceList/ServiceList";
import { OpenAPIProvider } from "./Util/OpenAPIProvider";
import { NavBar } from "./Components/NavBar/NavBar";
import { BrowserRouter as Router, Routes, Route  } from "react-router-dom";
import './App.css';


export default function App() {
  return (
    <Router>
      <OpenAPIProvider definition="https://localhost/api/schema/" axiosConfigDefaults={{ baseURL: "https://localhost" }}>
        <NavBar />
        <Routes>
          <Route path="/" element={<Dashboard/>}/>
          <Route path="/registry/services/wms" element={<ServiceList/>}/>
        </Routes>
      </OpenAPIProvider>
    </Router>
  );
}