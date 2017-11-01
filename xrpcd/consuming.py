# -*- coding: utf-8 -*-

"""XRPC executor"""

import os
import sys
import copy
import traceback
import psycopg2.extras
import pgq
import logging
import logging.handlers

EXIT_SUCCESS = 0
EXIT_FAILURE = 1

BATCH_CHUNK_LEN = 16 * 1024 # bytes

command_usage = """
%prog [options] INI [CMD]

commands:
  install                       installs functions and tables in database
  play                          start calling remote procedures
"""


class Call(object):
    def __init__(self, event, log=None):
        self.log = log

        self.id = event.id
        self.type = event.type
        self.db = event.extra1
        self.func = event.extra2
        self.args = event.extra3
        self.time = event.time

        self.args_obj = self.hstore_decode()

    def hstore_decode(self):
        data = None
        try:
            if self.args is None:
                data = {}
            else:
                data = psycopg2.extras.HstoreAdapter.parse(self.args, None)
        except Exception:
            exc_type, exc_value, exc_tb = sys.exc_info()
            if self.log:
                self.log.error("Cannot parse event_id=%d, args: [%s], error: %s",
                               self.id, self.args,
                               "".join(traceback.format_exception(exc_type, exc_value, exc_tb, 2))
                               )
        finally:
            return data

    def __repr__(self):
        fmt = (
            "<id={t.id} type={t.type} db={t.db}"
            " func=[{t.func}] args=[{t.args}] time=[{t.time}]"
            " args_obj=[{args_obj_repr}]>"
        )
        return fmt.format(t=self, args_obj_repr=repr(self.args_obj))


class XRpcConsumer(pgq.Consumer):
    def __init__(self, service_name, db_name, args):
        pgq.Consumer.__init__(self, service_name, db_name, args)

        if self.cf.get("log_debug", False):
            self.log.setLevel(logging.DEBUG)

        if len(self.args) < 2:
            print "need command"
            sys.exit(1)
        cmd = self.args[1]

        if cmd == "install":
            sys.exit(self.install())
        elif cmd == "play":
            self.log.debug("=== XRpcConsumer:__init__ ===")

            self.xrpc_source = self.cf.get("xrpc_source")
            self.xrpc_dsn = self.cf.get("xrpc_dsn")
            self.log.debug("XRpcConsumer.__init__ xrpc_source: {t.xrpc_source}".format(t=self))
            # self.set_single_loop(1) # debug
        else:
            print "Unknown command '%s', use --help for help" % cmd
            sys.exit(1)

    def init_optparse(self, parser=None):
        p = pgq.Consumer.init_optparse(self, parser)
        p.set_usage(command_usage.strip())
        return p

    def sort_max_id(self, events, params):
        # Detecting maximal id, where will put any 'bad' event (to the tail)
        max_id = 0
        for event in events:
            data = event.args_obj
            if data:
                max_param_id = max([int(data.get(param, 0)) for param in params])
                if max_param_id > max_id:
                    max_id = max_param_id
        return max_id

    def sort_index(self, event, max_id, params):
        # Getting ids and make sort indexes from them
        data = event.args_obj
        tail_id = max_id + 1
        sorting = []
        for param in params:
            if data:
                sorting.append(int(data.get(param, tail_id)))
            else:
                sorting.append(tail_id)
        return sorting

    def log_delay_on(self):
        handler_list = copy.copy(self.log.handlers)
        for handler in handler_list:
            if handler.__class__.__name__ != "MemoryHandler":
                # If not at daemon mode
                if not self.go_daemon:
                    # -> skip StreamHandlers with stderr streams
                    if handler.stream and (handler.stream == sys.stderr):
                        continue

                mem = logging.handlers.MemoryHandler(100, logging.CRITICAL, handler)

                self.log.removeHandler(handler)
                self.log.addHandler(mem)

    def log_delay_off(self):
        handler_list = copy.copy(self.log.handlers)
        for handler in handler_list:
            if handler.__class__.__name__ == "MemoryHandler":
                handler.flush()
                target = handler.target

                handler.close()
                self.log.removeHandler(handler)
                self.log.addHandler(target)

    def process_batch(self, db, batch_id, event_list):
        self.log.debug("=== process_batch ===")
        cur_batch_info = self.get_batch_info(batch_id)

        for ev in event_list:
            ev.tag_done()

        xdb_calls = self.build_db_calls([Call(ev, self.log) for ev in event_list])
        for xdb in xdb_calls:
            self.log.debug("{0}: {1}".format(xdb, xdb_calls[xdb]))

            # skytools/python/scripting.py:get_database
            # User must not store it permanently somewhere,
            # as all connections will be invalidated on reset.
            dst_db = self.get_database(xdb, connstr=self.xrpc_dsn.format(xdb))
            curs = dst_db.cursor()

            self.log_delay_on()
            if self.is_last_batch(curs, batch_id):
                dst_db.commit()
                self.log.warning("Skip processed batch %s (tick %s) for %s", batch_id, cur_batch_info["tick_id"], xdb)
                self.log_delay_off()
                continue

            dst_db.commit()
            self.log_delay_off()

            curs = dst_db.cursor()
            curs.execute("select set_config('xrpc.tick_id', %s::text, true)",
                         [cur_batch_info["tick_id"]])  # todo type of tick_id

            batch_query = None
            event_queries = []

            # params that shows how to sort event
            params = ("user_id", "item_id")
            try:
                # sorting events
                max_id = self.sort_max_id(xdb_calls[xdb], params)
                xdb_calls[xdb] = sorted(xdb_calls[xdb], key=lambda (event): self.sort_index(event, max_id, params))
            except Exception as e:
                exc_type, exc_value, exc_tb = sys.exc_info()
                self.log.warning("Cannot sort events: %s",
                                 "".join(traceback.format_exception(exc_type, exc_value, exc_tb, 2)))

            # building individual sql queries
            for event in xdb_calls[xdb]:
                if event.args_obj is not None:
                    event_sql = self.get_call_query(curs, self.xrpc_source, batch_id, event)
                    event_queries.append(event_sql)
                else:
                    raise Exception("ERROR: Bad hstore, cannot build query for event=[%s]" % repr(event))

            # building final sql query
            batch_query = ""
            i = 0
            for q in event_queries:
                i += 1
                batch_query += q + ";"
                if len(batch_query) > BATCH_CHUNK_LEN:
                    self.log.info("i: %d event_queries: %d batch_query: %d" % (i, len(event_queries), len(batch_query)))
                    curs.execute(batch_query)
                    batch_query = ""
            if batch_query:
                self.log.info("i: %d event_queries: %d batch_query: %d" % (i, len(event_queries), len(batch_query)))
                curs.execute(batch_query)
                batch_query = ""

            self.log_delay_on()
            self.set_last_batch(curs, batch_id)
            dst_db.commit()
            self.log_delay_off()

    def is_last_batch(self, dst_curs, batch_id):
        self.log.debug("=== is_last_batch ===")
        q = "select not xrpc.check_batch(%s, %s, %s)"
        dst_curs.execute(q, [self.xrpc_source, self.pgq_queue_name, batch_id])
        res = dst_curs.fetchone()[0]
        self.log.debug("is_last_batch: {0}".format(res))
        return res

    def set_last_batch(self, dst_curs, batch_id):
        self.log.debug("=== set_last_batch ===")
        q = "select xrpc.set_batch_done(%s, %s, %s)"
        dst_curs.execute(q, (self.xrpc_source, self.pgq_queue_name, batch_id))
        msg = "set_last_batch: {t.xrpc_source}, {t.pgq_queue_name}, {batch_id}".format(t=self, batch_id=batch_id)
        self.log.debug(msg)

    def build_db_calls(self, calls):
        self.log.debug("=== build_db_calls ===")
        db_calls = {}
        for cl in calls:
            if not db_calls.has_key(cl.db):
                db_calls[cl.db] = [cl]
                continue
            db_calls[cl.db].append(cl)
        return db_calls

    def get_call_query(self, curs, db, batch_id, c):
        self.log.debug("=== get_call_query ===")
        res = curs.mogrify("select xrpc.do_call(%s, %s, %s, %s, %s, %s, %s, %s)",
                           (db, self.pgq_queue_name, batch_id, c.id, str(c.time), c.type, c.func, c.args))
        self.log.debug("get_call_query: {0}".format(res))
        return res

    def install(self):
        self.log.info("Installing schema, functions and tables into target database")

        with open(os.path.join(os.path.dirname((__file__)), "sql/schema.sql.tpl"), "r") as f:
            sql = f.read().format(current_database=self.cf.get("provider_db_name"))

        db = self.get_database(self.db_name)
        cx = db.cursor()

        try:
            cx.execute(sql)
            db.commit()
            self.log.info("Schema, functions and tables successfully installed into target database")
            return EXIT_SUCCESS
        except psycopg2.Error as e:
            exc_type, exc_value, exc_tb = sys.exc_info()
            self.log.error("Got error while installing schema, functions and tables into target database:\n%s",
                           "".join(traceback.format_exception(exc_type, exc_value, exc_tb, 2)))
            return EXIT_FAILURE
