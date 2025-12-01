up:
	docker compose up -d go-service

down:
	docker compose down

build-python:
	docker compose build python-service

benchmark:
	docker compose run --rm python-service uv run benchmark_cs_jp_lp.py --start $(START) --end $(END)

