PYTHON ?= python
PIP ?= $(PYTHON) -m pip
STREAMLIT ?= $(PYTHON) -m streamlit
PORT ?= 8501

.PHONY: all install auth ui run test render

all: install

install:
	$(PIP) install -r requirements.txt

auth:
	$(PYTHON) auth.py

ui:
	$(STREAMLIT) run dashboard/streamlit_app.py --server.address 0.0.0.0 --server.port $(PORT)

run: ui

test:
	$(PYTHON) -m pytest tests -v

render:
	$(STREAMLIT) run dashboard/streamlit_app.py --server.address 0.0.0.0 --server.port $${PORT:-10000} --server.headless true
