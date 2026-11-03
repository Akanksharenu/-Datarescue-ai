import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The backend URL comes from VITE_API_URL (see .env.example); nothing is hard-coded here.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
});
