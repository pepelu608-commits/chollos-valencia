alter table anuncios
  add column if not exists puntos integer default 0,
  add column if not exists motivos text,
  add column if not exists alertas text,
  add column if not exists grupo text,
  add column if not exists referencia_catastral text,
  add column if not exists anyo integer;
create index if not exists anuncios_grupo on anuncios (grupo);
create index if not exists anuncios_puntos on anuncios (descartado, puntos desc);
