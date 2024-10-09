# Define variables
IMAGENAME := nwgiebink/tf-gambia
DOCKERFILE := docker/Dockerfile
CONTAINER ?= gambia
CODE_PATH := $(shell pwd)
PARENT_PATH := $(shell dirname "$(CODE_PATH)")
LOGS_DIR ?= /home/logs/
PORT ?= 8080

.PHONY: build start run clean

build:
	docker build -t $(IMAGENAME) -f $(DOCKERFILE) .

clean:
	@echo "Checking if container $(CONTAINER) exists and needs to be removed..."
	@docker rm -f $(CONTAINER) 2>/dev/null || echo "Container $(CONTAINER) may not exist or an error occurred during removal."

start: clean
	docker run -it --gpus all -d \
		-v $(PARENT_PATH):/home/ \
		-v $(LOGS_DIR):/home/logs/ \
		-w /home/ \
		-p $(PORT):$(PORT) \
		--name $(CONTAINER) $(IMAGENAME) 

attach:
	@echo "Attempting to attach to container $(CONTAINER)..."
	@docker attach $(CONTAINER) || { \
		echo "Container $(CONTAINER) may not be running. Attempting to start..."; \
		docker start $(CONTAINER) && docker attach $(CONTAINER) || \
		echo "Failed to attach: container $(CONTAINER) may not exist or an error occurred."; \
	}

run: clean start attach