CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username VARCHAR(100)
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    total DECIMAL(10, 2)
);

INSERT INTO users VALUES (1, 'gokhan');
INSERT INTO users VALUES (2, 'sample');
INSERT INTO orders VALUES (1, 1, 149.90);
