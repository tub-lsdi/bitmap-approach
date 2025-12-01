up:
	docker-compose up -d go-service

down:
	docker-compose down

benchmark:
	docker-compose run --build --rm python-service uv run benchmark_cs_jp_lp.py --start $(START) --end $(END)

