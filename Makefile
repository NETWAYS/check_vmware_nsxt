.PHONY: lint test coverage

lint:
	python -m pylint check_vmware_nsxt.py
test:
	env TZ=UTC python -m unittest -v -b test_check_vmware_nsxt.py
coverage:
	env TZ=UTC python -m coverage run -m unittest test_check_vmware_nsxt.py
	env TZ=UTC python -m coverage report -m --include check_vmware_nsxt.py
