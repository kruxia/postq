#!/bin/bash
set -eux

cd `dirname $0`; 
TAG=$(python setup.py --version)
SHA=$(git rev-parse --short HEAD)

docker-compose build postq
docker tag postq_postq kruxia/postq:$SHA
docker tag postq_postq kruxia/postq:$TAG
docker tag postq_postq kruxia/postq:latest
docker push kruxia/postq:$SHA
docker push kruxia/postq:$TAG
docker push kruxia/postq:latest
docker image rm kruxia/postq:$TAG
docker image rm kruxia/postq:$SHA
