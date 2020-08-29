# postq Job Worker for the docker Executor
FROM debian:buster-slim
LABEL maintainer="Sean Harrison <sah@kruxia.com>"

WORKDIR /app

# install Docker (without the docker daemon?)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        apt-transport-https \
        ca-certificates \
        curl \
        gnupg \
        gnupg-agent \
        software-properties-common \
    && curl -fsSL https://download.docker.com/linux/debian/gpg >docker.key \
    && apt-key add docker.key \
    && rm docker.key \
    && add-apt-repository \
        "deb [arch=amd64] https://download.docker.com/linux/debian \
        $(lsb_release -cs) \
        stable" \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        docker-ce docker-ce-cli \ 
        # containerd.io \
    && rm -rf /var/lib/apt/lists/*

# install postq
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

COPY ./ ./
RUN pip3 install --no-cache-dir -e .
