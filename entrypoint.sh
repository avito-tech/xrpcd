#!/usr/bin/env bash

set -x

XRPCD_INI=/var/run/postgresql/xprcd.ini

envsubst < /xrpcd.ini.dist > $XRPCD_INI

PGHOST=$1 /wait-for-postgres.sh

xrpcd $XRPCD_INI install
xrpcd $XRPCD_INI play
