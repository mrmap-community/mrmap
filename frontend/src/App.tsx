import { ServiceList } from "./Components/Service/ServiceList/ServiceList";
import { OpenAPIProvider } from "./Util/OpenAPIProvider";
import './App.css';

function App() {
  return (
    <OpenAPIProvider definition="http://localhost:8001/api/schema/" axiosConfigDefaults={{ baseURL: "http://localhost:8001" }}>
      <ServiceList />
    </OpenAPIProvider>
  );
}

export default App;
