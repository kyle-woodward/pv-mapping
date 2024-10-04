# Define variables
IMAGENAME := tf-gpu-v1
DOCKERFILE := docker/Dockerfile
CONTAINER := tf_dev
WORKDIR := /opt/docker-example/
CODE_PATH := $(shell pwd)

.PHONY: build run

build:
	docker build -t $(IMAGENAME) -f $(DOCKERFILE) .

run: 
	docker run --gpus all -it --rm \
		-v $(CODE_PATH):$(WORKDIR) \
		-w $(WORKDIR) \
		-p 8080:8080 \
		--name $(CONTAINER) $(IMAGENAME)