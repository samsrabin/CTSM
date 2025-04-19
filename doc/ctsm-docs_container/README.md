This directory and its Dockerfile are used to build a Docker container for building the CTSM documentation. Unless you're a developer working on the container, you probably don't need to care about anything in here.

If you actually want to build the container, do:
```shell
docker build -t ctsm/docs
```