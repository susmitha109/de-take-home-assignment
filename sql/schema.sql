-- ============================================================================
--  Manulife DE Take-Home — MySQL schema
--  Tables: raw_orders (bronze) -> stage_orders (silver)
--          -> clean_orders + rejected_orders (gold)
--  Run with:  mysql -u root -p < sql/schema.sql
-- ============================================================================

CREATE DATABASE IF NOT EXISTS manulife_takehome
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE manulife_takehome;

-- ----------------------------------------------------------------------------
-- raw_orders — lossless landing zone
--   Every CSV row stored as TEXT (no casting). Two audit columns:
--     create_ts        : when this row was loaded (server time)
--     input_file_name  : source file (used to skip re-processing same file)
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS raw_orders;
CREATE TABLE raw_orders (
  source_row_id          BIGINT       NOT NULL AUTO_INCREMENT,
  create_ts       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  input_file_name VARCHAR(255) NOT NULL,

  order_id      TEXT,
  customer_id   TEXT,
  customer_name TEXT,
  email         TEXT,
  phone         TEXT,
  country       TEXT,
  state         TEXT,
  city          TEXT,
  address       TEXT,
  postal_code   TEXT,
  order_date    TEXT,
  ship_date     TEXT,
  ship_mode     TEXT,
  item_sku      TEXT,
  item_name     TEXT,
  quantity      TEXT,
  unit_price    TEXT,
  currency      TEXT,
  discount_code TEXT,
  order_notes   TEXT,

  PRIMARY KEY (source_row_id),
  KEY ix_raw_file (input_file_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ----------------------------------------------------------------------------
-- stage_orders — typed staging layer
--   All cleaned rows (good and bad) land here with proper types but NO
--   uniqueness or NOT NULL constraints. Lets us re-run validation rules
--   without re-cleaning from raw.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS stage_orders;
CREATE TABLE stage_orders (
  stage_id        BIGINT       NOT NULL AUTO_INCREMENT,
  source_row_id          BIGINT       NOT NULL,
  input_file_name VARCHAR(255) NOT NULL,
  processed_ts    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

  order_id      VARCHAR(64),
  customer_id   VARCHAR(64),
  customer_name VARCHAR(255),
  email         VARCHAR(255),
  phone         VARCHAR(32),
  country       CHAR(2),
  state         VARCHAR(64),
  city          VARCHAR(128),
  address       VARCHAR(255),
  postal_code   VARCHAR(32),
  order_date    DATE,
  ship_date     DATE,
  ship_mode     VARCHAR(32),
  item_sku      VARCHAR(64),
  item_name     VARCHAR(255),
  quantity      INT,
  unit_price    DECIMAL(12,2),
  currency      CHAR(3),
  discount_code VARCHAR(64),
  order_notes   TEXT,

  PRIMARY KEY (stage_id),
  KEY ix_stage_file (input_file_name),
  KEY ix_stage_raw  (source_row_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ----------------------------------------------------------------------------
-- clean_orders — typed silver layer
--   One row per (order_id, item_sku). All columns typed and validated.
--   source_row_id links back to bronze for lineage.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS clean_orders;
CREATE TABLE clean_orders (
  clean_id        BIGINT       NOT NULL AUTO_INCREMENT,
  source_row_id          BIGINT       NOT NULL,
  input_file_name VARCHAR(255) NOT NULL,
  processed_ts    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

  order_id      VARCHAR(64)   NOT NULL,
  customer_id   VARCHAR(64)   NOT NULL,
  customer_name VARCHAR(255)  NOT NULL,
  email         VARCHAR(255),
  phone         VARCHAR(32),
  country       CHAR(2),
  state         VARCHAR(64),
  city          VARCHAR(128),
  address       VARCHAR(255),
  postal_code   VARCHAR(32),
  order_date    DATE          NOT NULL,
  ship_date     DATE,
  ship_mode     VARCHAR(32),
  item_sku      VARCHAR(64)   NOT NULL,
  item_name     VARCHAR(255)  NOT NULL,
  quantity      INT           NOT NULL,
  unit_price    DECIMAL(12,2) NOT NULL,
  currency      CHAR(3),
  discount_code VARCHAR(64),
  order_notes   TEXT,

  PRIMARY KEY (clean_id),
  UNIQUE KEY uq_order_sku (order_id, item_sku),
  KEY ix_clean_file (input_file_name),
  KEY ix_clean_raw  (source_row_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ----------------------------------------------------------------------------
-- rejected_orders — quarantine
--   Same shape as raw_orders (lossless TEXT) plus the reason a row was rejected.
--   Lets a human see exactly what arrived without re-running the pipeline.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS rejected_orders;
CREATE TABLE rejected_orders (
  rejected_id      BIGINT       NOT NULL AUTO_INCREMENT,
  source_row_id           BIGINT       NOT NULL,
  input_file_name  VARCHAR(255) NOT NULL,
  processed_ts     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  rejection_reason VARCHAR(128) NOT NULL,

  order_id      TEXT,
  customer_id   TEXT,
  customer_name TEXT,
  email         TEXT,
  phone         TEXT,
  country       TEXT,
  state         TEXT,
  city          TEXT,
  address       TEXT,
  postal_code   TEXT,
  order_date    TEXT,
  ship_date     TEXT,
  ship_mode     TEXT,
  item_sku      TEXT,
  item_name     TEXT,
  quantity      TEXT,
  unit_price    TEXT,
  currency      TEXT,
  discount_code TEXT,
  order_notes   TEXT,

  PRIMARY KEY (rejected_id),
  KEY ix_rejected_file (input_file_name),
  KEY ix_rejected_raw  (source_row_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

USE manulife_takehome;

SELECT * FROM raw_orders;

SELECT * FROM stage_orders;

SELECT * FROM clean_orders;

SELECT * FROM rejected_orders;
