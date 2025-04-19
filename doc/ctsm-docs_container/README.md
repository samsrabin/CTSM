This directory and its Dockerfile are used to build a Docker container for building the CTSM documentation. Unless you're a developer working on the container, you probably don't need to care about anything in here.

If you actually want to build the container, make sure Docker is running and do:
```shell
docker build -t ghcr.io/escomp/ctsm/ctsm-docs
```

If you want to publish the container, you first need a [GitHub Personal Access Token (Classic) with the correct permissions](https://github.com/settings/tokens/new?scopes=write:packages). You can authenticate in your shell session like so (note the leading spaces to avoid your token being saved in your shell's history—at least, that works in bash):
```shell
   echo YOUR_PERSONAL_ACCESS_TOKEN_CLASSIC | docker login ghcr.io -u YOUR_USERNAME --password-stdin
```
You'll next need to tag the image. List your images with `docker images`, which should return something like this:
```shell
REPOSITORY                      TAG          IMAGE ID       CREATED       SIZE
...
ghcr.io/escomp/ctsm/ctsm-docs   latest       8722e8712893   3 weeks ago   232MB
...
```
Copy the relevant image ID and give it the `latest` tag:
```shell
docker tag 8722e8712893 ghcr.io/escomp/ctsm/ctsm-docs:latest
```
Push to the repo:
```shell
docker push ghcr.io/escomp/ctsm/ctsm-docs:latest
```
Then browse to the [repo's container page](https://github.com/ESCOMP/CTSM/packages) and make sure it worked and is public. You may need special permissions in the ESCOMP organization in order to change the visibility of a package.

For more information, see:
- [GitHub: Working with the container registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [GitHub: Connecting a repository to a package](https://docs.github.com/en/packages/learn-github-packages/connecting-a-repository-to-a-package)