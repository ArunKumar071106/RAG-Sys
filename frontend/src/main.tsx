import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { loadBrandFonts } from "./brand";
import "./brand/brand.css";
import "./styles/global.css";

loadBrandFonts();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
