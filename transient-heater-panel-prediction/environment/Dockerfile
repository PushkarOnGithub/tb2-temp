FROM public.ecr.aws/docker/library/ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-numpy python3-scipy python3-pip && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /app && chmod 0777 /app
WORKDIR /app
COPY data/ /app/data/
