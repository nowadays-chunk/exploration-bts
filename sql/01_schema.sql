-- MySQL 8.0.16+ is required for enforced CHECK constraints.
-- Create the database once in your hosting provider's console:
-- CREATE DATABASE airdata CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
-- The loader connects to that database and creates these tables.

CREATE TABLE IF NOT EXISTS airlines (
    carrier VARCHAR(2) NOT NULL,
    name VARCHAR(255) NOT NULL,
    PRIMARY KEY (carrier),
    CONSTRAINT airlines_carrier_format
        CHECK (REGEXP_LIKE(carrier, '^[A-Z0-9]{2}$', 'c'))
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS airports (
    faa VARCHAR(3) NOT NULL,
    name VARCHAR(255) NOT NULL,
    lat DOUBLE,
    lon DOUBLE,
    alt INT,
    tz INT,
    dst VARCHAR(8),
    tzone VARCHAR(64),
    metadata_source VARCHAR(32) NOT NULL DEFAULT 'dataset',
    PRIMARY KEY (faa),
    CONSTRAINT airports_faa_format
        CHECK (REGEXP_LIKE(faa, '^[A-Z0-9]{3}$', 'c')),
    CONSTRAINT airports_metadata_source
        CHECK (metadata_source IN ('dataset', 'flight_reference'))
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS planes (
    tailnum VARCHAR(6) NOT NULL,
    year INT,
    type VARCHAR(255),
    manufacturer VARCHAR(255),
    model VARCHAR(255),
    engines INT,
    seats INT,
    speed INT,
    engine VARCHAR(64),
    metadata_source VARCHAR(32) NOT NULL DEFAULT 'dataset',
    PRIMARY KEY (tailnum),
    CONSTRAINT planes_tailnum_format
        CHECK (REGEXP_LIKE(tailnum, '^[A-Z0-9]{1,6}$', 'c')),
    CONSTRAINT planes_metadata_source
        CHECK (metadata_source IN ('dataset', 'flight_reference'))
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS weather (
    year INT NOT NULL,
    month TINYINT NOT NULL,
    day TINYINT NOT NULL,
    `hour` TINYINT NOT NULL,
    origin VARCHAR(3) NOT NULL,
    temp DOUBLE,
    dewp DOUBLE,
    humid DOUBLE,
    wind_dir DOUBLE,
    wind_speed DOUBLE,
    wind_gust DOUBLE,
    precip DOUBLE,
    pressure DOUBLE,
    visib DOUBLE,
    time_hour DATETIME NOT NULL COMMENT 'UTC timestamp from the source data',
    PRIMARY KEY (year, month, day, `hour`, origin, time_hour),
    CONSTRAINT weather_month_range CHECK (month BETWEEN 1 AND 12),
    CONSTRAINT weather_day_range CHECK (day BETWEEN 1 AND 31),
    CONSTRAINT weather_hour_range CHECK (`hour` BETWEEN 0 AND 23),
    CONSTRAINT weather_origin_format
        CHECK (REGEXP_LIKE(origin, '^[A-Z0-9]{3}$', 'c')),
    CONSTRAINT weather_origin_airport_fk
        FOREIGN KEY (origin) REFERENCES airports (faa),
    KEY weather_origin_time_idx (origin, time_hour)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS flights (
    year INT NOT NULL,
    month TINYINT NOT NULL,
    day TINYINT NOT NULL,
    dep_time INT,
    sched_dep_time INT,
    dep_delay DOUBLE,
    arr_time INT,
    sched_arr_time INT,
    arr_delay DOUBLE,
    carrier VARCHAR(2) NOT NULL,
    flight INT NOT NULL,
    tailnum VARCHAR(6),
    origin VARCHAR(3) NOT NULL,
    dest VARCHAR(3) NOT NULL,
    air_time DOUBLE,
    distance INT,
    `hour` TINYINT NOT NULL,
    minute TINYINT,
    time_hour DATETIME COMMENT 'UTC timestamp from the source data',
    PRIMARY KEY (year, month, day, `hour`, carrier, flight),
    KEY flights_tailnum_idx (tailnum),
    KEY flights_origin_idx (origin),
    KEY flights_dest_idx (dest),
    KEY flights_time_hour_idx (time_hour),
    CONSTRAINT flights_month_range CHECK (month BETWEEN 1 AND 12),
    CONSTRAINT flights_day_range CHECK (day BETWEEN 1 AND 31),
    CONSTRAINT flights_hour_range CHECK (`hour` BETWEEN 0 AND 23),
    CONSTRAINT flights_carrier_format
        CHECK (REGEXP_LIKE(carrier, '^[A-Z0-9]{2}$', 'c')),
    CONSTRAINT flights_origin_format
        CHECK (REGEXP_LIKE(origin, '^[A-Z0-9]{3}$', 'c')),
    CONSTRAINT flights_dest_format
        CHECK (REGEXP_LIKE(dest, '^[A-Z0-9]{3}$', 'c')),
    CONSTRAINT flights_airline_fk
        FOREIGN KEY (carrier) REFERENCES airlines (carrier),
    CONSTRAINT flights_plane_fk
        FOREIGN KEY (tailnum) REFERENCES planes (tailnum),
    CONSTRAINT flights_origin_airport_fk
        FOREIGN KEY (origin) REFERENCES airports (faa),
    CONSTRAINT flights_dest_airport_fk
        FOREIGN KEY (dest) REFERENCES airports (faa)
) ENGINE=InnoDB;
