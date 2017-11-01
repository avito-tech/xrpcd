# xrpcd

PostgreSQL RPC built on top of pgq.

`xrpcd` requires the `pgq` (along with `pgq` schema) and `hstore` extensions to be installed.

## Setup dev env

```bash
$ mkvirtualenv --python=/usr/local/bin/python2.7 xrpcd
$ workon xrpcd
```

Clone [`skytools`](https://github.com/avito-tech/skytools) into your workspace directory
(not this project's working directory)
and extend `PYTHONPATH` within `skytools/python` for your `virtualenv`:

```bash
$ add2virtualenv ../skytools/python
```

If needed, set up `docker` environment:

```bash
$ cp .env.dist .env
$ $EDITOR .env
```


## Run tests

```bash
PGHOST=$(docker-machine ip) make test
```


## Example `xrpcd` config

```ini
[xrpcd]
job_name = xrpc_common

log_path = /var/log/postgresql
pid_path = /var/run/postgresql

provider_db_name = master
provider_db = dbname=%(provider_db_name)s host=192.168.99.100 user=postgres
xrpc_dsn = host=localhost port=6433 dbname={0} user=postgres
xrpc_source = master

pgq_queue_name = %(job_name)s

# no need to use logfile in container environment
# logfile = %(log_path)s/xrpcd-%(job_name)s.log
pidfile = %(pid_path)s/xrpcd-%(job_name)s.pid

# 10 MB * 10 = 100 MB total
log_size = 10485760
log_count = 10
```


## Setup `xrpcd`

```bash
xrpcd /path/to/xrpcd.ini install
```


## Run `xrpcd`

```bash
xrpcd /path/to/xrpcd.ini play -d
```
