import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import { KeyGate } from "./components/KeyGate.jsx";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <KeyGate>{(access) => <App access={access} />}</KeyGate>
  </React.StrictMode>
);
