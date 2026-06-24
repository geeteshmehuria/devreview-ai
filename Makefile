.PHONY: up down build logs migrate test-backend test-frontend test-e2e clean

## Start all services
up:
	docker compose up

## Start in background
up-d:
	docker compose up -d --build

## Stop all services
down:
	docker compose down

## Rebuild images
build:
	docker compose build

## View logs
logs:
	docker compose logs -f

## Run database migrations
migrate:
	docker compose exec backend alembic upgrade head

## Generate a new migration
migration:
	docker compose exec backend alembic revision --autogenerate -m "$(MSG)"

## Backend tests
test-backend:
	cd backend && pytest -v

## Frontend tests
test-frontend:
	cd frontend && npm test

## E2E tests
test-e2e:
	cd frontend && npm run test:e2e

## Run all tests
test: test-backend test-frontend

## Install frontend deps locally
install-frontend:
	cd frontend && npm install

## Install backend deps locally
install-backend:
	cd backend && pip install -r requirements.txt

## Clean docker volumes (WARNING: deletes database)
clean:
	docker compose down -v

## Show API docs URL
docs:
	@echo "API Docs: http://localhost:8000/api/docs"
	@echo "ReDoc:    http://localhost:8000/api/redoc"
