set local client_encoding = 'utf8';
set local standard_conforming_strings = off;
set local check_function_bodies = false;
set local client_min_messages = warning;
set local escape_string_warning = off;

create schema "xrpc";

create extension if not exists hstore with schema public;

set local search_path = "xrpc", pg_catalog;


create function "_call"(
  "queue" "text",
  "dbconn" "text",
  "func" "text",
  "args" "public"."hstore"
)
returns bigint
language "sql" strict
as $$
  --
  --  вызов удаленной функции
  --
  --  реализуем
  --    eventual consistency  ( http://en.wikipedia.org/wiki/eventual_consistency )
  --
  --  организуем
  --    base кластер          ( http://en.wikipedia.org/wiki/eventual_consistency base )
  --    поверх acid баз       ( http://en.wikipedia.org/wiki/immediate_consistency, http://en.wikipedia.org/wiki/acid )
  --
  --  // нужны процедуры восстановления
  --

  --- pgq.insert_event(      queue_name,                          ev_type, ev_data, ev_extra1, ev_extra2, ev_extra3, ev_extra4 )
  --- pgq.insert_event_raw(  queue_name, null, now(), null, null, ev_type, ev_data, ev_extra1, ev_extra2, ev_extra3, ev_extra4 )

    select pgq.insert_event_raw
    (
        queue,                    -- queue_name
        null, now(), null, null,
        null,   -- '100',         -- ev_type
        null,   -- '1.1',         -- ev_data (rpc version)

        dbconn,                   -- ev_extra1
        func,                     -- ev_extra2
        args::text,               -- ev_extra3

        null    -- now()::timestamp::text  -- ev_extra4
    );
$$;


create function "_self_call"(
  "queue" "text",
  "func" "text",
  "args" "public"."hstore"
)
returns bigint
language "sql" strict
as $$
  select xrpc._call
  (
      queue,
      xrpc.current_database(),
      func,
      args
  )
$$;


create function "check_batch"(
  "_source_db" "text",
  "_qname" "text",
  "_batch_id" bigint
)
returns boolean
language "plpgsql"
as $$
  --
  --  проверка в приемнике
  --  обаработали ли уже данный батч?
  --    если не обработали ( текущий отмеченный меньше входного ), то батч - true
  --    если не нашли, регистрируем источник и - батч true
  --    иначе, - батч false
  --
  --  http://skytools.projects.pgfoundry.org/doc/pgq-nodupes.html
  --

  declare

    res boolean;

  begin
    select into res
      (
        _batch_id > x.last_performed_batch_id
      )
    from xrpc.source_queues x
    where x.source_db = _source_db and x.qname = _qname;

    if ( not found ) then
      perform xrpc.x_register_source_queue(_source_db, _qname);
      res := true;
    end if;

    return res;
  end;
$$;


create function "current_database"() returns "text"
language "sql" immutable
as $$
  -- Возвращает имя базы/пула.
  -- Вписываться во время создания функции с помощью подкоманды install.
  select text '{current_database}';
$$;


create function "do_call"(
  "_source_db" "text",
  "_source_queue" "text",
  "_batch_id" bigint,
  "_call_id" bigint,
  "_call_txtime" "text",
  "_call_type" "text",
  "func" "text",
  "args" "public"."hstore"
) returns integer
language "plpgsql"
as $$
  begin
    execute
    'select "' || replace(func, '.', '"."') || '"( $1 )'
    using
      coalesce( args, hstore '' ) ||
      hstore( 'xrpc.call_id', _call_id::text );

    return 0;
  end;
$$;


create function "set_batch_done"(
  "_source_db" "text",
  "_qname"     "text",
  "_batch_id"  bigint
)
returns integer
language "sql" strict
set "synchronous_commit" to 'on'
as $$
  -- отметка в приемнике о выполнение бaтча (всех вызовов из него) - http://skytools.projects.pgfoundry.org/doc/pgq-nodupes.html
  update xrpc.source_queues x set last_performed_batch_id = _batch_id
  where
    x.source_db  = _source_db and
    x.qname      = _qname
  ;
  select 0;
  -- set synchronous_commit = on
$$;


create function "x_qname"(
  "qname" "text"
)
returns "text"
language "sql" immutable strict
as $$
  select format( xrpc.x_qname_format(), qname );
$$;


create function "x_qname"(
  "qname" "text",
  "qix" integer
)
returns "text"
language "sql" immutable strict
as $$
  select format( xrpc.x_qname_format2(), qname, to_char( qix, 'fm' || '00' ) );
$$;


create function "x_qname_format"() returns "text"
language "sql" immutable strict
as $$
  select text 'xrpc_%s';
$$;


create function "x_qname_format2"() returns "text"
language "sql" immutable strict
as $$
  select xrpc.x_qname_format() || text '_%s';
$$;


create function "x_register_source_queue"(
  "_source_db" "text",
  "_qname" "text"
)
returns integer
language "sql" strict
as $$
  -- регистрация источника в приемнике
  insert into xrpc.source_queues ( source_db, qname ) values ( _source_db, _qname );
  select 0;
$$;


create table "source_queues" (
  "source_db" "text" not null,
  "qname" "text" not null,
  "last_performed_batch_id" bigint default 0 not null
);


alter table only "source_queues"
  add constraint "source_queues_qdatabase_qname_key" unique ("source_db", "qname");
