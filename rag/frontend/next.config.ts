import path from "path";
import { config as loadEnv } from "dotenv";
import type { NextConfig } from "next";

// Cargar variables de entorno desde el .env raíz del monorepo.
// Esto permite tener un único .env compartido entre el backend (Python)
// y el frontend (Next.js) en lugar de archivos separados.
loadEnv({ path: path.resolve(__dirname, "../.env") });

const nextConfig: NextConfig = {};

export default nextConfig;
