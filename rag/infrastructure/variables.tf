# ── General ───────────────────────────────────────────────────────────────────

variable "aws_region" {
  description = "Región de AWS"
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Nombre del proyecto"
  type        = string
  default     = "rag-playas"
}

variable "environment" {
  description = "Entorno de despliegue"
  type        = string
  default     = "prod"
}

# ── Imágenes Docker ───────────────────────────────────────────────────────────

variable "backend_image_tag" {
  description = "Tag de la imagen del backend en ECR"
  type        = string
  default     = "latest"
}

variable "frontend_image_tag" {
  description = "Tag de la imagen del frontend en ECR"
  type        = string
  default     = "latest"
}

# ── Base de datos ─────────────────────────────────────────────────────────────

variable "postgres_password" {
  description = "Contraseña de PostgreSQL"
  type        = string
  sensitive   = true
}

# ── Autenticación JWT ─────────────────────────────────────────────────────────

variable "jwt_secret_key" {
  description = "Clave secreta para firmar JWT"
  type        = string
  sensitive   = true
}

variable "jwt_algorithm" {
  description = "Algoritmo JWT"
  type        = string
  default     = "HS256"
}

variable "jwt_expire_minutes" {
  description = "Tiempo de expiración del JWT en minutos"
  type        = number
  default     = 10080
}

# ── LLM ──────────────────────────────────────────────────────────────────────

variable "openai_api_key" {
  description = "API key de OpenAI"
  type        = string
  sensitive   = true
  default     = ""
}

variable "openai_model" {
  description = "Modelo de OpenAI"
  type        = string
  default     = "gpt-4o-mini"
}

variable "openrouter_api_key" {
  description = "API key de OpenRouter"
  type        = string
  sensitive   = true
  default     = ""
}

variable "openrouter_model" {
  description = "Modelo de OpenRouter"
  type        = string
  default     = "openai/gpt-4o-mini"
}

variable "google_api_key" {
  description = "API key de Google (Gemini)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "gemini_model" {
  description = "Modelo de Gemini"
  type        = string
  default     = "gemini-1.5-flash"
}

# ── ChromaDB ──────────────────────────────────────────────────────────────────

variable "chroma_host" {
  description = "Host del servidor ChromaDB"
  type        = string
}

variable "chroma_port" {
  description = "Puerto de ChromaDB"
  type        = number
  default     = 8000
}

variable "chroma_collection" {
  description = "Nombre de la colección de ChromaDB"
  type        = string
  default     = "rag_playas"
}

# ── Ollama ────────────────────────────────────────────────────────────────────

variable "ollama_base_url" {
  description = "URL base del servidor Ollama"
  type        = string
}

variable "ollama_embedding_model" {
  description = "Modelo de embeddings en Ollama"
  type        = string
  default     = "embeddinggemma:latest"
}

variable "ollama_reranker_model" {
  description = "Modelo de reranking en Ollama"
  type        = string
  default     = "llama3.2:3b"
}

# ── Enriquecimiento ───────────────────────────────────────────────────────────

variable "query_enrichment_enabled" {
  description = "Activar enriquecimiento de consultas"
  type        = bool
  default     = true
}

# ── S3 ────────────────────────────────────────────────────────────────────────

variable "s3_bucket_name" {
  description = "Nombre del bucket S3 del pipeline de datos"
  type        = string
  default     = ""
}
