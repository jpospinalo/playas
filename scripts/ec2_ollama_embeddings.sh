sudo apt-get update && sudo apt-get upgrade -y

sudo apt-get install -y docker.io

sudo systemctl enable --now docker

sudo docker volume create ollama

sudo docker run -d \
  --name ollama \
  --restart always \
  -p 11434:11434 \
  -v ollama:/root/.ollama \
  ollama/ollama

sudo docker exec -it ollama ollama pull embeddinggemma:latest

