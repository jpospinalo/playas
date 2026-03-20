docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama

sudo systemctl enable --now docker

docker exec -it ollama ollama pull phi4-mini:3.8b


# {
#   "model": "phi4-mini:3.8b",
#   "prompt": "responde en 30 palabras. ¿qué modelo eres?",
#   "stream": false,
#   "keep_alive": -1,
#   "options": {
#     "num_ctx": 512,
#     "num_predict": 128
#   }
# }
