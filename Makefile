.PHONY: up up-gpu down build build-gpu logs migrate shell-backend pull-model

up:
	docker compose up -d --build

# Linux + NVIDIA: requires nvidia-container-toolkit. See docker-compose.gpu.yml.
up-gpu:
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build

down:
	docker compose down

build:
	docker compose build

build-gpu:
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml build

logs:
	docker compose logs -f backend worker

migrate:
	docker compose exec backend alembic upgrade head

shell-backend:
	docker compose exec backend bash

pull-model:
	docker compose exec ollama ollama pull llama3.2
