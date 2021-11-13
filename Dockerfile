# postq for docker
FROM python:3.9-slim-buster
LABEL maintainer="Sean Harrison <sah@kruxia.com>"

WORKDIR /app

# install system requirements -- psql, docker
RUN apt-get update \
    && apt-get install -y --no-install-recommends --no-install-suggests \
        postgresql-client \
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
    && apt-get install -y --no-install-recommends --no-install-suggests \
        docker-ce docker-ce-cli \ 
        containerd.io \
    && rm -rf /var/lib/apt/lists/*

COPY req/ req/
RUN pip install --no-cache-dir -r req/dev.txt

COPY ./ ./
RUN pip install --no-cache-dir -e .

ENTRYPOINT ["./docker-entrypoint.sh", "python", "-m", "postq"]
