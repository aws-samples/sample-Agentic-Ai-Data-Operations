# Ontop VKG Server with Athena JDBC driver
# Pulls ontology + R2RML from S3 at container startup so artifact updates
# require only an ECS rolling restart, not an image rebuild.

FROM public.ecr.aws/amazoncorretto/amazoncorretto:17

# Install unzip + tar + AWS CLI v2 for S3 fetches at startup
RUN yum install -y unzip tar gzip which && yum clean all && \
    curl -fSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip && \
    unzip /tmp/awscliv2.zip -d /tmp/ && \
    /tmp/aws/install && \
    rm -rf /tmp/aws /tmp/awscliv2.zip

# Download and install Ontop CLI
ARG ONTOP_VERSION=5.2.1
RUN mkdir -p /opt/ontop && \
    curl -fSL "https://github.com/ontop/ontop/releases/download/ontop-${ONTOP_VERSION}/ontop-cli-${ONTOP_VERSION}.zip" \
      -o /tmp/ontop.zip && \
    unzip /tmp/ontop.zip -d /opt/ontop && \
    rm /tmp/ontop.zip && \
    chmod +x /opt/ontop/ontop

# Download the Simba Athena JDBC driver JAR
RUN mkdir -p /opt/ontop/jdbc && \
    curl -fSL \
      "https://downloads.athena.us-east-1.amazonaws.com/drivers/JDBC/SimbaAthenaJDBC-2.1.5.1001/AthenaJDBC42-2.1.5.1001.jar" \
      -o /opt/ontop/jdbc/AthenaJDBC42-2.1.5.1001.jar

# Download AWS SDK v1 core + STS JARs (needed by Simba driver for credential chain)
RUN curl -fSL "https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-core/1.12.780/aws-java-sdk-core-1.12.780.jar" \
      -o /opt/ontop/jdbc/aws-java-sdk-core-1.12.780.jar && \
    curl -fSL "https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-sts/1.12.780/aws-java-sdk-sts-1.12.780.jar" \
      -o /opt/ontop/jdbc/aws-java-sdk-sts-1.12.780.jar

RUN mkdir -p /opt/ontop/input

# Entrypoint script: pulls TTL files from S3 then launches Ontop
COPY start.sh /opt/ontop/start.sh
RUN chmod +x /opt/ontop/start.sh

EXPOSE 8080
WORKDIR /opt/ontop
ENTRYPOINT ["/bin/sh", "/opt/ontop/start.sh"]
