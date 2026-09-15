.PHONY: test unit clean

test: unit
	python3 tools/run.py

unit:
	cd tools && python3 -m unittest -v test_runner.py

clean:
	rm -rf artifacts
