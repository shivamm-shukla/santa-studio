import React from "react";
import { createRoot } from "react-dom/client";

import Booth from "./Booth.jsx";
import "./booth.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Booth />
  </React.StrictMode>
);
