up:
	docker compose up -d go-service

down:
	docker compose down

build:
	docker compose build	

build-python:
	docker compose build python-service

build-go:
	docker compose build go-service

