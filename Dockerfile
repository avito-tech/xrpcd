FROM debian

ARG PYTHON_PIP_VERSION="9.0.1"

ENV JOB_NAME= \
    QUEUE_NAME= \
    PROVIDER_DB_DSN= \
    XRPC_DSN= \
    XRPC_SOURCE=

ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8

COPY entrypoint.sh /
COPY xrpcd/conf/xrpcd.ini.dist /

RUN set -x \
    && groupadd -r postgres --gid=999 && useradd -r -g postgres --uid=999 postgres \
    && apt-get update \
        && apt-get install -y --no-install-recommends \
            python \
            python-dev \
            python-setuptools \
            build-essential \
            make \
            skytools \
            gettext \
            wget \
        && gpg --keyserver ha.pool.sks-keyservers.net --recv-keys C01E1CAD5EA2C4F0B8E3571504C367C218ADD4FF \
        && wget -O /tmp/get-pip.py 'https://bootstrap.pypa.io/get-pip.py' \
        && python2 /tmp/get-pip.py "pip==$PYTHON_PIP_VERSION" \
        && rm /tmp/get-pip.py \
        && pip install --no-cache-dir --upgrade xrpcd \
    && mkdir -p /var/run/postgresql && chown -R postgres /var/run/postgresql \
    && apt-get purge -y --auto-remove ca-certificates wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/*

USER postgres
