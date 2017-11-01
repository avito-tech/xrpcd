# coding=utf-8

import unittest
import os
import time

import compose.cli.command as docker_compose_cmd
import compose.config.environment as docker_compose_env
import compose.project as docker_compose_project

import psycopg2

SLEEP_TIME_SEC = 5


def wait_for_event_playback(timeout=SLEEP_TIME_SEC):
    time.sleep(timeout)


class XrpcdTestCase(unittest.TestCase):
    sut = None  # type: docker_compose_project.Project
    db = None  # type: psycopg2._psycopg.connection

    @classmethod
    def setUpClass(cls):
        environment = docker_compose_env.Environment.from_env_file(".")
        cls.sut = docker_compose_cmd.get_project('.', environment=environment, verbose=True)
        cls.sut.pull()
        cls.sut.up()

        dsn = "host={host} dbname=template1 user=postgres connect_timeout=1".format(
            host=os.getenv("PGHOST", "localhost")
        )
        cls.db = psycopg2.connect(dsn)
        cls.db.autocommit = True
        wait_for_event_playback(3)  # Wait for install and start of xrpcd

    @classmethod
    def tearDownClass(cls):
        cls.sut.down(remove_image_type=False, include_volumes=False, remove_orphans=False)
        cls.db.close()

    @classmethod
    def cursor(cls):
        return cls.db.cursor()


class StandardUsageXrpcdTestCase(XrpcdTestCase):
    # Write more tests using this template.
    # Learn more about AAA(A) technique: http://wiki.c2.com/?ArrangeActAssert
    #
    # def test_template(self):
    #     # Arrange
    #     # Act
    #     # Assert
    #     self.assertTrue(True)

    def test_basic_call(self):
        # Arrange
        with self.cursor() as curs:
            curs.execute("""
                create table basic_call_tbl (i integer);
                create function basic_call_func(payload_unused hstore) returns void language plpgsql as $$
                    begin
                      insert into basic_call_tbl (i) values (1);
                    end;
                $$;
            """)

        # Act
        with self.cursor() as curs:
            curs.execute("""
                select xrpc._call(
                    queue := xrpc.x_qname('queue'),
                    dbconn := 'template1'::text,
                    func := 'public.basic_call_func'::text,
                    args := ''::hstore
                );
            """)
            wait_for_event_playback()

        # Assert
        with self.cursor() as curs:
            curs.execute("""
                select count(*) from basic_call_tbl
            """)
            actual = curs.fetchone()[0]

        self.assertEquals(1, actual)

    def test_sequential_call(self):
        # Arrange
        with self.cursor() as curs:
            curs.execute("""
                create table sequential_call_tbl (i integer);
                create function sequential_call_func(payload hstore) returns void language plpgsql as $$
                    begin
                      insert into sequential_call_tbl (i) values ((payload->'value')::int);
                    end;
                $$;
            """)

        # Act
        with self.cursor() as curs:
            for i in xrange(1, 4):
                curs.execute("""
                    select xrpc._call(
                        queue := xrpc.x_qname('queue'),
                        dbconn := 'template1'::text,
                        func := 'public.sequential_call_func'::text,
                        args := hstore('value', %(call_num)s)
                    );
                """, {"call_num": str(i)})
            wait_for_event_playback()

        # Assert
        with self.cursor() as curs:
            curs.execute("""
                select * from sequential_call_tbl order by xmin::text::int
            """)
            actual = curs.fetchall()

        self.assertEquals([(1,), (2,), (3,)], actual)

    def test_unexistent_function_call(self):
        # Arrange
        with self.cursor() as curs:
            curs.execute("""
                create table unexistent_function_call_tbl (i integer);
                create function unexistent_function_call_func(payload hstore) returns void language plpgsql as $$
                    begin
                      insert into unexistent_function_call_tbl (i) values ((payload->'value')::int);
                    end;
                $$;
            """)

        # Act
        with self.cursor() as curs:
            curs.execute("""
                select xrpc._call(
                    queue := xrpc.x_qname('queue'),
                    dbconn := 'template1'::text,
                    func := 'public.unexistent_function_call_func'::text,
                    args := hstore('value', '1')
                );
            """)
            # We should force tick in order to split first batch and next one.
            curs.execute("""
                select pgq.force_tick(xrpc.x_qname('queue'));
            """)
            wait_for_event_playback(1)
            curs.execute("""
                select xrpc._call(
                    queue := xrpc.x_qname('queue'),
                    dbconn := 'template1'::text,
                    func := 'public.this_is_invalid_function_name_breaking_all_the_things'::text,
                    args := hstore('value', '2')
                );
            """)
            curs.execute("""
                select xrpc._call(
                    queue := xrpc.x_qname('queue'),
                    dbconn := 'template1'::text,
                    func := 'public.unexistent_function_call_func'::text,
                    args := hstore('value', '3')
                );
            """)
            wait_for_event_playback()

        # Assert
        with self.cursor() as curs:
            curs.execute("""
                select * from unexistent_function_call_tbl order by xmin::text::int
            """)
            actual = curs.fetchall()

        self.assertEquals([(1,)], actual)


if __name__ == '__main__':
    unittest.main()
