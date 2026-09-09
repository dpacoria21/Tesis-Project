ARG BASE_IMAGE
FROM ${BASE_IMAGE}
RUN apt-get update && apt-get install -y --no-install-recommends g++ && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1
USER 65534:65534
WORKDIR /tmp
