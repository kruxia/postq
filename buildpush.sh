#!/bin/bash
set -eux

cd `dirname $0`; 
TAG=$(python setup.py --version)

docker-compose build postq
docker tag postq_postq kruxia/postq:$TAG
docker tag postq_postq kruxia/postq
docker push kruxia/postq
docker push kruxia/postq:$TAG

