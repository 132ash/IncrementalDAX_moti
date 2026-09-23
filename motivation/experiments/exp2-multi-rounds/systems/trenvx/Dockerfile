ARG WORKLOAD_IMAGE
FROM ${WORKLOAD_IMAGE}
COPY workloads/prettier-6604 /opt/mixfs
RUN chmod +x /opt/mixfs/guest-runner.sh /opt/mixfs/build-manifests.sh /opt/mixfs/rounds/*/actions/*.sh
