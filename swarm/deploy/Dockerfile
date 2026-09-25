# syntax=docker/dockerfile:1.20
# The base is built from the fork source by build-image.sh.
ARG PAPERCLIP_SOURCE_IMAGE
FROM ${PAPERCLIP_SOURCE_IMAGE}
USER root
COPY --chown=root:root swarm/runtime /opt/swarm/runtime
COPY --chown=root:root swarm/config/campaign.json /opt/swarm/config/campaign.json
COPY --chown=root:root swarm/upstream.lock.json /opt/swarm/upstream.lock.json
RUN chmod -R go-w /opt/swarm
ARG SWARM_COMMIT
ARG SWARM_VERSION
ARG UPSTREAM_VERSION
LABEL org.opencontainers.image.source="https://github.com/kartamyshev-dev/loginom-swarm" \
      org.opencontainers.image.revision="${SWARM_COMMIT}" \
      org.opencontainers.image.version="${SWARM_VERSION}" \
      dev.loginom-swarm.upstream="${UPSTREAM_VERSION}"
USER node
WORKDIR /app
