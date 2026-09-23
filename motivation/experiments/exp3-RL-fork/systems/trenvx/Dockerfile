ARG WORKLOAD_IMAGE
FROM ${WORKLOAD_IMAGE}
ARG WORKLOAD_NAME
COPY workloads/${WORKLOAD_NAME} /opt/mixfs
RUN chmod +x /opt/mixfs/guest-runner.sh
