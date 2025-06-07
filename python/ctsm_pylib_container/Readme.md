# ctsm_pylib container
This directory and its Dockerfile are used to build a container for running (mostly testing) the CTSM Python tools. Unless you're a developer working on the container, you probably don't need to care about anything in here.

## Building
To build the image, go to the top level of the CTSM checkout, then do
```shell
docker build -f python/ctsm_pylib_container/Dockerfile -t ctsm_pylib_container .
```